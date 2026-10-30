"""Atomic writes and coherent read-only PostgreSQL snapshots."""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from django.core import signing
from django.db import IntegrityError, connection, transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from accounts.models import ProfileHealth, User
from media_assets.presentation import avatar, post_image
from social.presentation import post_fields, with_social
from workouts.calories import calculate
from workouts.models import Post, PostIdentity, WorkoutExercise, WorkoutSet


class RecordError(Exception):
    def __init__(self, status: int, code: str | None = None) -> None:
        self.status, self.code = status, code


def dto(post: Post, actor: User) -> dict[str, Any]:
    owner = post.user_id == actor.pk
    result: dict[str, Any] = {
        "viewer_id": str(actor.pk),
        "id": str(post.pk),
        "author": {
            "id": str(post.user_id),
            "username": post.user.username,
            "display_name": post.user.display_name,
            "avatar": avatar(post.user),
        },
        "is_owner": owner,
        "image": post_image(post),
        "performed_on": post.performed_on.isoformat(),
        "note": post.note,
        "created_at": post.created_at.astimezone(UTC)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z"),
        "updated_at": post.updated_at.astimezone(UTC)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z"),
        "exercises": [
            {
                "name": ex.name,
                "sets": [
                    {"weight_kg": f"{row.weight_kg:.2f}", "reps": row.reps} for row in ex.sets.all()
                ],
            }
            for ex in post.exercises.all()
        ],
        "energy": {"kcal": post.energy_kcal, "method": post.energy_method}
        if post.energy_kcal is not None
        else None,
        "energy_input": {
            k: getattr(post, k)
            for k in ("minutes", "kind")
            if owner or (getattr(post, k + "_public") and getattr(post, k) is not None)
        },
    }
    if owner:
        result["visibility"] = {
            k: "public" if getattr(post, k + "_public") else "private" for k in ("minutes", "kind")
        }
    result.update(post_fields(post))
    return result


def posts(actor: User) -> QuerySet[Post]:
    return with_social(
        Post.objects.select_related("user", "user__avatar_attachment__object", "image_attachment__object")
        .prefetch_related("exercises__sets")
        .filter(user__is_active=True), actor,
    )


@contextmanager
def snapshot() -> Iterator[None]:
    with transaction.atomic(durable=True):
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        yield


def detail(identity: UUID, actor: User) -> dict[str, Any]:
    with snapshot():
        post = posts(actor).filter(pk=identity).first()
        if post is None:
            raise RecordError(404)
        return dto(post, actor)


def preflight(identity: UUID, actor: User) -> None:
    post = Post.objects.filter(pk=identity, user__is_active=True).only("user_id").first()
    if post is None:
        raise RecordError(404)
    if post.user_id != actor.pk:
        raise RecordError(403)


def write(
    actor: User, data: dict[str, Any] | None, identity: UUID | None = None, *, delete: bool = False
) -> dict[str, Any] | None:
    creating = identity is None
    with transaction.atomic():
        user = User.objects.select_for_update().filter(pk=actor.pk, is_active=True).first()
        if user is None:
            raise RecordError(401)
        if creating:
            assert data is not None
            identity = data["id"]
            try:
                with transaction.atomic():
                    key = PostIdentity.objects.create(id=identity, author=user)
            except IntegrityError as exc:
                cause = exc.__cause__
                if getattr(cause, "sqlstate", None) == "23505":
                    with connection.cursor() as cursor:
                        constraints = connection.introspection.get_constraints(
                            cursor, PostIdentity._meta.db_table
                        )
                    actual = getattr(getattr(cause, "diag", None), "constraint_name", None)
                    if actual in constraints and constraints[actual]["primary_key"]:
                        raise RecordError(409, "POST_ID_CONFLICT") from None
                raise
            now = timezone.now()
            post = Post(identity=key, user=user, created_at=now, updated_at=now)
        else:
            found = Post.objects.select_for_update().filter(pk=identity).first()
            if found is None:
                raise RecordError(404)
            post = found
            if post.user_id != user.pk:
                raise RecordError(403)
        if delete:
            post.delete()
            return None
        assert data is not None
        recalc = (
            creating
            or data.get("recalculate", False)
            or (post.minutes, post.kind) != (data["minutes"], data["kind"])
        )
        if recalc:
            health = ProfileHealth.objects.filter(user=user).first()
            post.energy_kcal = calculate(
                health.weight_kg if health else None,
                health.age if health else None,
                data["minutes"],
                data["kind"],
            )
            post.energy_method = "met-gross-v1" if post.energy_kcal is not None else None
        for field in ("performed_on", "note", "minutes", "kind", "minutes_public", "kind_public"):
            setattr(post, field, data[field])
        post.updated_at = timezone.now()
        post.save()
        post.exercises.all().delete()
        for i, exercise in enumerate(data["exercises"]):
            ex = WorkoutExercise.objects.create(post=post, name=exercise["name"], position=i)
            WorkoutSet.objects.bulk_create(
                [
                    WorkoutSet(exercise=ex, position=j, **row)
                    for j, row in enumerate(exercise["sets"])
                ]
            )
        # All children and the saved response are read under the same write transaction.
        result = dto(posts(user).get(pk=post.pk), user)
    return result


def listing(username: str, actor: User, limit_text: str, cursor_text: str | None) -> dict[str, Any]:
    if not re.fullmatch(r"[a-z0-9_]{3,30}", username):
        raise RecordError(404)
    if not re.fullmatch(r"[1-9][0-9]?", limit_text) or not 1 <= int(limit_text) <= 50:
        raise RecordError(400, "INVALID_CURSOR")
    limit = int(limit_text)
    with snapshot():
        user = User.objects.filter(username=username, is_active=True).first()
        if user is None:
            raise RecordError(404)
        query = posts(actor).filter(user=user).order_by("-created_at", "-identity_id")
        if cursor_text is not None:
            try:
                if len(cursor_text) > 2048:
                    raise ValueError("Cursor length")
                value = signing.loads(cursor_text, salt="workouts.cursor.v1", max_age=86400)
                if (
                    not isinstance(value, dict)
                    or set(value) != {"v", "user", "viewer", "at", "id"}
                    or value["v"] != 1
                    or value["user"] != str(user.pk)
                    or value["viewer"] != str(actor.pk)
                ):
                    raise ValueError("Cursor context")
                at = datetime.fromisoformat(value["at"])
                last = UUID(value["id"])
                if at.tzinfo is None:
                    raise ValueError("Cursor time")
            except (signing.BadSignature, ValueError, TypeError, KeyError):
                raise RecordError(400, "INVALID_CURSOR") from None
            query = query.filter(Q(created_at__lt=at) | Q(created_at=at, identity_id__lt=last))
        rows = list(query[: limit + 1])
        more = len(rows) > limit
        visible = rows[:limit]
        next_cursor = None
        if more:
            last_post = visible[-1]
            next_cursor = signing.dumps(
                {
                    "v": 1,
                    "user": str(user.pk),
                    "viewer": str(actor.pk),
                    "at": last_post.created_at.isoformat(timespec="microseconds"),
                    "id": str(last_post.pk),
                },
                salt="workouts.cursor.v1",
            )
        return {
            "viewer_id": str(actor.pk),
            "items": [dto(row, actor) for row in visible],
            "next_cursor": next_cursor,
        }
