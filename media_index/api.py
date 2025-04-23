from ninja_extra import NinjaExtraAPI
from django.http import HttpResponse, HttpRequest

from language_analysis.v1.api import router as language_analysis_router
from TMDB.v1.api import router as movie_router
from media_index.errors import RESTError, FeatureDisabledError
from subtitles.v1.api import router as subtitles_router

api = NinjaExtraAPI()

api.add_router("/media/", movie_router)
api.add_router("/subtitles/", subtitles_router)
api.add_router("/linguistic/", language_analysis_router)


@api.exception_handler(RESTError)
def rest_error(
    request: HttpRequest,
    exc: RESTError,
) -> HttpResponse:
    return api.create_response(
        request,
        {"error": {"message": exc.message}},
        status=exc.status_code,
    )


@api.exception_handler(FeatureDisabledError)
def feature_disabled_error(
    request: HttpRequest,
    exc: FeatureDisabledError,
) -> HttpResponse:
    return api.create_response(
        request,
        {"error": {"message": exc.message}},
        status=exc.status_code,
    )
