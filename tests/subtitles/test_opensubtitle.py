import logging
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, Mock
from io import BytesIO
from datetime import datetime

from subtitles.services.opensubtitle import OpenSubtitlesService
from subtitles.schemas import SubtitleFile, SubtitleSearchResponse, SubtitleMetadata, UploaderInfo, FeatureDetails
from subtitles.services.subtitle_scoring import SubtitleQualityScorer


@pytest.fixture
def open_subtitles_service():
    return OpenSubtitlesService()


@pytest.mark.asyncio
async def test_search_and_download(open_subtitles_service):
    '''Should successfully find and download the best subtitle for a valid TMDB ID and language'''
    # Mock the search_subtitles method
    mock_subtitles = [
        SubtitleSearchResponse(
            id="123",
            type="subtitle",
            attributes=SubtitleMetadata(
                subtitle_id="123",
                language="en",
                upload_date=datetime.now(),
                uploader=UploaderInfo(name='Uploader Name', rank="1"),
                feature_details=FeatureDetails(feature_id=1, tmdb_id=12345),
                related_links=[],
                files=[SubtitleFile(file_id="456", cd_number=1, file_name="test.srt")]
            )
        )
    ]
    open_subtitles_service.search_subtitles = AsyncMock(return_value=mock_subtitles)

    # Mock the download_subtitle method
    mock_content = BytesIO(b"Subtitle content")
    mock_format = "srt"
    open_subtitles_service.download_subtitle = AsyncMock(return_value=(mock_content, mock_format))

    # Mock the SubtitleQualityScorer
    mock_scorer = MagicMock()
    mock_scorer.select_best_subtitle.return_value = mock_subtitles[0]

    # Call the method
    content, format, metadata = await open_subtitles_service.search_and_download(123, "en")

    # Assert the results
    assert isinstance(content, BytesIO)
    assert format == "srt"
    assert isinstance(metadata, SubtitleMetadata)

    # Verify method calls
    open_subtitles_service.search_subtitles.assert_called_once_with(123, "en")
    open_subtitles_service.download_subtitle.assert_called_once_with("456")

@pytest.mark.asyncio
async def test_search_and_download_logging(open_subtitles_service, caplog):
    '''Should log appropriate information at the start and end of the search and download process'''
    # Mock the search_subtitles method
    mock_subtitles = [
        SubtitleSearchResponse(
            id="123",
            type="subtitle",
            attributes=SubtitleMetadata(
                subtitle_id="123",
                language="en",
                upload_date=datetime.now(),
                uploader=UploaderInfo(name='Uploader Name', rank="1"),
                feature_details=FeatureDetails(feature_id=1, tmdb_id=12345),
                related_links=[],
                files=[SubtitleFile(file_id="456", cd_number=1, file_name="test.srt")]
            )
        )
    ]
    open_subtitles_service.search_subtitles = AsyncMock(return_value=mock_subtitles)

    # Mock the download_subtitle method
    mock_content = BytesIO(b"Subtitle content")
    mock_format = "srt"
    open_subtitles_service.download_subtitle = AsyncMock(return_value=(mock_content, mock_format))

    # Call the method
    with caplog.at_level(logging.INFO):
        await open_subtitles_service.search_and_download(123, "en")

    # Assert log messages
    assert "Searching and downloading subtitle" in caplog.text
    assert "tmdb_id:123" in caplog.text
    assert "language:en" in caplog.text
    assert "Search and download completed" in caplog.text
    assert "subtitle_id:123" in caplog.text
    assert "format:srt" in caplog.text

    # Verify method calls
    open_subtitles_service.search_subtitles.assert_called_once_with(123, "en")
    open_subtitles_service.download_subtitle.assert_called_once_with("456")

@pytest.mark.asyncio
async def test_search_and_download_no_subtitles(open_subtitles_service):
    '''Should raise an exception when no subtitles are found for the given TMDB ID and language'''
    # Mock the search_subtitles method to return an empty list
    open_subtitles_service.search_subtitles = AsyncMock(return_value=[])

    # Call the method and expect an exception
    with pytest.raises(Exception) as exc_info:
        await open_subtitles_service.search_and_download(123, "en")

    # Assert the exception message
    assert str(exc_info.value) == "No subtitles found for TMDB ID 123"

    # Verify method calls
    open_subtitles_service.search_subtitles.assert_called_once_with(123, "en")


@pytest.mark.asyncio
async def test_search_and_download_multiple_options(open_subtitles_service):
    '''Should correctly handle multiple subtitle options and select the best one using the SubtitleQualityScorer'''
    # Mock the search_subtitles method to return multiple subtitles
    mock_subtitles = [
        SubtitleSearchResponse(
            id="123",
            type="subtitle",
            attributes=SubtitleMetadata(
                subtitle_id="123",
                language="en",
                upload_date=datetime.now(),
                uploader=UploaderInfo(name='Uploader Name', rank="1"),
                feature_details=FeatureDetails(feature_id=1, tmdb_id=12345),
                related_links=[],
                files=[SubtitleFile(file_id="456", cd_number=1, file_name="test1.srt")]
            )
        ),
        SubtitleSearchResponse(
            id="789",
            type="subtitle",
            attributes=SubtitleMetadata(
                subtitle_id="789",
                language="en",
                upload_date=datetime.now(),
                uploader=UploaderInfo(name='Uploader Name', rank="1"),
                feature_details=FeatureDetails(feature_id=2, tmdb_id=54321),
                related_links=[],
                files=[SubtitleFile(file_id="101", cd_number=1, file_name="test2.srt")]
            )
        )
    ]
    open_subtitles_service.search_subtitles = AsyncMock(return_value=mock_subtitles)

    # Mock the download_subtitle method
    mock_content = BytesIO(b"Best subtitle content")
    mock_format = "srt"
    open_subtitles_service.download_subtitle = AsyncMock(return_value=(mock_content, mock_format))

    # Mock the SubtitleQualityScorer
    mock_scorer = MagicMock()
    mock_scorer.select_best_subtitle.return_value = mock_subtitles[1]
    SubtitleQualityScorer = MagicMock(return_value=mock_scorer)

    # Call the method
    content, format, metadata = await open_subtitles_service.search_and_download(789, "en")

    # Assert the results
    assert isinstance(content, BytesIO)
    assert format == "srt"
    assert isinstance(metadata, SubtitleMetadata)
    assert metadata.subtitle_id == "789"

    # Verify method calls
    open_subtitles_service.search_subtitles.assert_called_once_with(123, "en")
    open_subtitles_service.download_subtitle.assert_called_once_with("101")


@pytest.mark.asyncio
async def test_search_and_download_correct_tuple_format(open_subtitles_service):
    '''Should return the correct tuple format (BytesIO, str, SubtitleMetadata) when a subtitle is found and downloaded'''
    # Mock the search_subtitles method
    mock_subtitles = [
        SubtitleSearchResponse(
            id="123",
            type="subtitle",
            attributes=SubtitleMetadata(
                subtitle_id="123",
                language="en",
                upload_date=datetime.now(),
                uploader=UploaderInfo(name='Uploader Name', rank="1"),
                feature_details=FeatureDetails(feature_id=1, tmdb_id=12345),
                related_links=[],
                files=[SubtitleFile(file_id="456", cd_number=1, file_name="test.srt")]
            )
        )
    ]
    open_subtitles_service.search_subtitles = AsyncMock(return_value=mock_subtitles)

    # Mock the download_subtitle method
    mock_content = BytesIO(b"Subtitle content")
    mock_format = "srt"
    open_subtitles_service.download_subtitle = AsyncMock(return_value=(mock_content, mock_format))

    # Mock the SubtitleQualityScorer
    mock_scorer = MagicMock()
    mock_scorer.select_best_subtitle.return_value = mock_subtitles[0]
    SubtitleQualityScorer = MagicMock(return_value=mock_scorer)

    # Call the method
    result = await open_subtitles_service.search_and_download(123, "en")

    # Assert the result format
    assert isinstance(result, tuple)
    assert len(result) == 3
    assert isinstance(result[0], BytesIO)
    assert isinstance(result[1], str)
    assert isinstance(result[2], SubtitleMetadata)

    # Verify method calls
    open_subtitles_service.search_subtitles.assert_called_once_with(123, "en")
    open_subtitles_service.download_subtitle.assert_called_once_with("456")


@pytest.mark.asyncio
async def test_search_and_download_performance(open_subtitles_service):
    '''Should perform efficiently for large TMDB IDs or extensive subtitle searches'''
    # Mock the search_subtitles method to return a large number of subtitles
    large_subtitle_list = [
        SubtitleSearchResponse(
            id=str(i),
            type="subtitle",
            attributes=SubtitleMetadata(
                subtitle_id=str(i),
                language="en",
                upload_date=datetime.now(),
                uploader=UploaderInfo(name='Uploader Name', rank="1"),
                feature_details=FeatureDetails(feature_id=i, tmdb_id=i * 1000),
                related_links=[],
                files=[SubtitleFile(file_id=str(i * 100), cd_number=1, file_name=f"test{i}.srt")]
            )
        ) for i in range(1000)
    ]
    open_subtitles_service.search_subtitles = AsyncMock(return_value=large_subtitle_list)

    # Mock the download_subtitle method
    mock_content = BytesIO(b"Subtitle content")
    mock_format = "srt"

    # Mock the SubtitleQualityScorer
    scorer = SubtitleQualityScorer()
    scorer.select_best_subtitle = Mock(return_value=large_subtitle_list[0])

    open_subtitles_service.download_subtitle = AsyncMock(return_value=(mock_content, mock_format))

    scorer.select_best_subtitle(large_subtitle_list)

    # Measure the execution time
    start_time = time.time()
    content, format, metadata = await open_subtitles_service.search_and_download(1000, "en")
    end_time = time.time()

    # Assert the results
    assert isinstance(content, BytesIO)
    assert format == "srt"
    assert isinstance(metadata, SubtitleMetadata)

    # Check execution time (adjust the threshold as needed)
    execution_time = end_time - start_time
    assert execution_time < 2.0, f"Execution time ({execution_time:.2f}s) exceeded the threshold of 2.0s"

    # Verify method calls
    open_subtitles_service.search_subtitles.assert_called_once_with(1000, "en")
    open_subtitles_service.download_subtitle.assert_called_once_with("0")
    scorer.select_best_subtitle.assert_called_once()
