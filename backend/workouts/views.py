"""HTTP policy and validation, with all business updates in service."""

from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_protect

from accounts.views import auth_required, method_error
from common.errors import error_response
from workouts import service
from workouts.validation import FORM, canonical_uuid, decode, validate


def failure(request: HttpRequest, exc: service.RecordError) -> JsonResponse:
    return (
        auth_required(request)
        if exc.status == 401
        else error_response(request, exc.status, exc.code)
    )


@csrf_protect
def record(request: HttpRequest, identity: str | None = None) -> HttpResponse:
    allowed = "POST" if identity is None else "GET, PUT, DELETE"
    if request.method not in allowed.split(", "):
        return method_error(request, allowed)
    if not request.user.is_authenticated:
        return auth_required(request)
    key: UUID | None = None
    if identity is not None:
        try:
            key = canonical_uuid(identity)
        except ValueError:
            return error_response(request, 404)
    try:
        if request.method == "GET":
            assert key is not None
            return JsonResponse(service.detail(key, request.user))
        try:
            actor = canonical_uuid(request.headers.get("X-Record-Owner", ""))
        except ValueError:
            return error_response(request, 400, "INVALID_REQUEST", field_errors={"_form": [FORM]})
        if actor != request.user.pk:
            return error_response(request, 409, "RECORD_OWNER_CHANGED")
        if key is not None:
            service.preflight(key, request.user)
        if request.method == "DELETE":
            service.write(request.user, None, key, delete=True)
            return HttpResponse(status=204)
        raw = request.read(32769)
        if len(raw) > 32768:
            return error_response(request, 413)
        if (
            request.content_type != "application/json"
            or (request.content_params or {}).get("charset", "utf-8").lower() != "utf-8"
        ):
            return error_response(request, 415)
        try:
            data = validate(decode(raw), creating=key is None)
        except (ValueError, RecursionError, UnicodeError):
            return error_response(request, 400, field_errors={"_form": [FORM]})
        except ValidationError as exc:
            return error_response(request, 400, field_errors=exc.message_dict)
        return JsonResponse(
            service.write(request.user, data, key), status=201 if key is None else 200, safe=False
        )
    except service.RecordError as exc:
        return failure(request, exc)
    except IntegrityError:
        return error_response(request, 500)


@csrf_protect
def user_posts(request: HttpRequest, username: str) -> JsonResponse:
    if request.method != "GET":
        return method_error(request, "GET")
    if not request.user.is_authenticated:
        return auth_required(request)
    if set(request.GET) - {"limit", "cursor"} or any(
        len(request.GET.getlist(k)) != 1 for k in request.GET
    ):
        return error_response(request, 400, "INVALID_CURSOR")
    try:
        return JsonResponse(
            service.listing(
                username, request.user, request.GET.get("limit", "20"), request.GET.get("cursor")
            )
        )
    except service.RecordError as exc:
        return failure(request, exc)
