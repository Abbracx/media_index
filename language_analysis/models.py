from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import JSONField

from TMDB.models import Movie
from media_index.base_model import TimeStampedUUIDModel
from subtitles.models import MovieSubtitle
from django.utils.translation import gettext_lazy as _


class MediaAnalysisResult(TimeStampedUUIDModel):
    class MediaType(models.TextChoices):
        MOVIE = "movie", _("Movie")
        BOOK = "book", _("Book")
        SONG = "song", _("SONG")

    movie = models.ForeignKey(
        Movie, on_delete=models.CASCADE, related_name="media_analysis_results"
    )
    version = models.CharField(
        max_length=50, help_text="Version of analysis function/algorithm used"
    )
    kind = models.CharField(
        max_length=10, choices=MediaType.choices, help_text="Media type"
    )
    subtitle = models.ForeignKey(
        MovieSubtitle,
        on_delete=models.DO_NOTHING,
        related_name="media_analysis_results",
        null=True,
    )
    subtitle_version = models.CharField(
        max_length=50, help_text="Track which subtitle version was analyzed"
    )
    lexical_analysis = JSONField(
        help_text="JSON containing concepts, pos_stats, sentences_count, sentences_avg_length, and difficulty"
    )
    is_latest = models.BooleanField()

    class Meta:
        indexes = [
            models.Index(fields=["movie", "version"]),
            GinIndex(fields=["lexical_analysis"]),
        ]

    def __str__(self) -> str:
        return f"{self.movie.tmdb_id}  - {self.movie.title}  - {self.kind}"
