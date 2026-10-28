"""DEBUGに依存しないAPI境界とサーバー生成request-id。"""
import json
import logging
from collections.abc import Callable
from uuid import uuid4

from django.core.exceptions import DisallowedHost
from django.http import HttpRequest, HttpResponse, JsonResponse

from common.errors import ERRORS, api_exception_handler, error_response

logger = logging.getLogger("fitlog.api")


class ApiBoundaryMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.META["FITLOG_REQUEST_ID"] = str(uuid4())
        is_api = request.path == "/api" or request.path.startswith("/api/")
        response: HttpResponse
        if is_api:
            try:
                request.get_host()
            except DisallowedHost:
                response = error_response(request, 400)
            else:
                response = self.get_response(request)
        else:
            response = self.get_response(request)
        if is_api:
            if response.status_code in ERRORS and not self._is_common_error(request, response):
                normalized = error_response(request, response.status_code)
                for header in (
                    "Allow", "WWW-Authenticate", "Retry-After", "X-Content-Type-Options",
                    "Referrer-Policy", "Cross-Origin-Opener-Policy", "Strict-Transport-Security",
                    "X-Frame-Options",
                ):
                    if header in response:
                        normalized[header] = response[header]
                response = normalized
            response["X-Request-Id"] = request.META["FITLOG_REQUEST_ID"]
            if response.status_code >= 400:
                logger.warning("api_error status=%s request_id=%s",
                               response.status_code, request.META["FITLOG_REQUEST_ID"])
        return response

    @staticmethod
    def _is_common_error(request: HttpRequest, response: HttpResponse) -> bool:
        if not response.get("Content-Type", "").startswith("application/json"):
            return False
        try:
            body = json.loads(response.content)
        except (ValueError, UnicodeDecodeError):
            return False
        return (
            isinstance(body, dict)
            and isinstance(body.get("code"), str)
            and isinstance(body.get("message"), str)
            and body.get("requestId") == request.META["FITLOG_REQUEST_ID"]
        )

    def process_exception(self, request: HttpRequest, exception: Exception) -> JsonResponse | None:
        if request.path == "/api" or request.path.startswith("/api/"):
            return api_exception_handler(exception, {"request": request})
        return None
