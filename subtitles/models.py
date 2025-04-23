from django.db import models
import structlog

from TMDB.models import Movie
from media_index.base_model import TimeStampedUUIDModel
from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage

log: structlog.BoundLogger = structlog.get_logger(__name__)


class SubtitleS3Storage(S3Boto3Storage):  # type: ignore
    """Custom S3 storage for subtitles"""

    def __init__(self) -> None:
        super().__init__(**settings.STORAGES["subtitles"]["OPTIONS"])  # type: ignore


class MovieSubtitle(TimeStampedUUIDModel):

    class SubtitleFormat(models.TextChoices):
        SRT = "srt", "SubRip"
        VTT = "vtt", "WebVTT"
        ASS = "ass", "Advanced SubStation Alpha"
        SSA = "ssa", "SubStation Alpha"

    class ProcessingStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"

    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="subtitles")
    subtitle_file = models.FileField(
        upload_to="",
        storage=SubtitleS3Storage(),
        max_length=500,
        help_text="Stored subtitle file",
    )
    source = models.CharField(
        max_length=100, help_text="Source of subtitle (e.g. 'opensubtitles', 'manual')"
    )
    subtitle_format = models.CharField(
        max_length=3, choices=SubtitleFormat.choices, help_text="Subtitle file format"
    )
    version = models.CharField(
        max_length=100,
    )
    language = models.CharField(
        max_length=10,
    )
    content_hash = models.CharField(
        max_length=64,
    )
    quality_score = models.FloatField(
        null=True, help_text="Calculated quality score (0-1)"
    )
    metadata = models.JSONField(
        default=dict,
    )
    is_active = models.BooleanField(
        default=True,
    )

    # Replace is_processed with processing_status
    processing_status = models.CharField(
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.PENDING,
        help_text="Current processing status of the subtitle",
    )
    processing_error = models.TextField(
        null=True, blank=True, help_text="Error message if processing failed"
    )
    processing_attempts = models.IntegerField(
        default=0, help_text="Number of processing attempts"
    )
    last_processing_attempt = models.DateTimeField(
        null=True, blank=True, help_text="Timestamp of last processing attempt"
    )
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when processing completed successfully",
    )
    subtitle_is_processed = models.BooleanField(
        default=False, help_text="Subtitle text as processed"
    )

    class Meta:
        indexes = [
            models.Index(fields=["movie", "language", "is_active"]),
            models.Index(fields=["movie", "version"]),
            models.Index(fields=["content_hash"]),
            models.Index(fields=["quality_score"]),
            models.Index(fields=["processing_status"]),
            models.Index(fields=["language", "processing_status", "is_active"]),
            models.Index(fields=["last_processing_attempt"]),
        ]
        unique_together = [("movie", "language", "content_hash")]

    def __str__(self) -> str:
        return f"{self.movie.title} - {self.language} ({self.subtitle_format})"

    @property
    def is_processed(self) -> bool:
        """Maintain backward compatibility with is_processed field"""
        return self.processing_status == self.ProcessingStatus.PROCESSED
