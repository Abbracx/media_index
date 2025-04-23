from io import BytesIO
import pytest
from pytest_factoryboy import register
from .factories import (
    MediaAnalysisResultFactory,
    MovieFactory,
    MovieSubtitleFactory,
)
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection

register(MediaAnalysisResultFactory)
register(MovieFactory)
register(MovieSubtitleFactory)

@pytest.fixture(scope='session', autouse=True)
def setup_test_database(django_db_blocker):
    with django_db_blocker.unblock():
        with connection.cursor() as cursor:
            cursor.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm;')
            cursor.execute('CREATE EXTENSION IF NOT EXISTS unaccent;')

@pytest.fixture
def subtitle_file():
    """Create a mock subtitle file."""
    subtitle_file = SimpleUploadedFile(
        "test_subtitle.srt", b"Test subtitle content", content_type="text/plain"
    )
    return subtitle_file


@pytest.fixture
def subtitle_content():
    """Create a mock subtitle content."""
    return BytesIO(b"Test subtitle content")


@pytest.fixture
def content():
    return {
        "subtitle_id": "123",
        "language": "en",
        "upload_date": "2023-01-01T00:00:00Z",
        "release": "1.0",
        "slug": "example-slug",
        "source": "manual",
        "uploader": {"name": "Manual Upload", "rank": "user"},
        "feature_details": {"feature_id": 1, "feature_type": "Movie", "title": "Test Movie"},
        "related_links": [],
        "files": [],
    }


@pytest.fixture
def movie(db, movie_factory):
    return movie_factory.create()


@pytest.fixture
def subtitle(db, movie_subtitle_factory):
    return movie_subtitle_factory.create()

@pytest.fixture
def media_analysis_result(db, media_analysis_result_factory):
    return media_analysis_result_factory.create()


@pytest.fixture
def language_analysis_service(mocker):
    return mocker.patch("language_analysis.v1.api.LanguageAnalysisService")