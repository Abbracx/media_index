from pydantic import ValidationError
import pytest
from django.test import TestCase
from ninja.testing import TestClient, TestAsyncClient
from media_index.errors import RESTError
from subtitles.services.storage import SubtitleStorageService
from subtitles.v1.api import router

from subtitles.models import MovieSubtitle
from datetime import date, datetime
from io import BytesIO
from django.core.files.uploadedfile import SimpleUploadedFile
from subtitles.models import MovieSubtitle
from subtitles.schemas import (
    SubtitleMetadata,
    SubtitleDownloadRequest,
)

from TMDB.models import Movie

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock
from subtitles.tasks import download_missing_subtitles


@pytest.mark.django_db
class TestListMoviesNeedingSubtitles(TestCase):
    def setUp(self):
        self.client = TestClient(router)

    def test_list_movies_needing_subtitles_correct_count(self):
        """Should return the correct number of movies when there are movies without subtitles"""

        # Create test movies
        movie_1 = Movie.objects.create(
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

        movie_2 = Movie.objects.create(
            tmdb_id=103,
            latest_analysis_id=None,
            title="Interstellar",
            original_title="Interstellar",
            language="en",
            original_language="en",
            release_date=date(2014, 11, 7),
            genres=["Adventure", "Drama", "Sci-Fi"],
            runtime=169,
            overview="A team of explorers travel through a wormhole in space in an attempt to ensure humanity's survival.",
            poster_url="https://example.com/poster/interstellar.jpg",
            backdrop_url="https://example.com/backdrop/interstellar.jpg",
            vote_average=8.6,
            vote_count=18000,
            difficulty=0.6,
            author="Christopher Nolan",
        )

        # Create a subtitle for one movie
        MovieSubtitle.objects.create(
            movie=movie_1, language="en", subtitle_is_processed=True, is_active=True
        )

        # Make the request
        response = self.client.get(
            "/media/missing-subtitles?page=1&limit=10&language=en"
        )

        # Assert the response
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["data"]) == 1
        assert [movie["tmdb_id"] for movie in data["data"]] == [103]

    def test_list_movies_needing_subtitles_all_processed(self):
        """Should return an empty list when all movies have processed subtitles"""

        # Create test movies
        movie_1 = Movie.objects.create(
            tmdb_id=101,
            latest_analysis_id=None,
            title="Inception",
            original_title="Inception",
            language="en",
            original_language="en",
            release_date=date(2010, 7, 16),
            genres=["Action", "Sci-Fi", "Thriller"],
            runtime=148,
            overview="A thief who steals corporate secrets through the use of dream-sharing technology is given the inverse task of planting an idea into the mind of a CEO.",
            poster_url="https://example.com/poster/inception.jpg",
            backdrop_url="https://example.com/backdrop/inception.jpg",
            vote_average=8.8,
            vote_count=20000,
            difficulty=0.5,
            author="Christopher Nolan",
        )

        movie_2 = Movie.objects.create(
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

        movie_3 = Movie.objects.create(
            tmdb_id=103,
            latest_analysis_id=None,
            title="Interstellar",
            original_title="Interstellar",
            language="en",
            original_language="en",
            release_date=date(2014, 11, 7),
            genres=["Adventure", "Drama", "Sci-Fi"],
            runtime=169,
            overview="A team of explorers travel through a wormhole in space in an attempt to ensure humanity's survival.",
            poster_url="https://example.com/poster/interstellar.jpg",
            backdrop_url="https://example.com/backdrop/interstellar.jpg",
            vote_average=8.6,
            vote_count=18000,
            difficulty=0.6,
            author="Christopher Nolan",
        )

        # Create processed subtitles for all movies
        MovieSubtitle.objects.create(
            movie=movie_1, language="en", subtitle_is_processed=True, is_active=True
        )
        MovieSubtitle.objects.create(
            movie=movie_2, language="en", subtitle_is_processed=True, is_active=True
        )
        MovieSubtitle.objects.create(
            movie=movie_3, language="en", subtitle_is_processed=True, is_active=True
        )

        # Make the request
        response = self.client.get(
            "/media/missing-subtitles?page=1&limit=10&language=en"
        )

        # Assert the response
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["data"]) == 0
        assert data["has_next"] == False
        assert data["has_previous"] == False

    def test_list_movies_needing_subtitles_pagination(self):
        """Should handle pagination correctly when there are multiple pages of results"""

        # Create test movies
        for i in range(1, 26):
            Movie.objects.create(
                id=i,
                tmdb_id=100 + i,
                latest_analysis_id=None,
                title="Interstellar",
                original_title=f"Movie {i}",
                language="en",
                original_language="en",
                release_date=f"2023-01-{i:02d}",
                genres=["Adventure", "Drama", "Sci-Fi"],
                runtime=150 + i,
                overview="A team of explorers travel through a wormhole in space in an attempt to ensure humanity's survival.",
                poster_url="https://example.com/poster/interstellar.jpg",
                backdrop_url="https://example.com/backdrop/interstellar.jpg",
                vote_average=8.6,
                vote_count=18000,
                difficulty=0.6,
                author="Christopher Nolan",
            )

        # Create subtitles for some movies
        for i in range(1, 6):
            MovieSubtitle.objects.create(
                movie_id=i, language="en", subtitle_is_processed=True, is_active=True
            )

        # Make the first page request
        response = self.client.get(
            "/media/missing-subtitles?page=1&limit=10&language=en"
        )

        # Assert the first page response
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 20
        assert len(data["data"]) == 10
        assert data["page"] == 1
        assert data["total_pages"] == 2
        assert data["has_next"] == True
        assert data["has_previous"] == False
        assert [movie["tmdb_id"] for movie in data["data"]] == list(range(125, 115, -1))

        # Make the second page request
        response = self.client.get(
            "/media/missing-subtitles?page=2&limit=10&language=en"
        )

        # Assert the second page response
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 20
        assert len(data["data"]) == 10
        assert data["page"] == 2
        assert data["total_pages"] == 2
        assert data["has_next"] == False
        assert data["has_previous"] == True
        assert [movie["tmdb_id"] for movie in data["data"]] == list(range(115, 105, -1))




class TestStartMissingSubtitleDownloads(TestCase):
    def setUp(self):
        self.client = TestAsyncClient(router)  

    @pytest.mark.asyncio
    @patch("django_rq.get_queue")
    async def test_start_missing_subtitle_downloads_success(self, mock_get_queue):
        """Should successfully queue a download job with valid parameters"""
        # Arrange
        mock_queue = mock_get_queue.return_value
        mock_job = AsyncMock()
        mock_job.id = "test_job_id"
        mock_queue.enqueue.return_value = mock_job

        #Act
        params = SubtitleDownloadRequest(language="en", max_downloads=100)
        response = await self.client.post("/download/start", json=params.model_dump())

        #Assert
        mock_get_queue.assert_called_once_with("subtitles", default_timeout=28800)
        mock_queue.enqueue.assert_called_once_with(
            download_missing_subtitles, args=("en", 100), job_timeout=28800
        )

        self.assertEqual(response.json()['job_id'], "test_job_id")
        self.assertEqual(response.json()['status'], "queued")
        self.assertIsInstance(datetime.fromisoformat(response.json()['started_at']), datetime)

    @pytest.mark.asyncio
    @patch("django_rq.get_queue")
    async def test_start_missing_subtitle_downloads_max_downloads_edge_cases(self, mock_get_queue):
        """Should handle various max_downloads values, including edge cases"""

         # Arrange
        mock_queue = mock_get_queue.return_value
        mock_job = AsyncMock()
        mock_job.id = "test_job_id"
        mock_queue.enqueue.return_value = mock_job

        edge_cases = [0, 1, 100, 1000000, None]

        for max_downloads in edge_cases:

            if max_downloads is None:
                with pytest.raises(ValidationError):
                    params = SubtitleDownloadRequest(language="en", max_downloads=max_downloads)
                    await self.client.post("/download/start", json=params.model_dump())
            else:
                params = SubtitleDownloadRequest(language="en", max_downloads=max_downloads)
                response = await self.client.post("/download/start", json=params.model_dump())

                mock_get_queue.assert_called_with("subtitles", default_timeout=28800)
                mock_queue.enqueue.assert_called_with(
                    download_missing_subtitles,
                    args=("en", max_downloads),
                    job_timeout=28800,
                )

                self.assertEqual(response.json()['job_id'], "test_job_id")
                self.assertEqual(response.json()['status'], "queued")
                self.assertIsInstance(datetime.fromisoformat(response.json()['started_at']), datetime)

        self.assertEqual(mock_queue.enqueue.call_count, len(edge_cases)-1)

    @patch("django_rq.get_queue")
    async def test_start_missing_subtitle_downloads_correct_queue(self, mock_get_queue):
        """Should use the correct queue name 'subtitles' for job enqueuing"""
         # Arrange
        mock_queue = mock_get_queue.return_value
        mock_job = AsyncMock()
        mock_job.id = "test_job_id"
        mock_queue.enqueue.return_value = mock_job

        params = SubtitleDownloadRequest(language="en", max_downloads=100)

        await self.client.post("/download/start", json=params.dict())

        mock_get_queue.assert_called_once_with("subtitles", default_timeout=28800)
        mock_queue.enqueue.assert_called_once()
        self.assertEqual(mock_get_queue.call_args[0][0], "subtitles")

    @patch("django_rq.get_queue")
    async def test_start_missing_subtitle_downloads_concurrent_requests(self, mock_get_queue):
        """Should handle concurrent requests without conflicts"""

        mock_queue = mock_get_queue.return_value
        mock_job = AsyncMock()
        mock_job.id = "test_job_id"
        mock_queue.enqueue.return_value = mock_job

        params = SubtitleDownloadRequest(language="en", max_downloads=100)

        # Simulate multiple concurrent requests
        num_concurrent_requests = 5
        tasks = [
            self.client.post("/download/start", json=params.dict())
            for _ in range(num_concurrent_requests)
        ]
        responses = await asyncio.gather(*tasks)

        # Assert that each request was processed independently
        for response in responses:
            self.assertEqual(response.json()['job_id'], "test_job_id")
            self.assertEqual(response.json()['status'], "queued")
            self.assertIsInstance(datetime.fromisoformat(response.json()['started_at']), datetime)

        # Assert that the queue was called the correct number of times
        self.assertEqual(mock_get_queue.call_count, num_concurrent_requests)
        self.assertEqual(mock_queue.enqueue.call_count, num_concurrent_requests)

        # Assert that each call to enqueue had the correct arguments
        for call in mock_queue.enqueue.call_args_list:
            self.assertEqual(call[0][0], download_missing_subtitles)
            self.assertEqual(call[1]["args"], ("en", 100))
            self.assertEqual(call[1]["job_timeout"], 28800)
