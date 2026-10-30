"""Authenticated image mutations and short-lived capability downloads."""

from threading import BoundedSemaphore
from uuid import UUID

from django.core import signing
from django.db import IntegrityError, transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_protect

from accounts.views import auth_required, method_error
from common.errors import error_response
from media_assets import service
from media_assets.exceptions import ImageError
from media_assets.models import ImageObject
from media_assets.presentation import resolve_token
from media_assets.processing import normalize
from media_assets.storage import LocalStorage
from media_assets.uploads import read_image
from workouts.validation import canonical_uuid

DECODE_SLOT = BoundedSemaphore(1)


def image_failure(request: HttpRequest, exc: ImageError) -> JsonResponse:
    response = (
        auth_required(request)
        if exc.status == 401
        else error_response(request, exc.status, exc.code)
    )
    if exc.code in {"IMAGE_PROCESSING_BUSY", "IMAGE_OPERATION_PENDING"}:
        response["Retry-After"] = "2"
    return response


@transaction.non_atomic_requests
@csrf_protect
def image(request: HttpRequest, identity: str | None = None) -> HttpResponse:
    if request.method not in {"PUT", "DELETE"}:
        return method_error(request, "PUT, DELETE")
    if not request.user.is_authenticated:
        return auth_required(request)
    kind: service.TargetKind = "post" if identity is not None else "avatar"
    try:
        target = canonical_uuid(identity) if identity is not None else request.user.pk
    except ValueError:
        return error_response(request, 404)
    header = "X-Record-Owner" if kind == "post" else "X-Profile-Owner"
    try:
        actor = canonical_uuid(request.headers.get(header, ""))
    except ValueError:
        return error_response(request, 400, "INVALID_REQUEST")
    if actor != request.user.pk:
        return error_response(
            request, 409, "RECORD_OWNER_CHANGED" if kind == "post" else "PROFILE_OWNER_CHANGED"
        )
    try:
        service.preflight(request.user, kind, target)
        if request.method == "DELETE":
            service.remove(request.user, kind, target)
            return HttpResponse(status=204)
        try:
            operation = canonical_uuid(request.headers.get("X-Image-Operation", ""))
            if operation.version != 4:
                raise ValueError
        except ValueError:
            return error_response(request, 400, "INVALID_REQUEST")
        if not DECODE_SLOT.acquire(blocking=False):
            raise ImageError(503, "IMAGE_PROCESSING_BUSY")
        try:
            maximum = 5242880 if kind == "post" else 2097152
            value = normalize(read_image(request, maximum), maximum)
            result = service.upload(request.user, kind, target, operation, value)
            return JsonResponse(result)
        finally:
            DECODE_SLOT.release()
    except ImageError as exc:
        return image_failure(request, exc)
    except IntegrityError:
        return error_response(request, 500)


def content(request: HttpRequest, token: str) -> HttpResponse:
    if request.method != "GET":
        return method_error(request, "GET")
    try:
        identity: UUID = resolve_token(token)
    except (signing.BadSignature, ValueError, TypeError):
        return error_response(request, 404)
    asset = ImageObject.objects.filter(pk=identity, state="attached").first()
    if asset is None:
        return error_response(request, 404)
    try:
        data = LocalStorage().read(asset.key)
    except ImageError as exc:
        return image_failure(request, exc)
    response = HttpResponse(data, content_type=asset.content_type)
    response["Content-Disposition"] = (
        'inline; filename="image.' + ("jpg" if asset.content_type == "image/jpeg" else "png") + '"'
    )
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Referrer-Policy"] = "no-referrer"
    return response
