from datetime import date
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from django.test import TestCase
from TMDB.models import Movie
from subtitles.models import MovieSubtitle


class TestSubtitleDownloadService(TestCase):

    @patch("subtitles.services.subtitle_download.OpenSubtitlesService")
    @patch("subtitles.services.subtitle_download.SubtitleStorageService")
    @patch(
        "subtitles.services.subtitle_download.SubtitleDownloadService"
    ) 
    def setUp(
        self, MockSubtitleDownload, MockSubtitleStorageService, MockOpenSubtitlesService
    ):
        self.mock_subtitle_service = MockOpenSubtitlesService
        self.mock_storage_service = MockSubtitleStorageService
        self.mock_download_service = MockSubtitleDownload

    @patch(
        "subtitles.services.subtitle_download.SubtitleDownloadService.get_movies_without_subtitles"
    )
    def test_get_movies_without_subtitles_empty_queryset(self, mock_get_movies):
        """Should return an empty QuerySet when there are no movies without subtitles"""

        mock_get_movies.return_value = []

        # Create a movie with an active subtitle
        movie = Movie.objects.create(
            tmdb_id=102,
            latest_analysis_id=None,
            title="The Matrix",
            original_title="The Matrix",
            language="en",
            original_language="en",
            release_date=date(1999, 3, 31),
            genres=["Action", "Sci-Fi"],
            runtime=136,
            overview="A computer hacker learns from mysterious rebels about the true nature of his reality and his role in the war against its controllers.",
            poster_url="https://example.com/poster/matrix.jpg",
            backdrop_url="https://example.com/backdrop/matrix.jpg",
            vote_average=8.7,
            vote_count=15000,
            difficulty=0.7,
            author="The Wachowskis",
        )

        MovieSubtitle.objects.create(movie=movie, language="en", is_active=True)

        # Call the method
        result = self.mock_download_service.get_movies_without_subtitles()

        # Assert that the result is an empty QuerySet
        self.assertQuerySetEqual(result, [])

    def test_get_movies_without_subtitles(self):
        """Should return an empty QuerySet when there are movies without subtitles"""

        # Mock the queryset that returns movies without subtitles
        self.mock_download_service.get_movies_without_subtitles = MagicMock(
            return_value=[Movie(id=1, title="Test Movie")]
        )

        movies = self.mock_download_service.get_movies_without_subtitles(
            language="en", limit=5
        )

        # Assertions
        self.assertEqual(len(movies), 1)
        self.assertEqual(movies[0].title, "Test Movie")

    @pytest.mark.asyncio
    async def test_download_and_save_subtitles(self):
        """Should download and save subtitles for a movie"""

        # Setup the mock return value
        self.mock_download_service.download_and_save_subtitles = AsyncMock(
            return_value={"status": "success", "movie_id": 1, "subtitle_id": 1}
        )

        # Create a mock Movie object
        movie = MagicMock(spec=Movie)
        movie.id = 1
        movie.tmdb_id = 102
        movie.title = "The Matrix"
        movie.language = "en"

        # Mock the subtitle service's behavior
        self.mock_subtitle_service.search_and_download = AsyncMock(
            return_value=(b"subtitle content", "srt", {"key": "value"})
        )
        self.mock_storage_service.store_subtitle.return_value = MagicMock(id=1)

        result = await self.mock_download_service.download_and_save_subtitles(
            movie, language="en"
        )

        # Assertions
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["movie_id"], 1)
        self.assertEqual(result["subtitle_id"], 1)

    @pytest.mark.asyncio
    async def test_download_and_save_subtitles_failure(self):
        """Should return an error message when downloading subtitles fails"""

        # Create a mock Movie object
        movie = MagicMock(spec=Movie)
        movie.id = 1
        movie.tmdb_id = 102
        movie.title = "The Matrix"
        movie.language = "en"

        self.mock_download_service.download_and_save_subtitles = AsyncMock(
            return_value={"status": "error", "movie_id": 1, "subtitle_id": 1}
        )

        # Simulate a download failure
        self.mock_subtitle_service.search_and_download = AsyncMock(
            side_effect=Exception("Download failed")
        )

        # Call the method and handle the exception

        result = await self.mock_download_service.download_and_save_subtitles(
            movie, language="en"
        )

        # Assertions
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["movie_id"], movie.id)