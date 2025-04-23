import time
import pytest
from ninja.testing import TestClient
from language_analysis.v1.api import router
from language_analysis.schemas import ProcessTextRequest
from language_analysis.processor.schema import (
    ConceptOccurrence,
    ConceptProfile,
    ConceptType,
    LinguisticProfile,
    NumberAndRatio,
)
from media_index.errors import RESTError


# Test Process Language Endpoints API
class TestProcessLanguageEndpoint:

    @pytest.fixture
    def client(self):
        return TestClient(router)
    
    def test_process_text_success(self, client: TestClient, language_analysis_service):
        # Arrange
        mock_analysis = LinguisticProfile(
            analysis_version="1.0",
            concepts={
                ConceptType.PHRASAL_VERB: [
                    ConceptProfile(
                        concept="John",
                        num_occurrences=2,
                        examples=[
                            ConceptOccurrence(
                                context="John went to the store",
                                start_char=0,
                                end_char=4,
                                time=None,
                            )
                        ],
                        difficulty=0.5,
                    )
                ]
            },
            pos_stats={
                "NOUN": NumberAndRatio(number=5, ratio=0.2),
                "VERB": NumberAndRatio(number=3, ratio=0.12),
            },
            sentences_count=3,
            sentences_avg_length=10.5,
            duration=None,
            time_ranges=None,
            difficulty=0.6,
        )
        language_analysis_service.return_value.process_text.return_value = mock_analysis

        payload = ProcessTextRequest(
            text="Sample text for analysis",
            type="movie",
            original_language="en",
        )

        # Act
        response = client.post("/process", json=payload.dict())

        # Assert
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert response.json()["data"]["analysis_version"] == "1.0"
        assert response.json()["data"]["pos_stats"]["NOUN"]["number"] == 5
        assert response.json()["data"]["sentences_count"] == 3
        assert response.json()["data"]["difficulty"] == 0.6

        language_analysis_service.return_value.process_text.assert_called_once_with(
            text="Sample text for analysis",
            media_type="movie",
            original_language="en",
        )


    def test_process_text_empty_input(self, client: TestClient, language_analysis_service):

        # Act
        with pytest.raises(ValueError) as exc_info:
            payload = ProcessTextRequest(
            text="",
            type="movie",
            original_language="en",
        )
            client.post("/process", json=payload.dict())

        # Assert
        language_analysis_service.return_value.process_text.assert_not_called()



    def test_process_text_unsupported_media_type(self, client: TestClient, language_analysis_service):
        # Arrange
        language_analysis_service.return_value.process_text.side_effect = ValueError(
            "Unsupported media type"
        )

        payload = ProcessTextRequest(
            text="Sample text for analysis",
            type="unsupported_type",
            original_language="en",
        )

        # Act
        with pytest.raises(RESTError):
            response = client.post("/process", json=payload.dict())

            # Assert
            assert response.status_code == 500
            assert response.json()["detail"] == "Failed to process text analysis"

        language_analysis_service.return_value.process_text.assert_called_once_with(
            text="Sample text for analysis",
            media_type="unsupported_type",
            original_language="en",
        )


    def test_process_text_long_input(self, client: TestClient, language_analysis_service):
        # Arrange
        long_text = "This is a very long text. " * 10000  # 250,000 characters
        linguistic_profile = LinguisticProfile(
            analysis_version="1.0",
            concepts={},
            pos_stats={},
            sentences_count=10000,
            sentences_avg_length=25,
            duration=None,
            time_ranges=None,
            difficulty=0.5,
        )
        language_analysis_service.return_value.process_text.return_value = linguistic_profile

        payload = ProcessTextRequest(
            text=long_text,
            type="book",
            original_language="en",
        )

        # Act
        start_time = time.time()
        response = client.post("/process", json=payload.dict())
        end_time = time.time()

        # Assert
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert response.json()["data"]["sentences_count"] == 10000
        assert response.json()["data"]["sentences_avg_length"] == 25
        assert response.json()["data"]["difficulty"] == 0.5

        processing_time = end_time - start_time
        assert (
            processing_time < 5
        ), f"Processing time ({processing_time:.2f}s) exceeded 5 seconds"

        language_analysis_service.return_value.process_text.assert_called_once_with(
            text=long_text,
            media_type="book",
            original_language="en",
        )


    def test_process_text_multiple_languages(self, client: TestClient, language_analysis_service):
        # Arrange
        linguistic_profile = LinguisticProfile(
            analysis_version="1.1",
            concepts={
                ConceptType.WORD: [
                    ConceptProfile(
                        concept="John",
                        num_occurrences=1,
                        examples=[
                            ConceptOccurrence(
                                context="John speaks English and Spanish",
                                start_char=0,
                                end_char=4,
                                time=None,
                            )
                        ],
                        difficulty=0.3,
                    )
                ],
                ConceptType.IDIOM: [
                    ConceptProfile(
                        concept="English",
                        num_occurrences=1,
                        examples=[
                            ConceptOccurrence(
                                context="John speaks English and Spanish",
                                start_char=12,
                                end_char=19,
                                time=None,
                            )
                        ],
                        difficulty=0.2,
                    ),
                    ConceptProfile(
                        concept="Spanish",
                        num_occurrences=1,
                        examples=[
                            ConceptOccurrence(
                                context="John speaks English and Spanish",
                                start_char=24,
                                end_char=31,
                                time=None,
                            )
                        ],
                        difficulty=0.2,
                    ),
                ],
            },
            pos_stats={
                "NOUN": NumberAndRatio(number=3, ratio=0.3),
                "VERB": NumberAndRatio(number=1, ratio=0.1),
            },
            sentences_count=1,
            sentences_avg_length=6.0,
            duration=None,
            time_ranges=None,
            difficulty=0.4,
        )
        language_analysis_service.return_value.process_text.return_value = linguistic_profile

        payload = ProcessTextRequest(
            text="John speaks English and Spanish",
            type="subtitle",
            original_language="en",
        )

        # Act
        response = client.post("/process", json=payload.dict())

        # Assert
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert response.json()["data"]["analysis_version"] == "1.1"
        # assert len(response.json()["data"]["concepts"]["PERSON"]) == 1
        # assert len(response.json()["data"]["concepts"]["LANGUAGE"]) == 2
        assert response.json()["data"]["pos_stats"]["NOUN"]["number"] == 3
        assert response.json()["data"]["sentences_count"] == 1
        assert response.json()["data"]["sentences_avg_length"] == 6.0
        assert response.json()["data"]["difficulty"] == 0.4

        language_analysis_service.return_value.process_text.assert_called_once_with(
            text="John speaks English and Spanish",
            media_type="subtitle",
            original_language="en",
        )


    def test_process_text_special_characters(self, client: TestClient, language_analysis_service):
        # Arrange
        linguistic_profile = LinguisticProfile(
            analysis_version="1.0",
            concepts={
                ConceptType.PHRASAL_VERB: [
                    ConceptProfile(
                        concept="@",
                        num_occurrences=1,
                        examples=[
                            ConceptOccurrence(
                                context="Email: user@example.com",
                                start_char=7,
                                end_char=8,
                                time=None,
                            )
                        ],
                        difficulty=0.1,
                    )
                ]
            },
            pos_stats={
                "NOUN": NumberAndRatio(number=1, ratio=0.25),
                "PUNCT": NumberAndRatio(number=3, ratio=0.75),
            },
            sentences_count=1,
            sentences_avg_length=4,
            duration=None,
            time_ranges=None,
            difficulty=0.2,
        )
        language_analysis_service.return_value.process_text.return_value = linguistic_profile

        payload = ProcessTextRequest(
            text="Email: user@example.com!",
            type="subtitle",
            original_language="en",
        )

        # Act
        response = client.post("/process", json=payload.dict())

        # Assert
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert response.json()["data"]["pos_stats"]["PUNCT"]["number"] == 3
        assert response.json()["data"]["sentences_count"] == 1
        assert response.json()["data"]["difficulty"] == 0.2

        language_analysis_service.return_value.process_text.assert_called_once_with(
            text="Email: user@example.com!",
            media_type="subtitle",
            original_language="en",
        )


    def test_process_text_consistency(self, client: TestClient, language_analysis_service):
        # Arrange
        linguistic_profile = LinguisticProfile(
            analysis_version="1.0",
            concepts={
                ConceptType.IDIOM: [
                    ConceptProfile(
                        concept="John",
                        num_occurrences=1,
                        examples=[
                            ConceptOccurrence(
                                context="John is a person",
                                start_char=0,
                                end_char=4,
                                time=None,
                            )
                        ],
                        difficulty=0.3,
                    )
                ]
            },
            pos_stats={
                "NOUN": NumberAndRatio(number=2, ratio=0.5),
                "VERB": NumberAndRatio(number=1, ratio=0.25),
            },
            sentences_count=1,
            sentences_avg_length=4.0,
            duration=None,
            time_ranges=None,
            difficulty=0.4,
        )
        language_analysis_service.return_value.process_text.return_value = linguistic_profile

        payload = ProcessTextRequest(
            text="John is a person",
            type="subtitle",
            original_language="en",
        )

        # Act
        response1 = client.post("/process", json=payload.dict())
        response2 = client.post("/process", json=payload.dict())
        response3 = client.post("/process", json=payload.dict())

        # Assert
        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response3.status_code == 200

        assert response1.json() == response2.json() == response3.json()
        assert response1.json()["data"]["analysis_version"] == "1.0"
        assert response1.json()["data"]["pos_stats"]["NOUN"]["number"] == 2
        assert response1.json()["data"]["sentences_count"] == 1
        assert response1.json()["data"]["difficulty"] == 0.4

        assert language_analysis_service.return_value.process_text.call_count == 3
        language_analysis_service.return_value.process_text.assert_called_with(
            text="John is a person",
            media_type="subtitle",
            original_language="en",
        )


    def test_process_text_high_difficulty(self, client: TestClient, language_analysis_service):
        # Arrange
        linguistic_profile = LinguisticProfile(
            analysis_version="1.0",
            concepts={
                ConceptType.WORD: [
                    ConceptProfile(
                        concept="Einstein",
                        num_occurrences=2,
                        examples=[
                            ConceptOccurrence(
                                context="Einstein's theory of relativity",
                                start_char=0,
                                end_char=8,
                                time=None,
                            )
                        ],
                        difficulty=0.9,
                    )
                ]
            },
            pos_stats={
                "NOUN": NumberAndRatio(number=10, ratio=0.2),
                "VERB": NumberAndRatio(number=5, ratio=0.1),
            },
            sentences_count=5,
            sentences_avg_length=20.0,
            duration=None,
            time_ranges=None,
            difficulty=0.85,
        )
        language_analysis_service.return_value.process_text.return_value = linguistic_profile

        payload = ProcessTextRequest(
            text="Einstein's theory of relativity revolutionized our understanding of space and time.",
            type="scientific",
            original_language="en",
        )

        # Act
        response = client.post("/process", json=payload.dict())

        # Assert
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert response.json()["data"]["analysis_version"] == "1.0"
        assert "WORD".lower() in response.json()["data"]["concepts"]
        assert response.json()["data"]["pos_stats"]["NOUN"]["number"] == 10
        assert response.json()["data"]["sentences_count"] == 5
        assert response.json()["data"]["sentences_avg_length"] == 20.0
        assert response.json()["data"]["difficulty"] == 0.85

        language_analysis_service.return_value.process_text.assert_called_once_with(
            text="Einstein's theory of relativity revolutionized our understanding of space and time.",
            media_type="scientific",
            original_language="en",
        )


    def test_process_text_concurrent_requests(self,client: TestClient, language_analysis_service):
        # Arrange
        num_requests = 10
        linguistic_profile = LinguisticProfile(
            analysis_version="1.0",
            concepts={},
            pos_stats={},
            sentences_count=5,
            sentences_avg_length=10.0,
            duration=None,
            time_ranges=None,
            difficulty=0.5,
        )
        language_analysis_service.return_value.process_text.return_value = linguistic_profile

        payload = ProcessTextRequest(
            text="Sample text for analysis",
            type="movie",
            original_language="en",
        )

        # Act
        start_time = time.time()
        responses = [
            client.post("/process", json=payload.dict()) for _ in range(num_requests)
        ]
        end_time = time.time()

        # Assert
        total_time = end_time - start_time
        avg_time_per_request = total_time / num_requests

        assert all(response.status_code == 200 for response in responses)
        assert all(response.json()["status"] == "success" for response in responses)
        assert (
            avg_time_per_request < 0.5
        ), f"Average processing time ({avg_time_per_request:.2f}s) exceeded 0.5 seconds"

        assert language_analysis_service.return_value.process_text.call_count == num_requests
        language_analysis_service.return_value.process_text.assert_called_with(
            text="Sample text for analysis",
            media_type="movie",
            original_language="en",
        )
