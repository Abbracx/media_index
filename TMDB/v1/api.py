from http import HTTPStatus
from typing import Any, Annotated
from urllib.request import Request
from asyncio import Task

import structlog
from django.http import HttpRequest
from ninja import Router, Query
from ninja.responses import Response

from TMDB.models import Movie
from TMDB.services.movie_search import HybridMovieSearch
from TMDB.schema import (
    MovieResponse,
    SyncResponse,
    SyncYearRequest,
    SyncYearRangeRequest,
    SearchResult,
)
from media_index.errors import RESTError
from TMDB.tasks import enqueue_year_sync, enqueue_year_range

log: structlog.BoundLogger = structlog.get_logger(__name__)

router = Router(tags=["Media"])


# Track active searches by client and session
_active_searches: dict[tuple[str, str], Task[SearchResult]] = {}


@router.get("/get/{movie_id}", response=MovieResponse)
def get_movie_details(request: Request, movie_id: str) -> MovieResponse:
    """Get detailed information about a specific movie."""
    log.info("Movie details requested", movie_id=movie_id)
    try:
        movie = Movie.objects.get(tmdb_id=movie_id)
        movie_data = MovieResponse.model_validate(movie)
        log.info("Movie details retrieved", movie_id=movie_id, title=movie.title)
        return movie_data
    except Movie.DoesNotExist:
        raise RESTError("Movie not found", status_code=HTTPStatus.NOT_FOUND)
    except Exception as e:
        log.error("Failed to fetch movie details", movie_id=movie_id, error=str(e))
        raise RESTError(
            "Failed to retrieve movie details",
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )


@router.post(
    "/movie-cache/update/year", response=SyncResponse, summary="Sync movies in a year"
)
def sync_year(request: Request, payload: SyncYearRequest) -> dict[str, Any]:
    """Trigger movies sync for a specific year with support for limiting results"""
    log.info(
        "Year sync requested",
        year=payload.year,
        language=payload.language,
        max_results=payload.max_results,
    )
    try:
        job_id = enqueue_year_sync(
            year=payload.year,
            language=payload.language,
            max_results=payload.max_results if payload.max_results != 0 else None,
        )

        log.info(
            "Year sync job queued",
            job_id=job_id,
            year=payload.year,
            language=payload.language,
        )

        return {
            "status": "success",
            "data": {
                "job_id": job_id,
                "year": payload.year,
                "language": payload.language,
                "max_results": payload.max_results,
            },
        }
    except Exception as e:
        log.error(
            "Failed to enqueue year sync",
            year=payload.year,
            error=str(e),
            exc_info=True,
        )
        raise RESTError(
            message="Failed to enqueue sync job",
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )


@router.post(
    "/movie-cache/update/year-range",
    response=SyncResponse,
    summary="Sync movies for specified year range",
)
def sync_year_range(request: Request, payload: SyncYearRangeRequest) -> dict[str, Any]:
    """Trigger sync for a range of years."""
    log.info(
        "Year range sync requested",
        start_year=payload.start_year,
        end_year=payload.end_year,
        language=payload.language,
        max_results=payload.max_results,
    )
    try:
        job_ids = enqueue_year_range(
            start_year=payload.start_year,
            end_year=payload.end_year,
            language=payload.language,
            max_results=payload.max_results if payload.max_results != 0 else None,
        )

        log.info(
            "Year range sync jobs queued",
            job_count=len(job_ids),
            start_year=payload.start_year,
            end_year=payload.end_year,
            language=payload.language,
        )

        return {
            "status": "success",
            "data": {
                "job_ids": job_ids,
                "start_year": payload.start_year,
                "end_year": payload.end_year,
                "language": payload.language,
                "max_results": payload.max_results,
                "total_years": len(job_ids),
            },
        }
    except Exception as e:
        log.error(
            "Failed to enqueue year range sync",
            start_year=payload.start_year,
            end_year=payload.end_year,
            error=str(e),
            exc_info=True,
        )
        raise RESTError(
            message="Failed to enqueue sync jobs",
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )


@router.get(
    "/movie-cache/update/{job_id}",
    response={200: dict[str, Any]},
    summary="Get status of processed movies",
)
def get_sync_status(request: Request, job_id: str) -> dict[str, Any]:
    """Fetch job status"""
    log.info("Job status requested", job_id=job_id)
    try:
        from django_rq.queues import get_queue

        queue = get_queue("tmdb_sync")
        job = queue.fetch_job(job_id)

        if not job:
            log.warning("Job not found", job_id=job_id)
            raise RESTError(message="Job not found", status_code=HTTPStatus.NOT_FOUND)

        status_data = {
            "id": job.id,
            "status": job.get_status().name,
            "enqueued_at": job.enqueued_at.isoformat() if job.enqueued_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "ended_at": job.ended_at.isoformat() if job.ended_at else None,
            "meta": job.meta or {},
        }

        log.info(
            "Job status retrieved",
            job_id=job_id,
            status=status_data["status"],
            enqueued_at=status_data["enqueued_at"],
        )

        return {"status": "success", "data": status_data}
    except RESTError:
        raise
    except Exception as e:
        log.error("Failed to fetch job status", job_id=job_id, error=str(e))
        raise RESTError(
            message="Failed to fetch job status",
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )


@router.get("/suggest")
def search_suggestions(
    request: HttpRequest, query: Annotated[str, Query(min_length=3, max_length=50)]
) -> Response:
    try:
        result = HybridMovieSearch.search(query)
        return Response(result, status=HTTPStatus.OK)
    except Exception as e:
        log.error("Search failed", error=str(e), exc_info=True)
        raise RESTError(str(e))
