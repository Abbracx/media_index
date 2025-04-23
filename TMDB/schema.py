from ninja import Schema
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from datetime import date, datetime
from typing import Optional, Any, Self


class TMDBMovieResponse(BaseModel):

    tmdb_id: int = Field(..., alias="id")  # Maps TMDB 'id' to our 'tmdb_id'
    title: str
    original_title: str
    overview: str
    release_date: date | None = None
    poster_path: str | None = None
    backdrop_path: str | None = None
    genres: list[str] = []
    runtime: int | None = None
    vote_average: float
    vote_count: int
    original_language: str
    author: str | None = None

    @property
    def poster_url(self) -> Optional[str]:
        if self.poster_path:
            return f"https://image.tmdb.org/t/p/original{self.poster_path}"
        return None

    @property
    def backdrop_url(self) -> Optional[str]:
        if self.backdrop_path:
            return f"https://image.tmdb.org/t/p/original{self.backdrop_path}"
        return None

    @field_validator("genres", mode="before")
    @classmethod
    def extract_genre_names(cls, v: Any) -> list[str]:
        """Extract genre names from TMDB genre objects."""
        if not v:
            return []

        try:
            return [genre.name for genre in v]
        except AttributeError:
            if isinstance(v[0], dict):
                return [genre["name"] for genre in v]
            return v  # type: ignore


class MovieResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    tmdb_id: int
    title: str
    original_title: str
    overview: str
    release_date: date
    poster_path: str | None = None
    backdrop_path: str | None = None
    genres: list[str] = []
    runtime: int | None = None
    vote_average: float
    vote_count: int
    original_language: str


class SyncYearRequest(BaseModel):
    """Schema for single year sync request."""

    year: int
    language: str = "en"
    max_results: int | None = 100

    @model_validator(mode="after")
    def validate_year(self) -> Self:
        current_year = datetime.now().year
        if self.year < 1900 or self.year > current_year:
            raise ValueError(f"Year must be between 1900 and {current_year}")
        return self


class SyncYearRangeRequest(BaseModel):
    """Schema for year range sync request."""

    start_year: int
    end_year: int
    language: str = "en"
    max_results: int | None = 100

    @model_validator(mode="after")
    def validate_years(self) -> Self:
        current_year = datetime.now().year
        if self.start_year < 1900 or self.start_year > current_year:
            raise ValueError(f"Start year must be between 1900 and {current_year}")
        if self.end_year < self.start_year:
            raise ValueError("End year must be greater than or equal to start year")
        if self.end_year > current_year:
            raise ValueError(f"End year cannot be greater than {current_year}")
        return self


class SyncResponse(BaseModel):
    """Schema for sync job response."""

    status: str = "success"
    data: dict[str, Any]


class PaginatedMovieResponse(Schema):
    data: list[dict[str, Any]]
    total: int
    page: int
    total_pages: int
    has_next: bool
    has_previous: bool


class MovieSearchResult(BaseModel):
    kind: str = Field(default="movie")
    id: str
    thumbnail_url: str | None
    image_url: str | None
    title: str
    year: int | None
    difficulty: float | None
    author: str | None
    tags: list[str] = Field(default_factory=list)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=50)
    search_session_id: str


class SearchResult(BaseModel):
    """
    Top-level search response matching client format.
    """

    media: list[dict[str, Any]]
    request_timestamp: datetime | None = None
