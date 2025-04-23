import pytest
from unittest.mock import AsyncMock, patch
from typing import Dict, Any

from TMDB.services.tmdb_service import (
    TMDBService,
    TMDBRequestError,
)


@pytest.fixture  # type: ignore
def api_key() -> str:
    return "Any_Key"


@pytest.fixture  # type: ignore
def movie_data() -> Dict[str, Any]:
    """Sample movie data fixture."""
    return {
        "id": 550,
        "title": "Fight Club",
        "original_title": "Fight Club",
        "overview": "A test overview",
        "release_date": "1999-10-15",
        "poster_path": "/poster.jpg",
        "backdrop_path": "/backdrop.jpg",
        "runtime": 139,
        "vote_average": 8.4,
        "vote_count": 24601,
        "original_language": "en",
    }


@pytest.fixture  # type: ignore
def movie_list_response(movie_data: Dict[str, Any]) -> Dict[str, Any]:
    """Movie list response fixture."""
    return {"page": 1, "results": [movie_data], "total_pages": 2, "total_results": 40}


class TestTMDBClient:
    """Test suite for TMDBClient."""

    @pytest.mark.asyncio  # type: ignore
    @patch("aiohttp.ClientSession.request")
    async def test_get_movies_by_year(
        self,
        mock_request: AsyncMock,
        api_key: str,
        movie_data: Dict[str, Any],
        movie_list_response: Dict[str, Any],
    ) -> None:
        """Test fetching movies by year."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(side_effect=[movie_list_response, movie_data])
        mock_request.return_value.__aenter__.return_value = mock_response

        client = TMDBService(api_key=api_key)
        movies = []
        async for movie in client.get_movies_by_year(2023, max_results=1):
            movies.append(movie)

        assert len(movies) == 1
        assert movies[0].tmdb_id == movie_data["id"]
        assert movies[0].title == movie_data["title"]

    @pytest.mark.asyncio  # type: ignore
    @patch("aiohttp.ClientSession.request")
    async def test_empty_responses(self, mock_request: AsyncMock, api_key: str) -> None:
        """Test handling of empty response data."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "page": 1,
                "results": [],
                "total_pages": 0,
                "total_results": 0,
            }
        )
        mock_request.return_value.__aenter__.return_value = mock_response

        client = TMDBService(api_key=api_key)
        movies = []
        async for movie in client.get_movies_by_year(2023):
            movies.append(movie)

        assert len(movies) == 0
        assert client.stats.processed_movies == 0

    @pytest.mark.asyncio  # type: ignore
    @patch("aiohttp.ClientSession.request")
    async def test_movie_details(
        self, mock_request: AsyncMock, api_key: str, movie_data: Dict[str, Any]
    ) -> None:
        """Test fetching movie details."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=movie_data)
        mock_request.return_value.__aenter__.return_value = mock_response

        client = TMDBService(api_key=api_key)
        movie = await client.get_movie_details(550)

        assert movie.tmdb_id == movie_data["id"]
        assert movie.title == movie_data["title"]

    @pytest.mark.asyncio  # type: ignore
    @patch("aiohttp.ClientSession.request")
    async def test_invalid_release_dates(
        self, mock_request: AsyncMock, api_key: str, movie_data: Dict[str, Any]
    ) -> None:
        """Test handling of invalid release dates."""
        invalid_data = movie_data.copy()
        invalid_data["release_date"] = "invalid-date"

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            side_effect=[
                {
                    "page": 1,
                    "results": [invalid_data],
                    "total_pages": 1,
                    "total_results": 1,
                },
                invalid_data,
            ]
        )
        mock_request.return_value.__aenter__.return_value = mock_response

        client = TMDBService(api_key=api_key)
        with pytest.raises(TMDBRequestError):
            async for _ in client.get_movies_by_year(2023, max_results=1):
                pass

    @pytest.mark.asyncio  # type: ignore
    @patch("aiohttp.ClientSession.request")
    async def test_pagination(
        self, mock_request: AsyncMock, api_key: str, movie_data: Dict[str, Any]
    ) -> None:
        """Test handling of paginated responses."""
        # Setup mock responses for both pages and movie details
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            side_effect=[
                {
                    "page": 1,
                    "results": [movie_data],
                    "total_pages": 2,
                    "total_results": 2,
                },
                movie_data,
                {
                    "page": 2,
                    "results": [movie_data],
                    "total_pages": 2,
                    "total_results": 2,
                },
                movie_data,
            ]
        )
        mock_request.return_value.__aenter__.return_value = mock_response

        client = TMDBService(api_key=api_key)
        movies = []
        async for movie in client.get_movies_by_year(2023, max_results=2):
            movies.append(movie)

        assert len(movies) == 2
        assert all(movie.tmdb_id == movie_data["id"] for movie in movies)
