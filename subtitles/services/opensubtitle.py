import asyncio
from datetime import datetime
from io import BytesIO
import structlog
from typing import Callable, Any

from django.conf import settings
from opensubtitlescom import OpenSubtitles, OpenSubtitlesException

from opensubtitlescom.responses import DownloadResponse, Subtitle

from TMDB.services.tmdb_service import RateLimiter
from .subtitle_scoring import SubtitleQualityScorer
from ..models import MovieSubtitle
from ..schemas import (
    FeatureDetails,
    SubtitleFile,
    SubtitleMetadata,
    SubtitleSearchResponse,
    UploaderInfo,
)

log: structlog.BoundLogger = structlog.get_logger(__name__)


SUBTITLE_AUTH_SETTINGS = settings.SUBTITLE_SETTINGS["OPENSUBTITLES"]


class CustomOpenSubtitlesClient(OpenSubtitles):  # type: ignore
    """OVERIDE CLIENT DOWNLOAD METHOD TO RETURN RAW FILE LINK"""

    def download(
        self,
        file_id: str | Subtitle,
        sub_format: int | None = None,
        file_name: int | None = None,
        in_fps: int | None = None,
        out_fps: int | None = None,
        timeshift: int | None = None,
        force_download: bool | None = None,
    ) -> tuple[bytes, DownloadResponse]:
        """
        Download a single subtitle file using the file_no.

        Docs: https://opensubtitles.stoplight.io/docs/opensubtitles-api/6be7f6ae2d918-download
        """
        subtitle_id = file_id.file_id if isinstance(file_id, Subtitle) else file_id
        if not subtitle_id:
            raise OpenSubtitlesException("Missing subtitle file id.")

        download_body = {"file_id": subtitle_id}

        # Helper function to add a parameter to the query_params list
        def add_param(
            name: str,
            value: int | None = None,
        ) -> None:
            if value is not None:
                download_body[name] = value
            return

        add_param("sub_format", sub_format)
        add_param("file_name", file_name)
        add_param("in_fps", in_fps)
        add_param("out_fps", out_fps)
        add_param("timeshift", timeshift)
        add_param("force_download", force_download)

        search_response_data = DownloadResponse(
            self.send_api("download", download_body)
        )
        self.user_downloads_remaining = search_response_data.remaining

        return self.download_client.get(search_response_data.link), search_response_data


class OpenSubtitlesRateLimiter(RateLimiter):
    def __init__(self) -> None:
        self.user_downloads_remaining: int | None = None
        self.downloads_reset_time: datetime | None = None
        self._lock = asyncio.Lock()
        self.last_update = datetime.now()
        self._consecutive_429s = 0

        self.requests_per_second = 5
        self.tokens = float(self.requests_per_second)

    def update_download_quota(self, login_response: dict[str, dict[str, str]]) -> None:
        self.user_downloads_remaining = int(login_response["user"]["allowed_downloads"])
        log.info(
            "Updated download quota", remaining_downloads=self.user_downloads_remaining
        )

    async def acquire(self, endpoint: str = "") -> None:
        """Acquire rate limit token"""
        async with self._lock:
            # Check download quota first
            # await self.check_download_quota(endpoint)

            now = datetime.now()
            time_passed = (now - self.last_update).total_seconds()

            self.tokens = min(
                self.requests_per_second,
                self.tokens + time_passed * self.requests_per_second,
            )

            if self.tokens < 1:
                wait_time = (1 - self.tokens) / self.requests_per_second
                await asyncio.sleep(wait_time)
                self.tokens = 1

            self.tokens -= 1
            self.last_update = now

            if "/download" in endpoint and self.user_downloads_remaining is not None:
                self.user_downloads_remaining -= 1
                log.info(
                    "Download quota updated",
                    remaining_downloads=self.user_downloads_remaining,
                )


class OpenSubtitlesService:
    """Service for interacting with OpenSubtitles API"""

    def __init__(self) -> None:
        self.client = CustomOpenSubtitlesClient(
            api_key=SUBTITLE_AUTH_SETTINGS["OPENSUBTITLES_API_KEY"],
            user_agent=SUBTITLE_AUTH_SETTINGS["OPENSUBTITLES_APP_NAME"],
        )

        self.rate_limiter = OpenSubtitlesRateLimiter()
        self.rate_limiter.update_download_quota(
            self.client.login(
                SUBTITLE_AUTH_SETTINGS["OPENSUBTITLES_USERNAME"],
                SUBTITLE_AUTH_SETTINGS["OPENSUBTITLES_PASSWORD"],
            )
        )
        self._token: str | None = None
        self.downloads_remaining: int | None = None

    async def _get_user_token(self) -> str | None:
        """Get user token if credentials are configured"""
        log.debug("Getting user token")
        if ("OPENSUBTITLES_USERNAME" in SUBTITLE_AUTH_SETTINGS) and (
            "OPENSUBTITLES_PASSWORD" in SUBTITLE_AUTH_SETTINGS
        ):
            try:
                login_result = await asyncio.to_thread(
                    self.client.login,
                    SUBTITLE_AUTH_SETTINGS.get("OPENSUBTITLES_USERNAME"),
                    SUBTITLE_AUTH_SETTINGS.get("OPENSUBTITLES_PASSWORD"),
                )
                self._token = login_result["token"]
                self.token = login_result["token"]

                # Update rate limiter with download quota
                self.rate_limiter.handle_success()
                return str(login_result["token"])
            except Exception as e:
                log.error("OpenSubtitles user login failed", error=str(e))
                return None
        return None

    async def _make_request(
        self, func: Callable[..., Any], *args: Any, endpoint: str = "", **kwargs: Any
    ) -> Any:
        """Make rate-limited request to OpenSubtitles with auth"""
        # TODO: Rate limiting only applies for calls to /download and /infos/user endpoints
        max_retries = 1
        attempt = 0

        log.debug(
            "Making OpenSubtitles request",
            function=func.__name__,
            args=args,
            kwargs=kwargs,
        )
        while attempt < max_retries:
            try:
                await self.rate_limiter.acquire(endpoint=endpoint)

                result = await asyncio.to_thread(func, *args, **kwargs)

                self.rate_limiter.handle_success()
                log.debug("OpenSubtitles request successful", function=func.__name__)
                return result

            except Exception as e:
                if getattr(e, "status_code", None) == 429:
                    backoff = self.rate_limiter.handle_429()
                    if attempt < max_retries - 1:
                        log.warning(
                            "Rate limit hit, backing off",
                            backoff_seconds=backoff,
                            attempt=attempt + 1,
                        )
                        await asyncio.sleep(backoff)
                        attempt += 1
                        continue

                log.error(
                    "OpenSubtitles request failed",
                    function=func.__name__,
                    attempt=attempt + 1,
                    error=str(e),
                    has_user_token=bool(kwargs.get("token")),
                    exc_info=True,
                )

                if attempt == max_retries - 1:
                    raise

                attempt += 1
                await asyncio.sleep(2**attempt)

        raise Exception("Max retries exceeded")

    async def search_subtitles(
        self, tmdb_id: int, language: str
    ) -> list[SubtitleSearchResponse]:
        """Search for subtitles by TMDB ID"""
        log.info("Searching subtitles", tmdb_id=tmdb_id, language=language)

        try:

            search_response = await self._make_request(
                self.client.search, tmdb_id=tmdb_id, languages=language
            )

            if not search_response or not hasattr(search_response, "data"):
                log.warning("No subtitles found", tmdb_id=tmdb_id, language=language)
                return []
            subtitle_responses = [
                SubtitleSearchResponse(
                    id=str(subtitle.subtitle_id),
                    type="subtitle",
                    attributes=SubtitleMetadata(
                        subtitle_id=str(subtitle.subtitle_id),
                        language=subtitle.language,
                        download_count=subtitle.download_count,
                        new_download_count=subtitle.new_download_count,
                        hearing_impaired=subtitle.hearing_impaired,
                        hd=subtitle.hd,
                        fps=subtitle.fps,
                        votes=subtitle.votes,
                        ratings=subtitle.ratings,
                        from_trusted=subtitle.from_trusted,
                        foreign_parts_only=subtitle.foreign_parts_only,
                        upload_date=subtitle.upload_date,
                        file_hashes=[],
                        ai_translated=subtitle.ai_translated,
                        nb_cd=1,
                        slug=f"{subtitle.subtitle_id}-{subtitle.title.lower()}",
                        machine_translated=subtitle.machine_translated,
                        release=subtitle.release,
                        comments=subtitle.comments,
                        legacy_subtitle_id=subtitle.legacy_subtitle_id,
                        legacy_uploader_id=subtitle.uploader_id,
                        uploader=UploaderInfo(
                            uploader_id=subtitle.uploader_id,
                            name=subtitle.uploader_name,
                            rank=subtitle.uploader_rank,
                        ),
                        feature_details=FeatureDetails(
                            feature_id=subtitle.feature_id,
                            feature_type=subtitle.feature_type,
                            year=subtitle.year,
                            title=subtitle.title,
                            movie_name=subtitle.movie_name,
                            imdb_id=subtitle.imdb_id,
                            tmdb_id=subtitle.tmdb_id,
                        ),
                        url=subtitle.url,
                        related_links=[],
                        files=[
                            SubtitleFile(
                                file_id=subtitle.file_id,
                                cd_number=1,
                                file_name=subtitle.file_name,
                            )
                        ],
                    ),
                )
                for subtitle in search_response.data
            ]
            log.info(
                "Subtitle search completed",
                tmdb_id=tmdb_id,
                language=language,
                results_count=len(subtitle_responses),
            )

            return subtitle_responses

        except Exception as e:
            log.error(
                "Subtitle search failed",
                tmdb_id=tmdb_id,
                language=language,
                error=str(e),
                exc_info=True,
            )
            raise

            # Calculate quality score
            # from .quality import SubtitleQualityScorer
            # quality_score = await SubtitleQualityScorer.score_subtitle(metadata)

            # subtitle_infos.append(SubtitleInfo(
            # file_id=metadata.file_id,
            #  metadata=metadata,
            #  content_hash=item['hash'],
            #   quality_score=quality_score
            # ))

            # return sorted(subtitle_infos, key=lambda x: x.quality_score, reverse=True)

    async def download_subtitle(self, file_id: str) -> tuple[BytesIO, str]:
        """Download subtitle content with proper cleanup"""
        log.info("Downloading subtitle", file_id=file_id)

        content = BytesIO()
        try:
            raw_content, download_info = await self._make_request(
                self.client.download, file_id, endpoint="/download"
            )
            content.write(raw_content)
            content.seek(0)
            format = download_info.file_name.split(".")[-1].lower()
            if format not in MovieSubtitle.SubtitleFormat.values:
                format = "srt"  # Default to SRT if unknown

            log.info(
                "Subtitle download completed",
                file_id=file_id,
                format=format,
                size=content.tell(),
            )

            return content, format

        except Exception as e:
            content.close()  # Ensure content is closed on error
            log.error(
                "Subtitle download failed", file_id=file_id, error=str(e), exc_info=True
            )
            raise

    async def search_and_download(
        self, tmdb_id: int, language: str
    ) -> tuple[BytesIO, str, SubtitleMetadata]:
        """Search for best subtitle and download it"""
        log.info(
            "Searching and downloading subtitle", tmdb_id=tmdb_id, language=language
        )

        subtitles = await self.search_subtitles(tmdb_id, language)
        if not subtitles:
            msg = f"No subtitles found for TMDB ID {tmdb_id}"
            log.error(msg, tmdb_id=tmdb_id, language=language)
            raise Exception(msg)

        # Select best subtitle using quality scorer
        scorer = SubtitleQualityScorer()
        best_subtitle = scorer.select_best_subtitle(subtitles)

        content, format = await self.download_subtitle(
            str(best_subtitle.attributes.files[0].file_id)
        )

        log.info(
            "Search and download completed",
            tmdb_id=tmdb_id,
            language=language,
            subtitle_id=best_subtitle.id,
            format=format,
        )

        return content, format, best_subtitle.attributes
