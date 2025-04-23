from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.search import SearchVectorField
from django.db import models

from media_index.base_model import TimeStampedUUIDModel


class Movie(TimeStampedUUIDModel):
    tmdb_id = models.IntegerField(unique=True)
    latest_analysis_id = models.IntegerField(unique=True, null=True)
    title = models.CharField(max_length=255)
    original_title = models.CharField(max_length=255)
    language = models.CharField(max_length=10)
    original_language = models.CharField(max_length=10)
    release_date = models.DateField()
    genres = ArrayField(
        models.CharField(max_length=50),
        default=list,
        blank=True,
    )
    runtime = models.IntegerField(null=True)
    overview = models.TextField()
    poster_url = models.URLField(max_length=500, null=True)
    backdrop_url = models.URLField(max_length=500, null=True)
    vote_average = models.DecimalField(max_digits=3, decimal_places=1)
    vote_count = models.IntegerField()
    difficulty = models.FloatField(default=0.0, null=True)
    author = models.CharField(max_length=500, blank=True)
    title_vector = SearchVectorField(null=True, editable=False)

    class Meta:
        indexes = [
            models.Index(fields=["tmdb_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} - {self.language} ({self.tmdb_id})"


class TMDBSyncQueue(TimeStampedUUIDModel):
    """Queue for tracking TMDB sync jobs."""

    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("IN_PROGRESS", "In Progress"),
        ("COMPLETED", "Completed"),
        ("FAILED", "Failed"),
    ]
    year = models.IntegerField(help_text="Year being synced")
    language = models.CharField(max_length=10, help_text="Language code (e.g., en)")
    job_id = models.CharField(max_length=100, help_text="RQ job ID")
    priority = models.IntegerField(default=0)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    attempts = models.IntegerField(default=0)
    last_attempt = models.DateTimeField(null=True)
    error_message = models.TextField(null=True, blank=True)

    movies_processed = models.IntegerField(default=0)
    movies_failed = models.IntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=["status", "priority"]),
            models.Index(fields=["year", "language"]),
        ]
