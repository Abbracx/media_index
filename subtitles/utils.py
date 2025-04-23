from asgiref.sync import async_to_sync

from TMDB.models import Movie
from subtitles.models import MovieSubtitle
from subtitles.services.storage import SubtitleStorageService


def get_active_subtitle(movie: Movie) -> MovieSubtitle:
    """Retrieve the active, unprocessed subtitle for the given movie."""
    subtitle = MovieSubtitle.objects.filter(
        movie=movie, is_active=True, subtitle_is_processed=False
    ).first()
    if not subtitle:
        raise ValueError(f"No active subtitles found for movie ID {movie.tmdb_id}")
    return subtitle


def fetch_subtitle_content(
    subtitle: MovieSubtitle, storage_service: SubtitleStorageService
) -> str:
    """Fetch the raw subtitle content from storage."""
    subtitle_content = async_to_sync(storage_service.get_subtitle)(subtitle.id)
    return subtitle_content.getvalue().decode("utf-8")


def mark_subtitle_as_processed(subtitle: MovieSubtitle) -> bool:
    """Mark the subtitle as processed."""
    subtitle.subtitle_is_processed = True
    subtitle.save()
    return subtitle.subtitle_is_processed
