"""Active-member relationships, sorted User locks and bounded search keysets."""

import re
import unicodedata
from datetime import datetime
from typing import Any
from uuid import UUID

from django.core import signing
from django.db import models, transaction
from django.db.models import Count, Exists, OuterRef, Q, QuerySet, Subquery, Value
from django.db.models.functions import Coalesce

from accounts.models import User
from media_assets.presentation import avatar
from social.models import Follow
from social.service import SocialError, snapshot
from social.validation import canonical_uuid


def relationships() -> QuerySet[Follow]:
    return Follow.objects.filter(follower__is_active=True, followee__is_active=True)


def member_query(actor: User) -> QuerySet[User]:
    rows = relationships()
    followers = rows.filter(followee_id=OuterRef("pk")).values("followee_id").annotate(total=Count("pk")).values("total")
    following = rows.filter(follower_id=OuterRef("pk")).values("follower_id").annotate(total=Count("pk")).values("total")
    return User.objects.filter(is_active=True).select_related("avatar_attachment__object").annotate(
        follower_count=Coalesce(Subquery(followers, output_field=models.IntegerField()), Value(0)),
        following_count=Coalesce(Subquery(following, output_field=models.IntegerField()), Value(0)),
        is_following=Exists(rows.filter(follower=actor, followee_id=OuterRef("pk"))),
    )


def relation_fields(user: User, actor: User) -> dict[str, Any]:
    # Profile callers may hold an unannotated User. One query, never a per-search-row query.
    if not hasattr(user, "follower_count"):
        user = member_query(actor).get(pk=user.pk)
    annotations = vars(user)
    return {"follower_count": annotations["follower_count"],
            "following_count": annotations["following_count"],
            "is_following": user.pk != actor.pk and annotations["is_following"]}


def write_follow(actor: User, target: UUID, *, enabled: bool) -> dict[str, Any]:
    if actor.pk == target:
        raise SocialError(400, "SELF_FOLLOW")
    with transaction.atomic():
        # Explicit ordering is essential; IN alone does not promise lock order.
        locked = {u.pk: u for u in User.objects.select_for_update().filter(pk__in=[actor.pk, target]).order_by("pk")}
        user, other = locked.get(actor.pk), locked.get(target)
        if user is None or not user.is_active:
            raise SocialError(401)
        if other is None or not other.is_active:
            raise SocialError(404)
        if enabled:
            Follow.objects.get_or_create(follower=user, followee=other)
        else:
            Follow.objects.filter(follower=user, followee=other).delete()
        rows = relationships()
        return {"viewer_id": str(user.pk), "user_id": str(other.pk),
                "is_following": rows.filter(follower=user, followee=other).exists(),
                "follower_count": rows.filter(followee=other).count(),
                "following_count": rows.filter(follower=user).count()}


def query_text(q: str) -> str:
    q = q.strip()
    if len(q) > 50 or any(unicodedata.category(char) in {"Cc", "Cs"} for char in q):
        raise SocialError(400, "VALIDATION_ERROR")
    return q


def boundary(actor: User, scope: str, limit_text: str, cursor: str | None, q: str = "") -> tuple[int, tuple[datetime, UUID] | None]:
    if not re.fullmatch(r"[1-9][0-9]?", limit_text) or not 1 <= int(limit_text) <= 50:
        raise SocialError(400, "INVALID_CURSOR")
    last = None
    if cursor is not None:
        try:
            if not cursor or not cursor.isascii() or len(cursor) > 2048:
                raise ValueError("cursor length")
            value = signing.loads(cursor, salt="social.members." + scope, max_age=86400)
            if (not isinstance(value, dict) or set(value) != {"v", "viewer", "scope", "q", "at", "id"}
                    or type(value["v"]) is not int or value["v"] != 1
                    or value["viewer"] != str(actor.pk) or value["scope"] != scope or value["q"] != q
                    or not isinstance(value["at"], str)):
                raise ValueError("cursor context")
            at = datetime.fromisoformat(value["at"])
            if at.tzinfo is None:
                raise ValueError("cursor time")
            last = at, canonical_uuid(value["id"])
        except (signing.BadSignature, TypeError, ValueError, KeyError, UnicodeError):
            raise SocialError(400, "INVALID_CURSOR") from None
    return int(limit_text), last


def make_cursor(actor: User, scope: str, at: datetime, identity: UUID, q: str = "") -> str:
    return signing.dumps({"v": 1, "viewer": str(actor.pk), "scope": scope, "q": q,
                          "at": at.isoformat(timespec="microseconds"), "id": str(identity)}, salt="social.members." + scope)


def search(actor: User, q: str, limit_text: str, cursor: str | None) -> dict[str, Any]:
    q = query_text(q)
    limit, last = boundary(actor, "search", limit_text, cursor, q)
    with snapshot():
        query = member_query(actor)
        if q:
            query = query.filter(Q(username__icontains=q) | Q(display_name__icontains=q))
        if last:
            at, identity = last
            query = query.filter(Q(date_joined__lt=at) | Q(date_joined=at, pk__lt=identity))
        rows = list(query.order_by("-date_joined", "-pk")[:limit+1])
        visible = rows[:limit]
        return {"viewer_id": str(actor.pk), "items": [
            {"id": str(user.pk), "username": user.username, "display_name": user.display_name,
             "avatar": avatar(user), "is_owner": user.pk == actor.pk, **relation_fields(user, actor)} for user in visible],
            "next_cursor": make_cursor(actor, "search", visible[-1].date_joined, visible[-1].pk, q) if len(rows) > limit else None}
