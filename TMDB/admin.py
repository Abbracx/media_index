from django.contrib import admin
from TMDB.models import Movie, TMDBSyncQueue


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin[Movie]):
    search_fields = ["original_title"]


admin.site.register(TMDBSyncQueue)
