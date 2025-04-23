from datetime import datetime
from math import ceil
import django_rq
from asgiref.sync import sync_to_async
from django.db.models import OuterRef, Exists
from ninja import Router, Query
from ninja.files import UploadedFile
import structlog
from django.http import HttpRequest
from io import BytesIO
from TMDB.models import Movie
from TMDB.schema import PaginatedMovieResponse
from media_index.errors import RESTError
from subtitles.models import MovieSubtitle
from subtitles.schemas import (
    SubtitleUploadResponse,
    SubtitleMetadata,
    FeatureDetails,
    UploaderInfo,
    DownloadJobStatus,
    SubtitleDownloadRequest,
    SubtitleResponse,
    SubtitleListResponse,
)
from subtitles.services.opensubtitle import OpenSubtitlesService
from subtitles.services.storage import SubtitleStorageService
from subtitles.tasks import download_missing_subtitles

log: structlog.BoundLogger = structlog.get_logger(__name__)

router = Router(tags=["Subtitles"])


@router.get(
    "/media/missing-subtitles",
    response=PaginatedMovieResponse,
    summary="List movies without subtitles",
)
def list_movies_needing_subtitles(
    request: HttpRequest,
    page: int = Query(1, gt=0),  # type: ignore
    limit: int = Query(100, gt=0, le=10000),  # type: ignore
    language: str = Query("en"),  # type: ignore
) -> PaginatedMovieResponse:
    """List movies with missing subtitles"""
    log.info(
        "Listing movies needing subtitles", page=page, limit=limit, language=language
    )

    try:
        offset = (page - 1) * limit

        # Base queryset for movies needing subtitles
        processed_subtitles = MovieSubtitle.objects.filter(
            movie=OuterRef("pk"),
            language=language,
            subtitle_is_processed=True,
            is_active=True,
        )

        # Main queryset with selected fields and subtitle annotation
        base_queryset = (
            Movie.objects.annotate(has_processed_subtitle=Exists(processed_subtitles))
            .filter(has_processed_subtitle=False)
            .order_by("-vote_count", "-release_date")
            .only("id", "tmdb_id", "title", "release_date", "vote_count")
        )

        # Get total count for pagination
        total_movies = base_queryset.count()
        total_pages = ceil(total_movies / limit)

        movies = base_queryset.order_by("-vote_count", "-release_date")[
            offset : offset + limit
        ]

        # Fetch all relevant subtitles in a single query
        subtitle_map = {
            subtitle.movie_id: subtitle
            for subtitle in MovieSubtitle.objects.filter(
                movie_id__in=[m.id for m in movies], language=language
            ).all()
        }

        results = [
            {
                "id": movie.id,
                "tmdb_id": movie.tmdb_id,
                "title": movie.title,
                "release_date": movie.release_date.isoformat(),
                "vote_count": movie.vote_count,
                "has_subtitles": movie.id in subtitle_map,
                "is_processed": False,
            }
            for movie in movies
        ]

        log.info(
            "Found movies needing subtitles",
            count=len(results),
            total=total_movies,
            page=page,
            total_pages=total_pages,
        )

        return PaginatedMovieResponse(
            data=results,
            total=total_movies,
            page=page,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        )

    except Exception as e:
        log.error(
            "Failed to list movies needing subtitles", error=str(e), exc_info=True
        )
        raise RESTError(f"Failed to list movies: {str(e)}")


@router.post(
    "/media/{movie_id}/subtitle",
    response=SubtitleUploadResponse,
    summary="Upload subtitle file for a movie",
)
def upload_subtitle(
    request: HttpRequest,
    movie_id: int,
    file: UploadedFile,
    release: str = "1.0",
    language: str = Query("en"),  # type: ignore
) -> SubtitleUploadResponse:
    """Upload subtitle file for a movie"""
    log.info(
        "Processing subtitle upload",
        movie_id=movie_id,
        filename=file.name,
        language=language,
    )

    try:
        movie = Movie.objects.get(tmdb_id=movie_id)

        # Get file format
        if file.name:
            subtitle_format = file.name.split(".")[-1].lower()
        else:
            raise RESTError("File name is missing.")

        if subtitle_format not in MovieSubtitle.SubtitleFormat.values:
            raise RESTError(f"Unsupported subtitle format: {subtitle_format}")

        # Create subtitle record
        content = BytesIO(file.read())
        storage = SubtitleStorageService()

        from datetime import datetime

        metadata = SubtitleMetadata(
            subtitle_id=str(hash(content)),
            language=language,
            upload_date=datetime.utcnow(),
            release=release,
            slug="example-slug",
            uploader=UploaderInfo(name="Manual Upload", rank="user"),
            feature_details=FeatureDetails(
                feature_id=movie.tmdb_id,
                feature_type="Movie",
                title=movie.title,
                year=movie.release_date.year,
                tmdb_id=movie.tmdb_id,
            ),
            related_links=[],
            files=[],
        )

        subtitle = storage.store_subtitle(
            movie=movie,
            subtitle_content=content,
            metadata=metadata,
            subtitle_format=subtitle_format,
        )

        log.info(
            "Subtitle upload successful", subtitle_id=subtitle.id, movie_id=movie_id
        )

        return SubtitleUploadResponse(
            id=subtitle.id,
            file_path=subtitle.subtitle_file.name,
            language=language,
            quality_score=subtitle.quality_score,
        )

    except Exception as e:
        log.error(
            "Subtitle upload failed", movie_id=movie_id, error=str(e), exc_info=True
        )
        raise RESTError(f"Failed to upload subtitle: {str(e)}")


@router.post(
    "/media/{movie_id}/subtitles/sync/debug",
    response=SubtitleResponse,
    summary="Fetch movie subtitle(Synchronous)",
)
async def sync_movie_subtitle_debug(
    request: HttpRequest, movie_id: int, language: str = Query("en")  # type: ignore
) -> SubtitleResponse:
    """Finds the best subtitle for a movie and saves it to the db"""
    try:
        movie = await Movie.objects.aget(tmdb_id=movie_id)

        log.info(
            "Starting direct subtitle sync",
            movie_id=movie_id,
            tmdb_id=movie.tmdb_id,
            language=language,
        )

        client = OpenSubtitlesService()
        storage = SubtitleStorageService()

        movie = await Movie.objects.aget(tmdb_id=movie_id)

        # Check existing subtitle
        existing = await MovieSubtitle.objects.filter(
            movie=movie, language=language, is_active=True
        ).afirst()

        if existing:
            return SubtitleResponse.from_orm(existing)

        content, format, metadata = await client.search_and_download(
            tmdb_id=movie.tmdb_id, language=language
        )
        subtitle = await sync_to_async(storage.store_subtitle)(
            movie=movie,
            subtitle_content=content,
            metadata=metadata,
            subtitle_format=format,
        )

        log.info(
            "Direct subtitle sync completed", movie_id=movie_id, subtitle_id=subtitle.id
        )

        return SubtitleResponse.from_orm(subtitle)

    except Movie.DoesNotExist:
        log.error("Movie not found", movie_id=movie_id)
        raise RESTError("Movie not found")
    except Exception as e:
        log.error(
            "Direct subtitle sync failed",
            movie_id=movie_id,
            error=str(e),
            exc_info=True,
        )
        raise RESTError(str(e))


@router.get(
    "/media/subtitles/{tmdb_id}",
    response=SubtitleListResponse,
    summary="List movie subtitles",
)
def list_subtitles(
    request: HttpRequest, tmdb_id: int, language: str | None = None
) -> SubtitleListResponse:
    """List available subtitles for a movie"""
    log.info("Listing subtitles", tmdb_id=tmdb_id, language=language)
    try:
        query = MovieSubtitle.objects.filter(movie__tmdb_id=tmdb_id)
        if language:
            query = query.filter(language=language)

        subtitles = query.all()

        response = SubtitleListResponse(
            subtitles=[SubtitleResponse.from_orm(subtitle) for subtitle in subtitles]
        )

        log.info(
            "Listed subtitles successfully",
            tmdb_id=tmdb_id,
            count=len(response.subtitles),
        )

        return response

    except Exception as e:
        log.error(
            "Failed to list subtitles", tmdb_id=tmdb_id, error=str(e), exc_info=True
        )
        raise RESTError(f"Failed to list subtitles: {str(e)}")


@router.post(
    "/download/start",
    response=DownloadJobStatus,
    summary="Trigger download all subtitles job",
)
async def start_missing_subtitle_downloads(
    request: HttpRequest, params: SubtitleDownloadRequest
) -> DownloadJobStatus:
    """Start a background job to download missing movie subtitles"""
    try:
        # Queue download job
        queue = django_rq.get_queue("subtitles", default_timeout=28800)
        job = queue.enqueue(
            download_missing_subtitles,
            args=(
                params.language,
                params.max_downloads,
            ),
            job_timeout=28800,
        )

        log.info("Queued subtitle download job", job_id=job.id, params=params.dict())

        return DownloadJobStatus(
            job_id=job.id, status="queued", started_at=datetime.now()
        )

    except Exception as e:
        log.error("Failed to queue download job", error=str(e), exc_info=True)
        raise RESTError(f"Failed to start download job: {str(e)}")
