import django_rq
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Any
import structlog
from asgiref.sync import sync_to_async
from django.conf import settings
from rq import get_current_job

from .models import Movie, TMDBSyncQueue
from TMDB.services.tmdb_service import TMDBService

log: structlog.BoundLogger = structlog.get_logger(__name__)


@dataclass
class SyncResult:
    """Result of a sync operation."""

    successful_ids: list[int]
    failed_ids: list[dict[str, Any]]
    total_processed: int
    duration: float
    year: int
    language: str


async def sync_year(
    year: int, language: str = "en", max_results: int | None = 100
) -> None:
    """Sync movies for a specific year."""
    job = get_current_job()
    processed_count = 0
    failed_count = 0

    # Create sync log
    queue_entry = await sync_to_async(TMDBSyncQueue.objects.create)(
        year=year,
        language=language,
        job_id=job.id if job else None,
        status="IN_PROGRESS",
    )

    try:
        client = TMDBService(api_key=settings.TMDB_API_KEY)
        movies_iterator = client.get_movies_by_year(
            year=year, language=language, max_results=max_results
        )

        async for movie in movies_iterator:
            try:
                # Use get_or_create with direct field assignment
                log.info(
                    "Save movie",
                    movie_id=movie.tmdb_id,
                    title=movie.title,
                    year=year,
                    processed_so_far=processed_count,
                )
                await sync_to_async(Movie.objects.update_or_create)(
                    tmdb_id=movie.tmdb_id,
                    defaults={
                        "title": movie.title,
                        "original_title": movie.original_title,
                        "overview": movie.overview,
                        "release_date": movie.release_date,
                        "runtime": movie.runtime,
                        "poster_url": movie.poster_url,
                        "backdrop_url": movie.backdrop_url,
                        "vote_average": movie.vote_average,
                        "vote_count": movie.vote_count,
                        "genres": movie.genres,
                        "original_language": movie.original_language,
                        "language": language,
                        "author": movie.author,
                    },
                )
                processed_count += 1

                # Update running stats
                await sync_to_async(
                    TMDBSyncQueue.objects.filter(id=queue_entry.id).update
                )(
                    movies_processed=processed_count,
                    movies_failed=failed_count,
                )

            except Exception as e:
                failed_count += 1
                log.error(
                    "Failed to save movie",
                    movie_id=movie.tmdb_id if hasattr(movie, "tmdb_id") else "unknown",
                    title=movie.title if hasattr(movie, "title") else "unknown",
                    error=str(e),
                    processed_count=processed_count,
                    failed_count=failed_count,
                    exc_info=True,
                )
                continue

        await sync_to_async(TMDBSyncQueue.objects.filter(id=queue_entry.id).update)(
            status="COMPLETED",
            movies_processed=processed_count,
            movies_failed=failed_count,
        )

        log.info(
            "Completed year sync",
            year=year,
            processed_count=processed_count,
            failed_count=failed_count,
            queue_id=queue_entry.id,
            status="COMPLETED",
        )

    except Exception as e:
        # Only mark as failed for non-movie specific errors
        await sync_to_async(TMDBSyncQueue.objects.filter(id=queue_entry.id).update)(
            status="FAILED",
            error_message=str(e),
            movies_processed=processed_count,
            movies_failed=failed_count,
        )

        log.error(
            "Year sync failed with critical error",
            year=year,
            language=language,
            error=str(e),
            processed_count=processed_count,
            failed_count=failed_count,
            queue_id=queue_entry.id,
            exc_info=True,
        )
        raise


def enqueue_year_sync(
    year: int,
    language: str = "en-US",
    priority: int = 0,
    max_results: int | None = 100,
) -> str:
    """
    Enqueue a year for syncing.

    Args:
        year: Year to sync
        language: Language code to fetch
        priority: Queue priority (higher = more important)

    Returns:
        str: Job ID
    """
    queue = django_rq.get_queue("tmdb_sync", default_timeout=28800)

    job = queue.enqueue(
        sync_year,
        args=(year, language),
        kwargs={"max_results": max_results},
        job_id=f"year_sync_{year}_{language}",
        job_timeout=28800,
        meta={"year": year, "language": language, "type": "year_sync"},
    )

    # Track in our queue model
    TMDBSyncQueue.objects.create(
        job_id=job.id, year=year, language=language, priority=priority, status="PENDING"
    )

    return job.id  # type: ignore


def enqueue_year_range(
    start_year: int,
    end_year: int,
    language: str = "en",
    priority: int = 0,
    max_results: int | None = 100,
) -> List[str]:
    """
    Enqueue a range of years for syncing.

    Args:
        start_year: Starting year
        end_year: Ending year (inclusive)
        language: Language code to fetch
        priority: Base priority (will be adjusted by year)
        max_results: Total maximum results across all years

    Returns:
        List[str]: List of job IDs
    """
    job_ids = []
    current_year = datetime.now().year

    # Calculate movies per year if max_results is set
    total_years = end_year - start_year + 1
    movies_per_year = (
        None if max_results is None else max(1, max_results // total_years)
    )

    log.info(
        "Enqueueing year range",
        start_year=start_year,
        end_year=end_year,
        total_years=total_years,
        max_results=max_results,
        movies_per_year=movies_per_year,
    )

    for year in range(end_year, start_year - 1, -1):  # Process newest to oldest
        year_priority = priority + max(0, current_year - year)

        # For the last year, add any remaining movies from the division
        if movies_per_year is not None and year == start_year:
            remaining_movies = (
                max_results - (movies_per_year * (total_years - 1))
                if max_results is not None
                else movies_per_year
            )
            year_max_results = max(remaining_movies, movies_per_year)
        else:
            year_max_results = movies_per_year  # type: ignore

        job_id = enqueue_year_sync(
            year=year,
            language=language,
            priority=year_priority,
            max_results=year_max_results,
        )
        job_ids.append(job_id)

    return job_ids


# Scheduled task to handle retries
@django_rq.job("tmdb_sync")  # type: ignore
def retry_failed_syncs() -> None:
    """Retry failed sync jobs with exponential backoff."""
    failed_queues = TMDBSyncQueue.objects.filter(
        status="FAILED", attempts__lt=settings.TMDB_MAX_RETRY_ATTEMPTS
    )

    for queue in failed_queues:
        # Exponential backoff
        backoff = 2**queue.attempts

        if queue.last_attempt:
            wait_time = timedelta(minutes=backoff)
            if datetime.now() - queue.last_attempt < wait_time:
                continue

        enqueue_year_sync(queue.year, queue.language, priority=queue.priority + 1)

        queue.attempts += 1
        queue.save()

    log.info("Retried failed syncs", retried_count=failed_queues.count())
