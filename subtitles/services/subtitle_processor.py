import time
from datetime import datetime, timedelta
from typing import Any
import structlog
from django.db import transaction
from django.utils import timezone
from django.db.models import Q
from django.db import models

from subtitles.models import MovieSubtitle
from language_analysis.analysis import LanguageAnalysisService
from subtitles.services.storage import SubtitleStorageService
from subtitles.utils import fetch_subtitle_content

log: structlog.BoundLogger = structlog.get_logger(__name__)

MAX_PROCESSING_ATTEMPTS = 10
PROCESSING_TIMEOUT = timedelta(hours=1)


class SubtitleProcessor:
    """Service for processing unprocessed subtitles"""

    def __init__(self) -> None:
        log.info("Initializing SubtitleProcessor")
        self.language_service = LanguageAnalysisService()
        self.storage_service = SubtitleStorageService()

    def get_unprocessed_subtitles(
        self,
        limit: int | None = None,
        batch_size: int = 30,
    ) -> list[MovieSubtitle]:
        """
        Get subtitles that need processing, with proper locking to prevent duplicate processing.

        Uses SELECT FOR UPDATE SKIP LOCKED to ensure only one worker processes each subtitle.
        """
        log.info("Fetching unprocessed subtitles", limit=limit)

        try:
            with transaction.atomic():
                # Get subtitles that are:
                # 1. Active and pending processing
                # 2. Failed but haven't exceeded max attempts
                # 3. Stuck in processing state for too long
                current_time = timezone.now()
                processing_timeout = current_time - PROCESSING_TIMEOUT

                queryset = (
                    MovieSubtitle.objects.select_related("movie")
                    .select_for_update(skip_locked=True)
                    .filter(
                        Q(is_active=True),
                        Q(
                            # Pending processing
                            Q(processing_status=MovieSubtitle.ProcessingStatus.PENDING)
                            |
                            # Failed but can retry
                            Q(
                                processing_status=MovieSubtitle.ProcessingStatus.FAILED,
                                processing_attempts__lt=MAX_PROCESSING_ATTEMPTS,
                            )
                            |
                            # Stuck in processing
                            Q(
                                processing_status=MovieSubtitle.ProcessingStatus.PROCESSING,
                                last_processing_attempt__lt=processing_timeout,
                            )
                        ),
                    )
                    .order_by("-movie__vote_count", "processing_attempts", "created_at")
                )

                if limit:
                    queryset = queryset[:limit]
                else:
                    queryset = queryset[:batch_size]

                # Update status to processing
                subtitles = list(queryset)
                if subtitles:
                    subtitle_ids = [s.id for s in subtitles]
                    MovieSubtitle.objects.filter(id__in=subtitle_ids).update(
                        processing_status=MovieSubtitle.ProcessingStatus.PROCESSING,
                        processing_attempts=models.F("processing_attempts") + 1,
                        last_processing_attempt=current_time,
                    )

                    log.info("Found unprocessed subtitles batch", count=len(subtitles))
                return subtitles

        except Exception as e:
            log.error(
                "Error fetching unprocessed subtitles", error=str(e), exc_info=True
            )
            raise

    def process_subtitle(self, subtitle: MovieSubtitle) -> dict[str, Any]:
        """Process a single subtitle with timing metrics and status tracking"""
        start_time = time.time()
        log.info(
            "Starting subtitle processing",
            subtitle_id=subtitle.id,
            movie_id=subtitle.movie.id,
            movie_title=subtitle.movie.title,
            language=subtitle.language,
            attempt=subtitle.processing_attempts,
        )

        processing_metrics = {
            "subtitle_id": subtitle.id,
            "movie_id": subtitle.movie.id,
            "movie_title": subtitle.movie.title,
            "language": subtitle.language,
            "started_at": datetime.now(),
            "text_length": 0,
            "processing_time": 0,
            "status": "failed",
        }

        try:
            # Fetch and process subtitle
            subtitle_text = fetch_subtitle_content(subtitle, self.storage_service)
            processing_metrics["text_length"] = len(subtitle_text)

            process_start = time.time()
            linguistic_analysis = self.language_service.process_text(
                text=subtitle_text,
                media_type="movie",
                original_language=subtitle.language,
            )
            process_end = time.time()
            processing_metrics["processing_time"] = process_end - process_start

            # Store analysis results
            self.language_service.store_analysis_result(
                movie=subtitle.movie,
                subtitle=subtitle,
                linguistic_analysis=linguistic_analysis,
            )

            # Update subtitle status
            self._mark_processed(subtitle)

            processing_metrics["status"] = "success"
            processing_metrics["completed_at"] = datetime.now()
            processing_metrics["total_time"] = time.time() - start_time

            log.info(
                "Processed subtitle successfully",
                subtitle_id=subtitle.id,
                movie_id=subtitle.movie.id,
                processing_metrics=processing_metrics,
            )

            return processing_metrics

        except Exception as e:
            processing_metrics["error"] = str(e)
            processing_metrics["completed_at"] = datetime.now()
            processing_metrics["total_time"] = time.time() - start_time

            # Update failure status
            self._mark_failed(subtitle, str(e))

            log.error(
                "Failed to process subtitle",
                subtitle_id=subtitle.id,
                movie_id=subtitle.movie.id,
                error=str(e),
                processing_metrics=processing_metrics,
                exc_info=True,
            )
            return processing_metrics

    def _mark_processed(self, subtitle: MovieSubtitle) -> None:
        """Mark subtitle as successfully processed"""
        subtitle.refresh_from_db()
        subtitle.processing_status = MovieSubtitle.ProcessingStatus.PROCESSED
        subtitle.processed_at = timezone.now()
        subtitle.save(update_fields=["processing_status", "processed_at"])

        log.info(
            "Marked subtitle as processed",
            subtitle_id=subtitle.id,
            processing_status=MovieSubtitle.ProcessingStatus.PROCESSED,
        )

    def _mark_failed(self, subtitle: MovieSubtitle, error: str) -> None:
        """Mark subtitle as failed with error message"""
        subtitle.refresh_from_db()
        subtitle.processing_status = MovieSubtitle.ProcessingStatus.FAILED
        subtitle.processing_error = error
        subtitle.save(update_fields=["processing_status", "processing_error"])
        log.info(
            "Marked subtitle as processed",
            subtitle_id=subtitle.id,
            processing_status=MovieSubtitle.ProcessingStatus.FAILED,
        )
