"""User → Post → Comment locks and coherent read-only PostgreSQL snapshots."""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from django.core import signing
from django.db import IntegrityError, connection, transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from accounts.models import User
from social.models import Comment, CommentIdentity, Like
from social.presentation import comment_dto, timestamp
from social.validation import canonical_uuid
from workouts.models import Post

CURSOR_SALT = "social.comments.cursor.v1"


class SocialError(Exception):
    def __init__(self, status: int, code: str | None = None) -> None:
        self.status, self.code = status, code


def comments() -> QuerySet[Comment]:
    return Comment.objects.filter(user__is_active=True, post__user__is_active=True).select_related(
        "user", "user__avatar_attachment__object"
    )


def preflight_post(identity: UUID) -> None:
    if not Post.objects.filter(pk=identity, user__is_active=True).exists():
        raise SocialError(404)


def preflight_comment(identity: UUID, actor: User) -> UUID:
    row = comments().filter(pk=identity).first()
    if row is None:
        raise SocialError(404)
    if row.user_id != actor.pk:
        raise SocialError(403)
    return cast(UUID, row.post_id)


@contextmanager
def snapshot() -> Iterator[None]:
    with transaction.atomic(durable=True):
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        yield


def result(row: Comment, actor: User) -> dict[str, Any]:
    return {
        "viewer_id": str(actor.pk),
        "post_id": str(row.post_id),
        "comment": comment_dto(row, actor),
        "comment_count": comments().filter(post_id=row.post_id).count(),
    }


def detail(identity: UUID, actor: User) -> dict[str, Any]:
    with snapshot():
        row = comments().filter(pk=identity).first()
        if row is None:
            raise SocialError(404)
        return result(row, actor)


def locked_parent(actor: User, post_id: UUID) -> tuple[User, Post]:
    user = User.objects.select_for_update().filter(pk=actor.pk, is_active=True).first()
    if user is None:
        raise SocialError(401)
    # Never join the parent author into FOR UPDATE: that would acquire a second User lock.
    post = Post.objects.select_for_update().filter(pk=post_id).first()
    if post is None or not User.objects.filter(pk=post.user_id, is_active=True).exists():
        raise SocialError(404)
    return user, post


def create_identity(identity: UUID, actor: User, post_id: UUID) -> CommentIdentity:
    try:
        with transaction.atomic():
            return CommentIdentity.objects.create(id=identity, author=actor, post_uuid=post_id)
    except IntegrityError as exc:
        cause = exc.__cause__
        if getattr(cause, "sqlstate", None) == "23505":
            with connection.cursor() as cursor:
                constraints = connection.introspection.get_constraints(
                    cursor, CommentIdentity._meta.db_table
                )
            actual = getattr(getattr(cause, "diag", None), "constraint_name", None)
            if actual in constraints and constraints[actual]["primary_key"]:
                raise SocialError(409, "COMMENT_ID_CONFLICT") from None
        raise


def write_comment(
    actor: User,
    post_id: UUID,
    data: dict[str, Any] | None,
    identity: UUID | None = None,
    *,
    delete: bool = False,
) -> dict[str, Any] | None:
    with transaction.atomic():
        user, post = locked_parent(actor, post_id)
        if identity is None:
            assert data is not None and not delete
            key = create_identity(data["id"], user, post.pk)
            now = timezone.now()
            row = Comment(
                identity=key,
                post=post,
                user=user,
                body=data["body"],
                created_at=now,
                updated_at=now,
            )
            row.save(force_insert=True)
        else:
            found = Comment.objects.select_for_update().filter(pk=identity, post_id=post.pk).first()
            if found is None or not User.objects.filter(pk=found.user_id, is_active=True).exists():
                raise SocialError(404)
            row = found
            if row.user_id != user.pk:
                raise SocialError(403)
            if delete:
                row.delete()
                return None
            assert data is not None
            row.body, row.updated_at = data["body"], timezone.now()
            row.save(update_fields=["body", "updated_at"])
        visible = comments().filter(pk=row.pk).first()
        if visible is None:
            raise SocialError(404)
        return result(visible, user)


def write_like(actor: User, post_id: UUID, *, enabled: bool) -> dict[str, Any]:
    with transaction.atomic():
        user, post = locked_parent(actor, post_id)
        if enabled:
            Like.objects.get_or_create(post=post, user=user)
        else:
            Like.objects.filter(post=post, user=user).delete()
        rows = Like.objects.filter(post=post, user__is_active=True)
        return {
            "viewer_id": str(user.pk),
            "post_id": str(post.pk),
            "is_liked": rows.filter(user=user).exists(),
            "like_count": rows.count(),
        }


def cursor_boundary(
    post_id: UUID, actor: User, limit_text: str, cursor_text: str | None
) -> tuple[int, tuple[datetime, UUID] | None]:
    if not re.fullmatch(r"[1-9][0-9]?", limit_text) or not 1 <= int(limit_text) <= 50:
        raise SocialError(400, "INVALID_CURSOR")
    boundary = None
    if cursor_text is not None:
        try:
            if len(cursor_text.encode("utf-8")) > 2048:
                raise ValueError("Cursor length")
            value = signing.loads(cursor_text, salt=CURSOR_SALT, max_age=86400)
            if (
                not isinstance(value, dict)
                or set(value) != {"v", "viewer", "post", "at", "id"}
                or type(value["v"]) is not int
                or value["v"] != 1
                or value["viewer"] != str(actor.pk)
                or value["post"] != str(post_id)
                or not isinstance(value["at"], str)
                or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", value["at"])
            ):
                raise ValueError("Cursor context")
            at = datetime.fromisoformat(value["at"])
            boundary = (at, canonical_uuid(value["id"], v4=True))
        except (signing.BadSignature, ValueError, TypeError, KeyError, UnicodeError):
            raise SocialError(400, "INVALID_CURSOR") from None
    return int(limit_text), boundary


def listing(post_id: UUID, actor: User, limit_text: str, cursor_text: str | None) -> dict[str, Any]:
    limit, boundary = cursor_boundary(post_id, actor, limit_text, cursor_text)
    with snapshot():
        preflight_post(post_id)
        all_rows = comments().filter(post_id=post_id)
        count = all_rows.count()
        query = all_rows.order_by("created_at", "identity_id")
        if boundary is not None:
            at, last = boundary
            query = query.filter(Q(created_at__gt=at) | Q(created_at=at, identity_id__gt=last))
        rows = list(query[: limit + 1])
        visible = rows[:limit]
        next_cursor = None
        if len(rows) > limit:
            row = visible[-1]
            next_cursor = signing.dumps(
                {
                    "v": 1,
                    "viewer": str(actor.pk),
                    "post": str(post_id),
                    "at": timestamp(row.created_at),
                    "id": str(row.pk),
                },
                salt=CURSOR_SALT,
            )
        return {
            "viewer_id": str(actor.pk),
            "post_id": str(post_id),
            "comment_count": count,
            "items": [comment_dto(row, actor) for row in visible],
            "next_cursor": next_cursor,
        }
