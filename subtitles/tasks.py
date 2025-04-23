import asyncio
from datetime import datetime
import structlog
from asgiref.sync import sync_to_async
from django.conf import settings

from TMDB.models import Movie
from .services.subtitle_download import SubtitleDownloadService

from typing import Callable, TypeVar, Any, cast
from django_rq import job

log: structlog.BoundLogger = structlog.get_logger(__name__)
SUBTITLE_AUTH_SETTINGS = settings.SUBTITLE_SETTINGS["OPENSUBTITLES"]

# Define a type variable for the function
F = TypeVar("F", bound=Callable[..., Any])


def typed_job(queue_name: str, timeout: int) -> Callable[[F], F]:
    return cast(Callable[[F], F], job(queue_name, timeout=timeout))


@typed_job("subtitles", timeout=28800)
def download_missing_subtitles(
    language: str = "en",
    max_downloads: int = 100,
) -> None:
    """
    Background job to download subtitles for movies that don't have them.

    Args:
        language: Language code for subtitles
        max_downloads: Maximum number of subtitles to download
    """
    try:
        # Run the async downloading in a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            _download_missing_subtitles(
                language=language,
                max_downloads=max_downloads,
            )
        )
        loop.close()

    except Exception as e:
        log.error("Subtitle download job failed", error=str(e), exc_info=True)
        pass


async def _download_missing_subtitles(
    language: str = "en",
    max_downloads: int = 100,
) -> dict[str, float| int ]:
    """
    Core async function to download missing subtitles.
    Continues until reaching max successful downloads or exhausting movies.
    """
    try:
        service = SubtitleDownloadService()

      
        stats: dict[str, float | int] = {
            "started_at": datetime.now().timestamp(),
            "completed_at": 0,
            "total_attempted": 0,
            "successful": 0,
            "failed": 0,
            "no_subtitles_found": 0,
        }

        # Get all movies without subtitles (no limit here)
        movies: list[Movie] = await sync_to_async(
            lambda: list(
                service.get_movies_without_subtitles(
                    language=language, limit=max_downloads
                )
            )
        )()

        if not movies:
            log.info("No movies found needing subtitles")
            stats["completed_at"] = datetime.now().timestamp()
            return stats

        log.info(
            "Starting subtitle downloads",
            total_movies=len(movies),
            language=language,
            target_downloads=max_downloads,
        )

        # Continue until we hit our target successful downloads or run out of movies
        for movie in movies:
            if stats["successful"] is not None and stats["successful"] >= max_downloads:
                log.info(
                    "Reached target successful downloads",
                    successful=stats["successful"],
                    target=max_downloads,
                )
                break

            stats["total_attempted"] += 1

            try:
                result = await service.download_and_save_subtitles(
                    movie=movie, language=language
                )

                if result["status"] == "success":
                    stats["successful"] += 1
                    log.info(
                        "Successful download",
                        movie_id=movie.id,
                        successful_count=stats["successful"],
                        target=max_downloads,
                    )
                else:
                    stats["failed"] += 1
                    if "No subtitles found" in result.get("error", ""):
                        stats["no_subtitles_found"] += 1

            except Exception as e:
                stats["failed"] += 1
                log.error(
                    "Failed to process movie",
                    movie_id=movie.id,
                    error=str(e),
                    exc_info=True,
                )

        stats["completed_at"] = datetime.now().timestamp()
        duration = datetime.fromtimestamp(stats["completed_at"] - stats["started_at"])

        log.info(
            "Completed subtitle downloads",
            successful=stats["successful"],
            failed=stats["failed"],
            no_subtitles=stats["no_subtitles_found"],
            total_attempted=stats["total_attempted"],
            duration_seconds=duration,
        )

        return stats

    except Exception as e:
        log.error("Subtitle download job failed", error=str(e), exc_info=True)
        raise
