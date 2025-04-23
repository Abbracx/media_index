from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import AsyncIterator, Any, Callable
import structlog
from themoviedb import aioTMDb
import aiohttp
import asyncio

from TMDB.schema import TMDBMovieResponse

log: structlog.BoundLogger = structlog.get_logger(__name__)


class TMDBConfigError(Exception):
    """Raised when TMDB configuration is invalid or missing."""

    pass


class TMDBRequestError(Exception):
    """Raised when TMDB API request fails."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        **log_context: dict[str, Any],
    ) -> None:

        super().__init__(message)
        self.message = message
        self.status_code = status_code
        log.error(
            "TMDB API request failed",
            error_message=message,
            status_code=status_code,
            **(log_context or {}),
            exc_info=True,
        )


@dataclass
class RateLimiter:
    """Rate limiter with token bucket algorithm and backoff handling."""

    # https://developer.themoviedb.org/docs/rate-limiting
    # Default to 40 requests/sec (below 50 for safety margin)
    requests_per_second: int = 40

    # Track request timestamps for rolling window
    _request_timestamps: list[datetime] = field(default_factory=list)

    # Backoff tracking
    _backoff_until: datetime | None = None
    _consecutive_429s: int = 0
    _base_backoff: float = 2.0  # seconds

    async def acquire(self) -> None:
        """
        Acquire a rate limit token, waiting if necessary.

        Implements:
        1. Token bucket rate limiting
        2. Exponential backoff on 429s
        3. Rolling window request tracking
        """
        now = datetime.now()
        # Check if we're in backoff period
        if self._backoff_until and now < self._backoff_until:
            sleep_time = (self._backoff_until - now).total_seconds()
            log.info("In backoff period, waiting", sleep_seconds=sleep_time)
            await asyncio.sleep(sleep_time)

        # Clean old timestamps outside rolling window
        window_start = now - timedelta(seconds=1)
        self._request_timestamps = [
            ts for ts in self._request_timestamps if ts > window_start
        ]

        # If at rate limit, wait until oldest request expires
        while len(self._request_timestamps) >= self.requests_per_second:
            sleep_time = (self._request_timestamps[0] - window_start).total_seconds()
            log.debug("Rate limit reached, waiting", sleep_seconds=sleep_time)
            await asyncio.sleep(sleep_time)

            # Update window after waiting
            now = datetime.now()
            window_start = now - timedelta(seconds=1)
            self._request_timestamps = [
                ts for ts in self._request_timestamps if ts > window_start
            ]

        # Add current request
        self._request_timestamps.append(now)

    def handle_429(self) -> Any:
        """
        Handle a 429 response with exponential backoff.

        Returns:
            float: Number of seconds to back off
        """
        self._consecutive_429s += 1
        backoff_seconds = self._base_backoff * (2 ** (self._consecutive_429s - 1))

        # Cap maximum backoff at 5 minutes
        backoff_seconds = min(backoff_seconds, 300)

        self._backoff_until = datetime.now() + timedelta(seconds=backoff_seconds)

        log.warning(
            "Received 429, implementing backoff",
            consecutive_429s=self._consecutive_429s,
            backoff_seconds=backoff_seconds,
        )

        return backoff_seconds

    def handle_success(self) -> None:
        """Reset backoff tracking after successful request."""
        self._consecutive_429s = 0
        self._backoff_until = None


@dataclass
class TMDBStats:
    """Statistics for TMDB API usage and results."""

    total_movies: int = 0
    processed_movies: int = 0
    failed_movies: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None

    @property
    def duration(self) -> float | None:
        """Calculate duration in seconds if finished."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None


class TMDBService:
    """Client for fetching movie data from TMDB API by year."""

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize TMDB client with optional API key."""
        self.api_key = api_key
        if not self.api_key:
            raise TMDBConfigError("TMDB API key not provided")

        self.tmdb = aioTMDb(key=self.api_key)
        self.stats = TMDBStats()
        self.rate_limiter = RateLimiter()

        log.debug("Initialized TMDB client")

    async def _make_request(self, request_func: Callable[[], Any]) -> Any:
        """
        Make a rate-limited API request with retry logic.
        Args:
            request_func: Async function that makes the actual API request
        Returns:
            API response
        Raises:
            TMDBRequestError: If request fails after retries
        """
        max_retries = 5
        attempt = 0

        while attempt < max_retries:
            try:
                # Wait for rate limit token
                await self.rate_limiter.acquire()

                response = await request_func()
                self.rate_limiter.handle_success()

                return response

            except aiohttp.ClientResponseError as e:
                if e.status == 429:
                    backoff = self.rate_limiter.handle_429()
                    if attempt < max_retries - 1:
                        await asyncio.sleep(backoff)
                        attempt += 1
                        continue

                raise TMDBRequestError(
                    f"API request failed: {str(e)}",
                    status_code=getattr(e, "status", None),
                    log_context={
                        "attempt": attempt + 1,
                        "url": getattr(e, "url", None),
                    },
                ) from e

            except Exception as e:

                raise TMDBRequestError(
                    f"Unexpected error: {str(e)}",
                    log_context={"attempt": attempt + 1},
                ) from e

    async def get_movies_by_year(
        self,
        year: int,
        include_adult: bool = False,
        language: str = "en",
        max_results: int | None = 100,
    ) -> AsyncIterator[TMDBMovieResponse]:
        """Fetch movies by year, handling pagination with date ranges if needed."""
        if not isinstance(year, int) or year < 1900 or year > datetime.now().year:
            raise ValueError(f"Invalid year: {year}")

        processed_count = 0
        # TMBD API throws an error from page 500 hence I split the year in ranges
        date_ranges = [
            (f"{year}-01-01", f"{year}-03-31"),
            (f"{year}-04-01", f"{year}-06-30"),
            (f"{year}-07-01", f"{year}-09-30"),
            (f"{year}-10-01", f"{year}-12-31"),
        ]

        log.info(
            "Starting movie fetch with quarterly ranges",
            year=year,
            language=language,
            max_results=max_results,
        )

        for start_date, end_date in date_ranges:
            log.info("Processing date range", start_date=start_date, end_date=end_date)
            page = 1
            total_pages = 1

            while page <= total_pages:
                log.info(
                    "Fetching page",
                    page=page,
                    total_pages=total_pages,
                    period=f"{start_date} to {end_date}",
                )
                try:
                    discover_response = await self._make_request(
                        lambda: self.tmdb.discover().movie(
                            primary_release_year=year,
                            release_date__gte=start_date,
                            release_date__lte=end_date,
                            include_adult=include_adult,
                            with_original_language=language,
                            page=page,
                        )
                    )

                    if page == 1:
                        total_pages = discover_response.total_pages
                        log.info(
                            "Discovered movies for period",
                            year=year,
                            start_date=start_date,
                            end_date=end_date,
                            total_pages=total_pages,
                            total_movies=discover_response.total_results,
                            language=language,
                        )

                    for movie_data in discover_response.results:
                        try:
                            if (
                                max_results is not None
                                and processed_count >= max_results
                            ):
                                log.info(
                                    "Reached max results limit",
                                    processed_count=processed_count,
                                    max_results=max_results,
                                )
                                return

                            details = await self._make_request(
                                lambda: self.tmdb.movie(movie_data.id).details(
                                    append_to_response="credits"
                                )
                            )

                            directors = [
                                member.name
                                for member in details.credits.crew
                                if member.job.lower() == "director"
                            ]

                            movie_dict = asdict(details)
                            movie_dict["author"] = (
                                ", ".join(directors) if directors else ""
                            )

                            movie = TMDBMovieResponse.model_validate(movie_dict)
                            self.stats.processed_movies += 1
                            processed_count += 1
                            yield movie

                            log.debug(
                                "Fetched movie",
                                movie_id=movie_data.id,
                                title=movie.title,
                                processed_count=processed_count,
                            )

                        except Exception as e:
                            self.stats.failed_movies += 1
                            log.error(
                                "Failed to process movie",
                                movie_id=movie_data.id,
                                error=str(e),
                                exc_info=True,
                            )
                            continue

                    log.info(
                        "Completed page",
                        page=page,
                        total_pages=total_pages,
                        processed_this_page=len(discover_response.results),
                    )
                    page += 1

                except Exception as e:
                    log.error(
                        "Failed to fetch page",
                        year=year,
                        page=page,
                        start_date=start_date,
                        end_date=end_date,
                        error=str(e),
                        exc_info=True,
                    )
                    page += 1
                    continue

    async def get_movie_details(self, movie_id: int) -> TMDBMovieResponse:
        """
        Get detailed information for a specific movie.

        Args:
            movie_id: TMDB movie ID

        Returns:
            MovieResponse with full movie details

        Raises:
            TMDBRequestError: If API request fails
        """
        try:
            details = await self.tmdb.movie(movie_id).details()
            return TMDBMovieResponse.model_validate(details.__dict__)

        except Exception as e:
            raise TMDBRequestError(
                f"Failed to fetch movie {movie_id}: {str(e)}",
                log_context={"movie_id": movie_id},
            ) from e

    async def get_all_movies(
        self,
        start_year: int | None = None,
        end_year: int | None = None,
        include_adult: bool = False,
    ) -> AsyncIterator[TMDBMovieResponse]:
        """
        Fetch all movies between start_year and end_year (inclusive).

        Args:
            start_year: Starting year (defaults to 1900)
            end_year: Ending year (defaults to current year)
            include_adult: Whether to include adult movies

        Yields:
            MovieResponse objects for each movie
        """
        current_year = datetime.now().year
        start_year = start_year or 1900
        end_year = min(end_year or current_year, current_year)

        if start_year > end_year:
            raise ValueError(f"start_year ({start_year}) > end_year ({end_year})")

        log.info(
            "Starting full movie fetch",
            start_year=start_year,
            end_year=end_year,
        )

        for year in range(start_year, end_year + 1):
            async for movie in self.get_movies_by_year(year, include_adult):
                yield movie

        log.info(
            "Completed full movie fetch",
            total_processed=self.stats.processed_movies,
            total_failed=self.stats.failed_movies,
            duration_seconds=self.stats.duration,
        )
