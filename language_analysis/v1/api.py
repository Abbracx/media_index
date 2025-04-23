from http import HTTPStatus
import django_rq
import structlog
from django.http import HttpRequest
from ninja import Router

from TMDB.models import Movie
from language_analysis.analysis import (
    LanguageAnalysisService,
)
from language_analysis.models import MediaAnalysisResult
from language_analysis.processor.schema import (
    ConceptOccurrence,
    ConceptProfile,
    ConceptType,
    LinguisticProfile,
    NumberAndRatio,
)
from language_analysis.schemas import (
    ProcessTextRequest,
    ProcessTextResponse,
    ErrorResponse,
)
from language_analysis.tasks import process_unprocessed_subtitles
from subtitles.models import MovieSubtitle
from subtitles.utils import (
    mark_subtitle_as_processed,
    fetch_subtitle_content,
    get_active_subtitle,
)
from media_index.errors import RESTError
from subtitles.services.storage import SubtitleStorageService


log: structlog.BoundLogger = structlog.get_logger(__name__)
router = Router(tags=["Linguistic Processing"])


@router.post(
    "/process",
    response={200: ProcessTextResponse, 400: ErrorResponse},
    summary="Process text and generate linguistic analysis",
    description="Analyze text content and return linguistic statistics",
)
def process_text(
    request: HttpRequest,
    payload: ProcessTextRequest,
) -> ProcessTextResponse:
    """
    Process text and return linguistic analysis.

    Args:
        request:
        payload: Text content and processing parameters
    """
    log.info(
        "Processing text analysis request",
        text_length=len(payload.text),
        type=payload.type,
    )

    try:

        language_service = LanguageAnalysisService()

        analysis: LinguisticProfile = language_service.process_text(
            text=payload.text,
            media_type=payload.type,
            original_language=payload.original_language,
        )

        log.info(
            "Analysis Results",
            version=analysis.analysis_version,
            concepts=analysis.concepts,
            pos_stats=analysis.pos_stats,
            sentences_count=analysis.sentences_count,
            sentences_avg_length=analysis.sentences_avg_length,
            difficulty=analysis.difficulty,
        )

        response_data = LinguisticProfile(
            analysis_version=analysis.analysis_version,
            concepts={
                concept_type: [
                    ConceptProfile(
                        concept=profile.concept,
                        num_occurrences=profile.num_occurrences,
                        examples=[
                            ConceptOccurrence(
                                context=example.context,
                                start_char=example.start_char,
                                end_char=example.end_char,
                                time=example.time,
                            )
                            for example in profile.examples
                        ],
                        difficulty=profile.difficulty,
                    )
                    for profile in profiles
                ]
                for concept_type, profiles in analysis.concepts.items()
            },
            pos_stats={
                pos_type: NumberAndRatio(
                    number=stats.number,
                    ratio=stats.ratio,
                )
                for pos_type, stats in analysis.pos_stats.items()
            },
            sentences_count=analysis.sentences_count,
            sentences_avg_length=analysis.sentences_avg_length,
            duration=analysis.duration,
            time_ranges=analysis.time_ranges,
            difficulty=analysis.difficulty,
        )

        return ProcessTextResponse(
            status="success",
            data=response_data,
        )

    except Exception as e:
        log.error(
            "Text analysis failed",
            error=str(e),
            exc_info=True,
        )
        raise RESTError(
            message="Failed to process text analysis",
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )


@router.get(
    "/media/movie/{movie_id}",
    response={200: ProcessTextResponse, 400: ErrorResponse, 500: ErrorResponse},
    summary="Get linguistic analysis for a movie",
    description="Retrieve stored linguistic analysis for a specific movie",
)
async def get_movie_linguistic_data(
    request: HttpRequest,
    movie_id: int,
    version: str | None = None,
) -> ProcessTextResponse:
    """
    Retrieve linguistic analysis data for a movie.

    Args:
        movie_id: ID of the movie to retrieve analysis for
        version: Optional specific version of analysis to retrieve
                If not provided, returns the latest version

    Returns:
        ProcessTextResponse containing the linguistic analysis data

    Raises:
        RESTError: With 404 if movie or analysis doesn't exist
        RESTError: With 500 if retrieval fails
    """
    log.info(
        "Retrieving movie linguistic data",
        movie_id=movie_id,
        analysis_version=version,
    )

    try:
        movie = await Movie.objects.aget(tmdb_id=movie_id)

        query = MediaAnalysisResult.objects.filter(
            movie=movie,
            kind=MediaAnalysisResult.MediaType.MOVIE,
        )

        if version:
            query = query.filter(version=version)
        else:
            query = query.filter(is_latest=True)

        analysis = await query.afirst()

        if not analysis:
            raise RESTError(
                message=(
                    f"No linguistic analysis found for movie {movie_id}"
                    f"{f' with version {version}' if version else ''}"
                ),
                status_code=HTTPStatus.NOT_FOUND,
            )

        lexical_data = analysis.lexical_analysis

        log.info(
            "Successfully retrieved movie linguistic data",
            movie_id=movie_id,
            analysis_id=analysis.id,
            version=analysis.version,
        )

        return ProcessTextResponse(
            status="success",
            data=lexical_data,
        )

    except Movie.DoesNotExist:
        log.warning(
            "Movie not found",
            movie_id=movie_id,
        )
        raise RESTError(
            message=f"Movie with ID {movie_id} not found",
            status_code=HTTPStatus.NOT_FOUND,
        )

    except Exception as e:
        log.error(
            "Failed to retrieve movie linguistic data",
            movie_id=movie_id,
            version=version,
            error=str(e),
            exc_info=True,
        )
        raise RESTError(
            message="Failed to retrieve linguistic analysis",
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )


@router.post(
    "/media/{tmdb_id}/process/subtitle",
    summary="Process and store movie subtitle",
    description="Analyzes a given movie subtitle and stores the results",
)
def process_and_persist_subtitle_analysis(
    request: HttpRequest, tmdb_id: str
) -> LinguisticProfile:
    log.info("Enqueuing subtitle processing job for movie ID: %s", tmdb_id)

    try:
        language_service = LanguageAnalysisService()
        storage_service = SubtitleStorageService()

        movie = Movie.objects.get(tmdb_id=tmdb_id)

        subtitle = get_active_subtitle(movie)

        subtitle_text = fetch_subtitle_content(subtitle, storage_service)

        """Analyze the subtitle text and generate a linguistic analysis."""

        linguistic_analysis = language_service.process_text(
            text=subtitle_text,
            media_type="movie",
            original_language=subtitle.language,
        )

        language_service.store_analysis_result(
            movie=movie,
            subtitle=subtitle,
            linguistic_analysis=linguistic_analysis,
        )

        is_processed = mark_subtitle_as_processed(subtitle)

        if not is_processed:
            log.info("Subtitle processing failed for movie ID: %s", tmdb_id)

        log.info("Successfully processed subtitle for movie ID: %s", tmdb_id)

        return linguistic_analysis

    except Movie.DoesNotExist:
        log.warning("Movie not found with ID %s", tmdb_id)
        raise
    except Exception as e:
        log.error("Error processing subtitle for movie ID %s: %s", tmdb_id, str(e))
        raise


@router.post("/process/bulk")
async def start_bulk_processing(
    request: HttpRequest, max_subtitles: int | None = None
) -> dict[str, str | int]:
    """Start bulk processing of unprocessed subtitles"""
    log.info(
        "Received batch processing request",
        max_subtitles=max_subtitles,
        function="start_bulk_processing",
    )

    try:
        # Get count of unprocessed subtitles
        total_unprocessed = await MovieSubtitle.objects.filter(
            is_active=True, subtitle_is_processed=False
        ).acount()

        if total_unprocessed == 0:
            log.info(
                "No unprocessed subtitles found, skipping",
                function="start_batch_processing",
            )
            return {"status": "skipped", "message": "No unprocessed subtitles found"}

        log.info(
            "Found unprocessed subtitles",
            total_unprocessed=total_unprocessed,
            max_subtitles=max_subtitles,
            function="start_batch_processing",
        )

        queue = django_rq.get_queue("subtitles", default_timeout=28800)
        # Queue processing job
        job = queue.enqueue(
            process_unprocessed_subtitles,
            kwargs={
                "max_subtitles": max_subtitles,
            },
        )

        log.info(
            "Queued batch subtitle processing",
            job_id=job.id,
            total_unprocessed=total_unprocessed,
            max_subtitles=max_subtitles,
            function="start_batch_processing",
        )

        return {
            "status": "queued",
            "job_id": job.id,
            "total_unprocessed": total_unprocessed,
            "max_subtitles": max_subtitles or total_unprocessed,
        }

    except Exception as e:
        log.error(
            "Failed to start batch processing",
            error=str(e),
            max_subtitles=max_subtitles,
            function="start_batch_processing",
            exc_info=True,
        )
        raise RESTError(f"Failed to start batch processing: {str(e)}")
