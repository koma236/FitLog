"""API例外境界。例外本文やユーザー入力をレスポンスへ反射しない。"""
from typing import Any
from uuid import uuid4

from django.core import exceptions as django_exceptions
from django.http import Http404, HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework import exceptions

ERRORS: dict[int, tuple[str, str]] = {
    400: ("VALIDATION_ERROR", "リクエストを確認してください。"),
    401: ("AUTH_REQUIRED", "ログインが必要です。"),
    403: ("FORBIDDEN", "この操作は許可されていません。"),
    404: ("NOT_FOUND", "対象が見つかりません。"),
    405: ("METHOD_NOT_ALLOWED", "このメソッドは利用できません。"),
    406: ("NOT_ACCEPTABLE", "指定された応答形式は利用できません。"),
    415: ("UNSUPPORTED_MEDIA_TYPE", "指定された入力形式は利用できません。"),
    429: ("RATE_LIMITED", "時間をおいて再試行してください。"),
    500: ("INTERNAL_ERROR", "処理中にエラーが発生しました。"),
}


class CsrfFailure(exceptions.PermissionDenied):
    """CSRF拒否として識別済みの場合だけ使用する。"""


def error_response(request: HttpRequest, status: int, code: str | None = None) -> JsonResponse:
    """固定文言の共通Errorとrequest-idを返す。"""
    default_code, message = ERRORS[status]
    if code == "INVALID_CREDENTIALS":
        message = "認証情報を確認してください。"
    elif code == "CSRF_FAILED":
        message = "リクエストを再送してください。"
    request_id = request.META.setdefault("FITLOG_REQUEST_ID", str(uuid4()))
    response = JsonResponse({
        "code": code or default_code, "message": message, "requestId": request_id,
    }, status=status)
    response["X-Request-Id"] = request_id
    return response


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> JsonResponse:
    """DRF/Django例外分類表を実装し、該当する例外ヘッダーを維持する。"""
    request = context["request"]
    code = None
    if isinstance(exc, (exceptions.ParseError, exceptions.ValidationError, django_exceptions.SuspiciousOperation, django_exceptions.BadRequest)):
        status = 400
    elif isinstance(exc, exceptions.NotAuthenticated):
        status = 401
    elif isinstance(exc, exceptions.AuthenticationFailed):
        status, code = 401, "INVALID_CREDENTIALS"
    elif isinstance(exc, CsrfFailure):
        status, code = 403, "CSRF_FAILED"
    elif isinstance(exc, (exceptions.PermissionDenied, django_exceptions.PermissionDenied)):
        status = 403
    elif isinstance(exc, (exceptions.NotFound, Http404)):
        status = 404
    elif isinstance(exc, exceptions.MethodNotAllowed):
        status = 405
    elif isinstance(exc, exceptions.NotAcceptable):
        status = 406
    elif isinstance(exc, exceptions.UnsupportedMediaType):
        status = 415
    elif isinstance(exc, exceptions.Throttled):
        status = 429
    else:
        status = 500
    response = error_response(request, status, code)
    auth_header = getattr(exc, "auth_header", None)
    if auth_header:
        response["WWW-Authenticate"] = auth_header
    # DRF sets this instance attribute dynamically; its stubs do not declare it.
    wait = getattr(exc, "wait", None)
    if isinstance(exc, exceptions.Throttled) and isinstance(wait, (int, float)):
        response["Retry-After"] = str(wait)
    return response


@csrf_exempt
def not_found(request: HttpRequest) -> JsonResponse:
    return error_response(request, 404)


def csrf_failure(request: HttpRequest, reason: str = "") -> JsonResponse:
    return error_response(request, 403, "CSRF_FAILED")
