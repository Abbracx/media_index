import pytest
import asyncio
from datetime import datetime, timedelta
import os
from typing import Optional

from TMDB.services.tmdb_service import (
    TMDBService,
)

# Skip all tests if no API key is available
pytestmark = pytest.mark.skipif(
    not os.getenv("TMDB_AI_KEY"), reason="TMDB_API_KEY environment variable not set"
)


@pytest.fixture  # type: ignore
def api_key() -> Optional[str]:
    return os.getenv("TMDB_API_KEY")


@pytest.fixture  # type: ignore
def client(api_key: Optional[str]) -> TMDBService:
    if api_key is None:
        pytest.fail("TMDB_API_KEY must be set for these tests to run")
    return TMDBService(api_key=api_key)


class TestTMDBIntegration:

    @pytest.mark.asyncio  # type: ignore
    async def test_fetch_recent_movies(self, client: TMDBService) -> None:
        """Test fetching movies from current year."""
        current_year = datetime.now().year
        movies = []
        async for movie in client.get_movies_by_year(current_year, max_results=5):
            movies.append(movie)

        assert len(movies) > 0
        for movie in movies:
            assert movie.release_date.year == current_year
            assert movie.title
            assert movie.tmdb_id > 0

    @pytest.mark.asyncio  # type: ignore
    async def test_fetch_movie_details(self, client: TMDBService) -> None:
        """Test fetching specific movie details (Fight Club)."""
        movie = await client.get_movie_details(550)
        assert movie.tmdb_id == 550
        assert movie.title == "Fight Club"
        assert movie.release_date.year == 1999
        assert movie.vote_count > 0

    @pytest.mark.asyncio  # type: ignore
    async def test_rate_limiting(self, client: TMDBService) -> None:
        """Test rate limiting with real API."""
        start_time = datetime.now()

        # Make multiple requests quickly
        movies = []
        async for movie in client.get_movies_by_year(2023, max_results=50):
            movies.append(movie)

        duration = (datetime.now() - start_time).total_seconds()
        requests_per_second = len(movies) / duration

        # Should not exceed rate limit
        assert requests_per_second <= 50

    @pytest.mark.asyncio  # type: ignore
    async def test_language_support(self, client: TMDBService) -> None:
        """Test fetching movies in different languages."""
        languages = ["en", "es", "fr"]

        for lang in languages:
            movies = []
            async for movie in client.get_movies_by_year(
                2023, language=lang, max_results=1
            ):
                movies.append(movie)
                assert movies[0].original_language == lang
            print(movies)

    # Skip for now cause it's resource intensive
    @pytest.mark.skip  # type: ignore
    @pytest.mark.asyncio  # type: ignore
    async def test_error_recovery(self, client: TMDBService) -> None:
        """Test recovery from API errors."""
        # Force some errors by making too many requests
        tasks = []
        for _ in range(100):
            tasks.append(client.get_movie_details(550))

        # Should handle rate limits and eventually succeed
        results = await asyncio.gather(*tasks, return_exceptions=True)
        successful = [r for r in results if not isinstance(r, Exception)]
        assert len(successful) > 0

    # Skip for now. Resource intensive
    @pytest.mark.skip  # type: ignore
    @pytest.mark.asyncio  # type: ignore
    async def test_long_running_fetch(self, client: TMDBService) -> None:
        """Test longer running fetch operation."""
        movies = []
        start_time = datetime.now()

        async for movie in client.get_movies_by_year(2023, max_results=200):
            movies.append(movie)
            if (datetime.now() - start_time) > timedelta(minutes=5):
                break

        assert len(movies) > 0
        assert client.stats.failed_movies < client.stats.processed_movies * 0.1
