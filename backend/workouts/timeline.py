"""A coherent post page for active authors, using existing post DTOs."""

from typing import Any

from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.cache import cache_control
from django.views.decorators.csrf import csrf_protect

from accounts.models import User
from common.errors import error_response
from social.follow_service import boundary, make_cursor, relationships
from social.follow_views import read_guard
from social.service import SocialError
from social.views import failure, invalid_query
from workouts.service import dto, posts, snapshot


def listing(actor: User, scope: str, limit_text: str, cursor: str | None) -> dict[str, Any]:
    limit, last = boundary(actor, scope, limit_text, cursor)
    with snapshot():
        query = posts(actor)
        if scope == "following":
            query = query.filter(Q(user=actor) | Q(user_id__in=relationships().filter(follower=actor).values("followee_id")))
        if last:
            at, identity = last
            query = query.filter(Q(created_at__lt=at) | Q(created_at=at, identity_id__lt=identity))
        rows = list(query.order_by("-created_at", "-identity_id")[:limit+1])
        visible = rows[:limit]
        return {"viewer_id": str(actor.pk), "items": [dto(row, actor) for row in visible],
                "next_cursor": make_cursor(actor, scope, visible[-1].created_at, visible[-1].pk) if len(rows) > limit else None}


@csrf_protect
@cache_control(no_store=True)
def timeline(request: HttpRequest, scope: str) -> HttpResponse:
    denied = read_guard(request)
    if denied is not None:
        return denied
    if scope not in {"following", "all"}:
        return error_response(request, 404)
    if invalid_query(request, {"limit", "cursor"}):
        return error_response(request, 400, "INVALID_CURSOR")
    assert isinstance(request.user, User)
    try:
        return JsonResponse(listing(request.user, scope, request.GET.get("limit", "20"), request.GET.get("cursor")))
    except SocialError as exc:
        return failure(request, exc)
