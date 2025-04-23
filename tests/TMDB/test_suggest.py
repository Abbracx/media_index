import pytest
from http import HTTPStatus
from tests.factories import MovieFactory
from TMDB.models import Movie
from ninja.testing import TestClient
from TMDB.v1.api import router


@pytest.fixture
def suggestion_movies(db):
    movies = [
        MovieFactory(
            with_title="The Shawshank Redemption",
            vote_count=10000,
            release_date="1994-09-23",
            difficulty=1,
            author="Frank Darabont",
            genres=["Drama"],
        ),
        MovieFactory(
            high_ranking=True,
            with_title="The Dark Knight",
            release_date="2008-07-18",
            difficulty=2,
            author="Christopher Nolan",
            genres=["Action", "Crime", "Drama"],
        ),
        MovieFactory(
            low_ranking=True,
            with_title="The Dark Knight Rises",
            release_date="2012-07-20",
            difficulty=2,
            author="Christopher Nolan",
            genres=["Action", "Crime", "Drama"],
        ),
        MovieFactory(
            medium_ranking=True,
            with_title="Inception",
            release_date="2010-07-16",
            difficulty=3,
            author="Christopher Nolan",
            genres=["Action", "Sci-Fi"],
        ),
    ]
    return movies


@pytest.mark.django_db(transaction=True)
class TestMediaSuggestAPI:
    client = TestClient(router)
    base_url = "/suggest"

    def test_suggest_with_valid_prefix(self, suggestion_movies):
        """Test suggestion endpoint with valid prefix"""
        # Verify movies are in database before making request
        db_movies = Movie.objects.all()
        print(f"\nBefore API call - Movies in database: {db_movies.count()}")
        for movie in db_movies:
            print(f"- {movie.title} (ID: {movie.id}, vote_count: {movie.vote_count})")
        
        # breakpoint()

        print("\nMaking API request...")
        response = self.client.get(f"{self.base_url}?query=the")
        print(f"Response status: {response.status_code}")
        print(f"Response data: {response.json()}")

        assert response.status_code == HTTPStatus.OK
        data = response.json()

        # Verify we get results
        assert len(data["media"]) > 0, "Should return at least one result"

        # Verify all results contain 'The'
        for movie in data["media"]:
            assert (
                "the" in movie["title"].lower()
            ), f"Movie title '{movie['title']}' should contain 'the'"

        # Verify ordering by vote_count if multiple results
        if len(data["media"]) > 1:
            vote_counts = [movie.get("vote_count", 0) for movie in data["media"]]
            assert vote_counts == sorted(
                vote_counts, reverse=True
            ), "Results should be ordered by vote_count"

        assert "request_timestamp" in data

    def test_suggest_with_case_insensitive_prefix(self, suggestion_movies):
        response = self.client.get(f"{self.base_url}?query=THE")
        assert response.status_code == HTTPStatus.OK

        data = response.json()
        assert len(data["media"]) > 0, "Should return results regardless of case"
        for movie in data["media"]:
            assert "the" in movie["title"].lower()

    def test_suggest_with_empty_query(self):
        response = self.client.get(f"{self.base_url}?query=")
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

        data = response.json()
        assert "detail" in data

    def test_suggest_with_missing_query(self):
        response = self.client.get(self.base_url)
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

        data = response.json()
        assert "detail" in data

    def test_suggest_with_short_query(self):
        response = self.client.get(f"{self.base_url}?query=a")
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

        data = response.json()
        assert "detail" in data
        error_msg = str(data["detail"]).lower()
        assert any(phrase in error_msg for phrase in ["minimum length", "at least 3", "too short"])

    def test_suggest_with_no_matches(self, suggestion_movies):
        response = self.client.get(f"{self.base_url}?query=xyz")
        assert response.status_code == HTTPStatus.OK

        data = response.json()
        assert len(data["media"]) == 0
        assert "request_timestamp" in data

    def test_suggest_response_structure(self, suggestion_movies):
        response = self.client.get(f"{self.base_url}?query=inception")
        assert response.status_code == HTTPStatus.OK

        data = response.json()
        assert "media" in data
        assert "request_timestamp" in data

        if data["media"]:
            item = data["media"][0]
            assert "id" in item
            assert "title" in item
            assert "year" in item
            assert "difficulty" in item
            assert "author" in item
            assert "thumbnail_url" in item
            assert "image_url" in item
            assert "tags" in item

    @pytest.mark.parametrize(
        "query,min_expected",
        [
            ("inception", 1),
            ("shawshank", 1),
            ("nolan", 0),  # Shouldn't match author name
            ("nonexistent", 0),
        ],
    )
    def test_suggest_different_queries(self, suggestion_movies, query, min_expected):
        response = self.client.get(f"{self.base_url}?query={query}")
        assert response.status_code == HTTPStatus.OK

        data = response.json()
        assert (
            len(data["media"]) >= min_expected
        ), f"Should find at least {min_expected} matches for '{query}'"
