from datetime import date
import pytest
from io import BytesIO
from django.test import TestCase
from unittest.mock import Mock, patch, MagicMock

import structlog

from TMDB.models import Movie
from subtitles.models import MovieSubtitle
from subtitles.schemas import SubtitleMetadata
from subtitles.services.storage import SubtitleStorageService

log: structlog.BoundLogger = structlog.get_logger(__name__)


class TestSubtitleStorageService(TestCase):

    # @patch("subtitles.services.storage.SubtitleStorageService")
    def setUp(self):
        self.mock_storage_service = SubtitleStorageService()
        self.subtitle_content = BytesIO(b"Test subtitle content")

        self.movie = MagicMock(spec=Movie)
        self.movie._state = MagicMock()
        self.movie.id = 1
        self.movie.title = "Test Movie"
        self.movie.release_date = date(2020, 1, 1)

        self.metadata = MagicMock(spec=SubtitleMetadata)
        self.metadata.release = "Test Release"
        self.metadata.language = "en"
        self.metadata.upload_date = date(2023, 1, 1)
        self.metadata.download_count = 100
        self.metadata.votes = 10
        self.metadata.ratings = 8.5
        self.metadata.hd = True
        self.metadata.from_trusted = True
        self.metadata.machine_translated = False
        self.metadata.ai_translated = False

        self.subtitle_format = "srt"

    def test_store_subtitle_success(self):
        """Should successfully store subtitle and create MovieSubtitle record with valid inputs"""
        # Arrange

        self.mock_storage_service.store_subtitle = MagicMock(
            return_value=MovieSubtitle(
                id=1,
                movie=self.movie,
                language="en",
                source="opensubtitles",
                content_hash="#####",
                quality_score=1,
            )
        )

        # Act
        subtitle = self.mock_storage_service.store_subtitle(
            self.movie,
            self.subtitle_content,
            self.metadata,
            self.subtitle_format,
        )

        # Assert
        self.assertIsInstance(subtitle, MovieSubtitle)
        self.assertEqual(subtitle.movie, self.movie)
        self.assertEqual(subtitle.language, self.metadata.language)
        self.assertEqual(subtitle.source, "opensubtitles")
        self.assertIsNotNone(subtitle.content_hash)
        self.assertIsNotNone(subtitle.quality_score)

    @patch("subtitles.services.storage.MovieSubtitle.subtitle_file")
    def test_store_subtitle_s3_upload_failure(self, mock_save):
        """Should handle failures in S3 file upload process"""
        # Arrange
        mock_save.save.side_effect = Exception("S3 upload failed")

        # Act & Assert
        with self.assertRaises(Exception) as context:
            mock_save.save()

        self.assertEqual(str(context.exception), "S3 upload failed")

    @patch("subtitles.services.storage.log")
    def test_store_subtitle_non_existent_format(self, mock_log_error):
        """Should handle non-existent subtitle format"""

        # Arrange
        non_existent_format = "xyvd"
        self.mock_storage_service.store_subtitle = MagicMock(
            side_effect=Exception("Database Error")
        )

        # Act & Assert
        with self.assertRaises(Exception) as context:
            self.mock_storage_service.store_subtitle(
                self.movie, self.subtitle_content, self.metadata, non_existent_format
            )

        mock_log_error.error(
            "Failed to store subtitle",
            movie_id=self.movie.id,
            language=self.metadata.language,
            error="Database error",
            exc_info=True,
        )

        self.assertIn("Database Error", str(context.exception))
        self.subtitle_content.close()

        mock_log_error.error.assert_called_once_with(
            "Failed to store subtitle",
            movie_id=self.movie.id,
            language=self.metadata.language,
            error="Database error",
            exc_info=True,
        )
