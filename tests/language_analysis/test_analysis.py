import pytest
from unittest.mock import patch
from tqdm import asyncio
from language_analysis.analysis import LanguageAnalysisService
from language_analysis.models import MediaAnalysisResult
from language_analysis.processor.schema import (
    LinguisticProfile,
    ConceptOccurrence,
    ConceptProfile,
    ConceptType,
    NumberAndRatio,
)



@pytest.fixture
def linguistic_analysis_profile() -> LinguisticProfile:
    """Creates a complete mock LinguisticProfile object."""
    concept_occurrences = [
        ConceptOccurrence(context="He likes to run fast", start_char=12, end_char=15),
        ConceptOccurrence(context="He was running fast", start_char=8, end_char=15),
    ]

    concept_profiles = [
        ConceptProfile(
            concept="run",
            num_occurrences=5,
            examples=concept_occurrences,
            difficulty=0.5,
        )
    ]

    pos_stats = {
        "NOUN": NumberAndRatio(number=10, ratio=0.5),
        "VERB": NumberAndRatio(number=5, ratio=0.25),
    }

    return LinguisticProfile(
        analysis_version="1.0",
        concepts={ConceptType.WORD: concept_profiles},
        pos_stats=pos_stats,
        sentences_count=3,
        sentences_avg_length=15.0,
        difficulty=0.75,
    )


class TestLanguageAnalysisService:
    """Test suite for LanguageAnalysisService."""

    @pytest.mark.django_db
    def test_process_text_returns_linguistic_profile(
        self, mocker, linguistic_analysis_profile
    ):
        # Arrange
        text = "Sample text for analysis"
        media_type = "movie"
        original_language = "en"

        mock_processor = mocker.Mock()

        mock_linguistic_profile = mocker.Mock(return_value=linguistic_analysis_profile)
        mock_processor.process.return_value = mock_linguistic_profile.return_value

        mocker.patch(
            "language_analysis.analysis.LinguisticProcessorSingleton.get_instance",
            return_value=mock_processor,
        )
        mocker.patch("language_analysis.analysis.LinguisticProcessorSingleton.cleanup")

        service = LanguageAnalysisService()

        # Act
        result = service.process_text(text, media_type, original_language)

        # Assert
        assert isinstance(result, LinguisticProfile)

        assert result.analysis_version == "1.0"
        assert isinstance(result.concepts, dict)
        assert isinstance(result.pos_stats, dict)
        assert 0 <= result.difficulty <= 1
        assert result == mock_linguistic_profile.return_value
        mock_processor.process.assert_called_once_with(text)


    @pytest.mark.django_db
    def test_store_analysis_result_creates_media_analysis_result( self, linguistic_analysis_profile, movie, subtitle):
        '''Store analysis result with valid movie and subtitle data'''
        # Arrange
       
        service = LanguageAnalysisService()

        # Act
        result = service.store_analysis_result(
            movie, linguistic_analysis_profile, subtitle
        )

        # Assert
        assert  isinstance(result, MediaAnalysisResult)
        assert result.movie == movie
        assert result.version == "1.0"
        assert result.is_latest == True
      

    @pytest.mark.django_db
    def test_store_analysis_result_marks_previous_as_not_latest(
        self, linguistic_analysis_profile, movie, subtitle
    ):
        '''Mark previous analyses as not latest when storing new result'''

        # Arrange
        service = LanguageAnalysisService()

        # Act
        result_1 = service.store_analysis_result(
            movie, linguistic_analysis_profile, subtitle
        )

        result_2 = service.store_analysis_result(
            movie, linguistic_analysis_profile, subtitle
        )

        # Assert
        assert result_1.is_latest is True
        assert result_2.is_latest is True

       
        false_result_1 = MediaAnalysisResult.objects.filter(movie=movie, is_latest=False).first()

        assert false_result_1.movie == result_2.movie
        assert false_result_1.subtitle == result_2.subtitle
        assert false_result_1.is_latest != result_2.is_latest
        assert false_result_1.is_latest is False
        assert result_2.is_latest is True

  