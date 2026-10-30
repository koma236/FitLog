"""Reserve -> immutable object write -> locked attachment; no distributed commit guesses."""

from typing import Any, Literal
from uuid import UUID, uuid4

from django.db import IntegrityError, OperationalError, transaction
from django.utils import timezone

from accounts.models import User
from media_assets.exceptions import ImageError
from media_assets.models import ImageObject, PostImage, UserAvatar
from media_assets.processing import NormalizedImage
from media_assets.signals import retire
from media_assets.storage import LocalStorage
from workouts.models import Post

TargetKind = Literal["post", "avatar"]


def preflight(actor: User, kind: TargetKind, target: UUID) -> None:
    if kind == "avatar":
        if target != actor.pk:
            raise ImageError(403, "FORBIDDEN")
        return
    post = Post.objects.filter(pk=target, user__is_active=True).only("user_id").first()
    if post is None:
        raise ImageError(404, "NOT_FOUND")
    if post.user_id != actor.pk:
        raise ImageError(403, "FORBIDDEN")


def matches(
    image: ImageObject, actor: User, kind: TargetKind, target: UUID, value: NormalizedImage
) -> bool:
    return (
        image.actor == actor.pk
        and image.target_kind == kind
        and image.target_uuid == target
        and image.digest == value.digest
        and image.size == len(value.data)
        and image.width == value.width
        and image.height == value.height
        and image.content_type == value.content_type
    )


def locked_target(actor: User, kind: TargetKind, target: UUID) -> tuple[User, Post | None]:
    user = User.objects.select_for_update().filter(pk=actor.pk, is_active=True).first()
    if user is None:
        raise ImageError(401, "AUTH_REQUIRED")
    post = None
    if kind == "post":
        post = Post.objects.select_for_update().filter(pk=target).first()
        if post is None:
            raise ImageError(404, "NOT_FOUND")
        if post.user_id != user.pk:
            raise ImageError(403, "FORBIDDEN")
    return user, post


def current_attachment(kind: TargetKind, target: UUID) -> PostImage | UserAvatar | None:
    return (
        PostImage.objects.filter(post_id=target).first()
        if kind == "post"
        else UserAvatar.objects.filter(user_id=target).first()
    )


def response(actor: User, kind: TargetKind, target: UUID) -> dict[str, Any]:
    if kind == "post":
        from workouts.service import RecordError, detail

        try:
            return detail(target, actor)
        except RecordError as exc:
            raise ImageError(exc.status, exc.code or "NOT_FOUND") from None
    from accounts.profile_service import profile_response

    user = (
        User.objects.select_related("profile_health", "avatar_attachment__object")
        .filter(pk=actor.pk, is_active=True)
        .first()
    )
    if user is None:
        raise ImageError(401, "AUTH_REQUIRED")
    return profile_response(user, actor)


def upload(
    actor: User, kind: TargetKind, target: UUID, operation: UUID, value: NormalizedImage
) -> dict[str, Any]:
    preflight(actor, kind, target)
    # A is committed before any storage mutation. Unique IDs cannot be recycled.
    with transaction.atomic(durable=True):
        try:
            with transaction.atomic():
                ImageObject.objects.create(
                    id=operation,
                    actor=actor.pk,
                    target_kind=kind,
                    target_uuid=target,
                    key=uuid4().hex + (".jpg" if value.content_type == "image/jpeg" else ".png"),
                    digest=value.digest,
                    size=len(value.data),
                    content_type=value.content_type,
                    width=value.width,
                    height=value.height,
                )
        except IntegrityError as exc:
            if (
                getattr(exc.__cause__, "sqlstate", None) != "23505"
                or not ImageObject.objects.filter(pk=operation).exists()
            ):
                raise
    # B never holds object locks while waiting for a User lock in C.
    try:
        with transaction.atomic(durable=True):
            image = ImageObject.objects.select_for_update(nowait=True).get(pk=operation)
            if not matches(image, actor, kind, target, value) or image.state == "retired":
                raise ImageError(409, "IMAGE_OPERATION_CONFLICT")
            if image.state == "pending":
                LocalStorage().put_if_absent(image.key, value.data, value.digest)
                image.written_at = timezone.now()
                image.save(update_fields=["written_at"])
    except OperationalError as exc:
        if getattr(exc.__cause__, "sqlstate", None) == "55P03":
            raise ImageError(409, "IMAGE_OPERATION_PENDING") from None
        raise
    # C rollback leaves a resumable pending object. Unknown commit does not delete it.
    with transaction.atomic(durable=True):
        locked_target(actor, kind, target)
        link = current_attachment(kind, target)
        identities = {operation}
        if link:
            identities.add(link.object_id)
        objects = {
            row.pk: row
            for row in ImageObject.objects.select_for_update()
            .filter(pk__in=identities)
            .order_by("pk")
        }
        image = objects[operation]
        if not matches(image, actor, kind, target, value):
            raise ImageError(409, "IMAGE_OPERATION_CONFLICT")
        if image.state == "attached":
            if link is None or link.object_id != operation:
                raise ImageError(409, "IMAGE_OPERATION_CONFLICT")
        elif image.state != "pending" or image.written_at is None:
            raise ImageError(409, "IMAGE_OPERATION_CONFLICT")
        else:
            if link:
                old = objects[link.object_id]
                link.object = image
                link.save(update_fields=["object"])
                retire(old)
            elif kind == "post":
                PostImage.objects.create(post_id=target, object=image)
            else:
                UserAvatar.objects.create(user_id=target, object=image)
            image.state = "attached"
            image.save(update_fields=["state"])
    return response(actor, kind, target)


def remove(actor: User, kind: TargetKind, target: UUID) -> None:
    preflight(actor, kind, target)
    with transaction.atomic(durable=True):
        locked_target(actor, kind, target)
        link = current_attachment(kind, target)
        if link:
            # pre_delete acquires the ImageObject lock and writes a durable cleanup job.
            link.delete()
