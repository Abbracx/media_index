from datetime import datetime

import structlog
from subtitles.models import MovieSubtitle
from subtitles.services.subtitle_processor import SubtitleProcessor

log: structlog.BoundLogger = structlog.get_logger(__name__)

from typing import Callable, TypeVar, Any, cast
from django_rq import job

# Define a type variable for the function
F = TypeVar("F", bound=Callable[..., Any])


def typed_job(queue_name: str, timeout: int) -> Callable[[F], F]:
    return cast(Callable[[F], F], job(queue_name, timeout=timeout))


@typed_job("subtitles", timeout=28800)
def process_unprocessed_subtitles(max_subtitles: int = 0) -> None:
    """Background job to process unprocessed subtitles"""
    log.info(
        "Starting background subtitle processing job",
        max_subtitles=max_subtitles,
        function="process_unprocessed_subtitles",
    )

    try:
        # Run async processing in new event loop
        _process_unprocessed_subtitles(max_subtitles)
        return

    except Exception as e:
        log.error(
            "Subtitle processing job failed",
            max_subtitles=max_subtitles,
            error=str(e),
            function="process_unprocessed_subtitles",
            exc_info=True,
        )
        return


def _process_unprocessed_subtitles(
    max_subtitles: int = 0,
    batch_size: int = 30,
    max_batches: int = 0,
) -> None:
    """Core async function for batch subtitle processing"""
    log.info(
        "Starting batch subtitle processing",
        max_subtitles=max_subtitles,
        function="_process_unprocessed_subtitles",
    )

    processor = SubtitleProcessor()
    stats: dict[str, int | float] = {
        "started_at": datetime.now().timestamp(),
        "completed_at": 0,
        "total_processed": 0,
        "successful": 0,
        "failed": 0,
        "total_processing_time": 0,
        "batches_processed": 0,
    }

    try:
        while True:
            # Check if we've hit max batches
            if stats["batches_processed"] >= max_batches:
                log.info(
                    "Reached maximum batch limit",
                    max_batches=max_batches,
                    total_processed=stats["total_processed"],
                )
                break

            batch: list[MovieSubtitle] = processor.get_unprocessed_subtitles(
                limit=max_subtitles
            )

            # No more subtitles to process
            if not batch:
                log.info(
                    "No more subtitles to process",
                    total_processed=stats["total_processed"],
                )
                break

            # Process this batch
            for subtitle in batch:
                result = processor.process_subtitle(subtitle)
                stats["total_processed"] += 1
                if result["status"] == "success":
                    stats["successful"] += 1
                else:
                    stats["failed"] += 1

            stats["batches_processed"] += 1

            log.info(
                "Completed batch",
                batch_number=stats["batches_processed"],
                batch_size=len(batch),
                total_processed=stats["total_processed"],
            )

        stats["completed_at"] = datetime.now().timestamp()
        duration = stats["completed_at"] - stats["started_at"]

        log.info(
            "Completed subtitle processing",
            total_processed=stats["total_processed"],
            successful=stats["successful"],
            failed=stats["failed"],
            batches=stats["batches_processed"],
            duration_seconds=duration,
        )

    except Exception as e:
        log.error(
            "Batch processing failed",
            error=str(e),
            stats=stats,
            function="_process_unprocessed_subtitles",
            exc_info=True,
        )
        raise
