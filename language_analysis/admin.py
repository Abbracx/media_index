from django.contrib import admin
from language_analysis.models import MediaAnalysisResult


@admin.register(MediaAnalysisResult)
class MediaAnalysisResultAdmin(admin.ModelAdmin[MediaAnalysisResult]):
    autocomplete_fields = ["movie", "subtitle"]
    exclude = ["lexical_analysis"]

    def get_queryset(self, request):  # type: ignore
        return super().get_queryset(request).select_related("movie")

    raw_id_fields = ("movie",)
