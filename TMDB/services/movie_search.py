from datetime import datetime
import structlog
from django.contrib.postgres.search import TrigramDistance, TrigramSimilarity
from django.db import connection
from typing import TypeVar, Any
from django.db.models.functions import Cast, Ln, Greatest

from django.db.models import Value, F, FloatField

from TMDB.models import Movie
from TMDB.schema import SearchResult

log: structlog.BoundLogger = structlog.get_logger(__name__)

T = TypeVar("T")


class HybridMovieSearch:
    """
    Hybrid search using optimized trigram and full-text search.
    """

    # Search parameters
    MIN_SEARCH_LENGTH = 3  # Min search query length
    MAX_SEARCH_LENGTH = 50  # Max search query length
    MAX_RESULTS = 10
    DISTANCE_THRESHOLD = 0.7
    FTS_THRESHOLD = 8  # Query length for FTS

    # Ranking weights
    WEIGHTS = {"fts_rank": 0.4, "trigram": 0.3, "popularity": 0.3}

    @classmethod
    def search(cls, query: str) -> SearchResult:
        try:
            if not query or len(query) < cls.MIN_SEARCH_LENGTH:
                return SearchResult(media=[], request_timestamp=datetime.now())

            query = query[: cls.MAX_SEARCH_LENGTH].strip().lower()

            # Decide search strategy based on query length
            if len(query) > cls.FTS_THRESHOLD:
                results = cls._full_text_search(query)
            else:
                results = cls._trigram_search(query)

            # Convert to response format the old way(Pydantic introduced a 25ms delay)
            movies = [
                {
                    "kind": "movie",
                    "id": str(row[0]),
                    "title": row[1],
                    "year": row[2].year if row[2] else None,
                    "difficulty": row[4],
                    "author": row[5],
                    "thumbnail_url": row[6],
                    "image_url": row[6],
                    "tags": row[7] or [],
                }
                for row in results
            ]

            log.info(
                "Search completed",
                query=query,
                results_count=len(movies),
                search_type="fts" if len(query) > cls.FTS_THRESHOLD else "trigram",
            )

            return SearchResult(media=movies, request_timestamp=datetime.now())

        except Exception as e:
            log.error("Search failed", query=query, error=str(e), exc_info=True)
            raise

    @classmethod
    def _trigram_search(cls, query: str) -> list:  # type: ignore

        return list(
            Movie.objects.annotate(distance=TrigramDistance("title", str(Value(query))))
            .annotate(
                similarity=TrigramSimilarity("title", query),
                popularity_score=cls._normalize_popularity(),
            )
            .filter(similarity__gte=0.1)
            .order_by("distance", "-vote_count")
            .values_list(
                "id",
                "title",
                "release_date",
                "vote_count",
                "difficulty",
                "author",
                "poster_url",
                "genres",
            )[: cls.MAX_RESULTS]
        )

    @classmethod
    def _full_text_search(cls, query: str) -> Any:
        sql = """
           WITH SearchResults AS (
               SELECT 
                   id, title, release_date, vote_count, difficulty,
                   author, poster_url, genres,
                   ts_rank(
                       title_vector, 
                       websearch_to_tsquery('english', %s),
                       32 /* rank normalization */
                   ) * ln(GREATEST(vote_count, 1) + 1.0) as rank_score,
                   word_similarity(lower(title), lower(%s)) as title_sim
               FROM "TMDB_movie" m
               WHERE 
                   title_vector @@ websearch_to_tsquery('english', %s)
                   OR word_similarity(lower(title), lower(%s)) > %s
           ),
           RankedResults AS (
               SELECT *,
                   GREATEST(
                       rank_score,
                       title_sim * ln(GREATEST(vote_count, 1) + 1.0)
                   ) as final_score
               FROM SearchResults
               WHERE rank_score > 0 OR title_sim > %s
           )
           SELECT * FROM RankedResults
           ORDER BY final_score DESC, vote_count DESC
           LIMIT %s;
           """

        params = (
            query,  # For ts_rank
            query,  # For word_similarity
            query,  # For websearch_to_tsquery
            query,  # For word_similarity threshold
            cls.DISTANCE_THRESHOLD,  # Similarity threshold
            cls.DISTANCE_THRESHOLD,  # Final threshold
            cls.MAX_RESULTS,  # Result limit
        )

        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()

    @staticmethod
    def _normalize_popularity() -> Cast:
        """Normalize vote count to 0-1 range."""
        return Cast(Ln(Greatest(1, F("vote_count") + 1)) / Ln(100000), FloatField())
