"""HTTP policy: method, actor, target, owner guard, preflight, then input."""

from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_protect

from accounts.models import User
from accounts.views import auth_required, method_error
from common.errors import error_response
from social import service
from social.validation import FORM, canonical_uuid, decode, validate


def failure(request: HttpRequest, exc: service.SocialError) -> JsonResponse:
    return (
        auth_required(request)
        if exc.status == 401
        else error_response(request, exc.status, exc.code)
    )


def boundary(request: HttpRequest, identity: str, allowed: str) -> UUID | HttpResponse:
    if request.method not in allowed.split(", "):
        return method_error(request, allowed)
    if not request.user.is_authenticated:
        return auth_required(request)
    try:
        key = canonical_uuid(identity)
    except ValueError:
        return error_response(request, 404)
    if request.method != "GET":
        try:
            owner = canonical_uuid(request.headers.get("X-Social-Owner", ""))
        except ValueError:
            return error_response(request, 400, "INVALID_REQUEST", field_errors={"_form": [FORM]})
        if owner != request.user.pk:
            return error_response(request, 409, "SOCIAL_OWNER_CHANGED")
    return key


def declared_length(request: HttpRequest) -> int:
    # CSRF may have consumed multipart POST data before the view reads the stream.
    try:
        return int(request.META.get("CONTENT_LENGTH", "0"))
    except (TypeError, ValueError):
        return 0


def input_data(request: HttpRequest, *, creating: bool) -> dict[str, object] | JsonResponse:
    if declared_length(request) > 16384:
        return error_response(request, 413)
    raw = request.read(16385)
    if len(raw) > 16384:
        return error_response(request, 413)
    if (
        request.content_type != "application/json"
        or (request.content_params or {}).get("charset", "utf-8").lower() != "utf-8"
    ):
        return error_response(request, 415)
    try:
        return validate(decode(raw), creating=creating)
    except (ValueError, RecursionError, UnicodeError):
        return error_response(request, 400, field_errors={"_form": [FORM]})
    except ValidationError as exc:
        return error_response(request, 400, field_errors=exc.message_dict)


def invalid_query(request: HttpRequest, allowed: set[str]) -> bool:
    return bool(set(request.GET) - allowed) or any(
        len(request.GET.getlist(k)) != 1 for k in request.GET
    )


@csrf_protect
def comments(request: HttpRequest, identity: str) -> HttpResponse:
    key = boundary(request, identity, "GET, POST")
    if isinstance(key, HttpResponse):
        return key
    assert isinstance(request.user, User)
    try:
        if request.method == "GET":
            if invalid_query(request, {"limit", "cursor"}):
                return error_response(request, 400, "INVALID_CURSOR")
            return JsonResponse(
                service.listing(
                    key, request.user, request.GET.get("limit", "20"), request.GET.get("cursor")
                )
            )
        service.preflight_post(key)
        data = input_data(request, creating=True)
        if isinstance(data, JsonResponse):
            return data
        return JsonResponse(service.write_comment(request.user, key, data), status=201, safe=False)
    except service.SocialError as exc:
        return failure(request, exc)
    except IntegrityError:
        return error_response(request, 500)


@csrf_protect
def comment(request: HttpRequest, identity: str) -> HttpResponse:
    key = boundary(request, identity, "GET, PUT, DELETE")
    if isinstance(key, HttpResponse):
        return key
    assert isinstance(request.user, User)
    try:
        if request.method == "GET":
            if invalid_query(request, set()):
                return error_response(request, 400, "INVALID_CURSOR")
            return JsonResponse(service.detail(key, request.user))
        post_id = service.preflight_comment(key, request.user)
        if request.method == "DELETE":
            service.write_comment(request.user, post_id, None, key, delete=True)
            return HttpResponse(status=204)
        data = input_data(request, creating=False)
        if isinstance(data, JsonResponse):
            return data
        return JsonResponse(service.write_comment(request.user, post_id, data, key), safe=False)
    except service.SocialError as exc:
        return failure(request, exc)
    except IntegrityError:
        return error_response(request, 500)


@csrf_protect
def like(request: HttpRequest, identity: str) -> HttpResponse:
    key = boundary(request, identity, "POST, DELETE")
    if isinstance(key, HttpResponse):
        return key
    assert isinstance(request.user, User)
    try:
        service.preflight_post(key)
        if declared_length(request) > 0 or request.read(1):
            return error_response(request, 400, "INVALID_REQUEST", field_errors={"_form": [FORM]})
        return JsonResponse(service.write_like(request.user, key, enabled=request.method == "POST"))
    except service.SocialError as exc:
        return failure(request, exc)
    except IntegrityError:
        return error_response(request, 500)
