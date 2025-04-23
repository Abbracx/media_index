from django.http import HttpRequest
from ninja.renderers import JSONRenderer
from typing import Any
from datetime import timezone, datetime


class L2APIRenderer(JSONRenderer):
    def render(
        self,
        request: HttpRequest,
        data: Any,
        *,
        response_status: int,
    ) -> Any:
        if isinstance(data, dict):
            data["request_timestamp"] = datetime.now(timezone.utc).isoformat()

        return super().render(request, data, response_status=response_status)
