from http import HTTPStatus


import structlog

log: structlog.BoundLogger = structlog.get_logger(__name__)


class RESTError(Exception):
    """Raise HTTP errors which can be returned to the client.
    RESTErrors that are raised *must* be safe to return to the client, and
    should contain a short but descriptive message of maximum 200 characters.
    These errors may sometimes be displayed to the user. Whilst, ideally, the client
    would handle them, it is important to ensure that the message is appropriate for
    an end user to read.
    """

    def __init__(
        self,
        message: str = "Bad request",
        status_code: HTTPStatus = HTTPStatus.BAD_REQUEST,
    ) -> None:
        if len(message) > 200:
            log.warning(
                "RESTError message too long",
                message=message,
                status_code=status_code,
            )

        super().__init__(message)
        self.message: str = message
        self.status_code: HTTPStatus = status_code


class FeatureDisabledError(Exception):
    """Error raised when a feature is used which has been disabled, e.g. by feature flags."""

    def __init__(
        self,
        message: str,
        status_code: HTTPStatus = HTTPStatus.SERVICE_UNAVAILABLE,
    ) -> None:
        self.message: str = message
        self.status_code: HTTPStatus = status_code
        super().__init__(message)
