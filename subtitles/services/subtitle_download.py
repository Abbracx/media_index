import structlog

from asgiref.sync import sync_to_async
from django.db.models import QuerySet, OuterRef, Exists
from typing import Any

from TMDB.models import Movie
from subtitles.models import MovieSubtitle
from subtitles.services.opensubtitle import OpenSubtitlesService
from subtitles.services.storage import SubtitleStorageService

log: structlog.BoundLogger = structlog.get_logger(__name__)


class SubtitleDownloadService:
    """Service for finding movies without subtitles and downloading them"""

    def __init__(self) -> None:
        self.subtitle_service = OpenSubtitlesService()
        self.storage_service = SubtitleStorageService()

    def get_movies_without_subtitles(
        self,
        language: str = "en",
        limit: int | None = None,
    ) -> QuerySet[Movie]:
        """
        Get movies that don't have subtitles.

        Args:
            language: Language code for subtitles
            limit: Optional limit on number of movies
        """
        # Find movies without any active subtitles in the specified language
        active_subtitles = MovieSubtitle.objects.filter(
            movie=OuterRef("pk"), language=language, is_active=True
        )

        movies = (
            Movie.objects.annotate(has_subtitle=Exists(active_subtitles))
            .filter(has_subtitle=False)
            .order_by("-release_date")
        )

        if limit:
            movies = movies[:limit]

        return movies

    async def download_and_save_subtitles(
        self, movie: Movie, language: str = "en"
    ) -> dict[str, Any]:
        """
        Download and save subtitle for a single movie.

        Args:
            movie: Movie to download subtitle for
            language: Language code for subtitles

        Returns:
            Dict containing download status and results
        """
        try:
            log.info(
                "Downloading subtitle",
                movie_id=movie.id,
                tmdb_id=movie.tmdb_id,
                language=language,
            )

            # Download subtitle from OpenSubtitles
            content, format, metadata = await self.subtitle_service.search_and_download(
                tmdb_id=movie.tmdb_id, language=language
            )

            # Store subtitle
            subtitle = await sync_to_async(self.storage_service.store_subtitle)(
                movie=movie,
                subtitle_content=content,
                metadata=metadata,
                subtitle_format=format,
            )

            log.info(
                "Successfully downloaded subtitle",
                movie_id=movie.id,
                subtitle_id=subtitle.id,
            )

            return {
                "status": "success",
                "movie_id": movie.id,
                "subtitle_id": subtitle.id,
            }

        except Exception as e:
            log.error(
                "Failed to download subtitle",
                movie_id=movie.id,
                error=str(e),
                exc_info=True,
            )

            return {"status": "error", "movie_id": movie.id, "error": str(e)}
