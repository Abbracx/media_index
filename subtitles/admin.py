from django.contrib import admin
from django.db.models import QuerySet

from subtitles.models import MovieSubtitle


@admin.register(MovieSubtitle)
class MovieSubtitleAdmin(admin.ModelAdmin[MovieSubtitle]):
    list_display = [
        "id",
        "movie",
        "subtitle_format",
        "language",
        "processing_status",
        "is_active",
    ]
    list_display_links = ["id", "movie"]
    list_editable = ["processing_status"]
    ordering = ["processing_status"]
    autocomplete_fields = ["movie"]
    search_fields = ["movie__title", "movie__tmdb_id"]

    raw_id_fields = ("movie",)

    def get_queryset(self, request):  # type: ignore
        return super().get_queryset(request).select_related("movie")
