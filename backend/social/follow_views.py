"""Method/auth/query precedence and bodyless owner-bound follow commands."""

from django.db import IntegrityError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_protect

from accounts.models import User
from accounts.views import auth_required, method_error
from common.errors import error_response
from social import follow_service as service
from social.service import SocialError
from social.views import boundary, declared_length, failure, invalid_query


def read_guard(request: HttpRequest) -> HttpResponse | None:
    if request.method != "GET":
        return method_error(request, "GET")
    if not request.user.is_authenticated:
        return auth_required(request)
    return None


@csrf_protect
def search(request: HttpRequest) -> HttpResponse:
    denied = read_guard(request)
    if denied is not None:
        return denied
    assert isinstance(request.user, User)
    if invalid_query(request, {"q", "limit", "cursor"}):
        return error_response(request, 400, "INVALID_CURSOR")
    try:
        return JsonResponse(service.search(request.user, request.GET.get("q", ""), request.GET.get("limit", "20"), request.GET.get("cursor")))
    except SocialError as exc:
        return failure(request, exc)


@csrf_protect
def follow(request: HttpRequest, identity: str) -> HttpResponse:
    key = boundary(request, identity, "POST, DELETE")
    if isinstance(key, HttpResponse):
        return key
    assert isinstance(request.user, User)
    if key == request.user.pk:
        return error_response(request, 400, "SELF_FOLLOW")
    if not User.objects.filter(pk=key, is_active=True).exists():
        return error_response(request, 404)
    if invalid_query(request, set()) or declared_length(request) > 0 or request.read(1):
        return error_response(request, 400, "INVALID_REQUEST")
    try:
        return JsonResponse(service.write_follow(request.user, key, enabled=request.method == "POST"))
    except SocialError as exc:
        return failure(request, exc)
    except IntegrityError:
        return error_response(request, 500)
