"""Independent scalar aggregates avoid the comment/like Cartesian product."""

from datetime import UTC, datetime
from typing import Any

from django.db.models import Count, Exists, IntegerField, OuterRef, QuerySet, Subquery, Value
from django.db.models.functions import Coalesce

from accounts.models import User
from media_assets.presentation import avatar
from social.models import Comment, Like
from workouts.models import Post


def with_social(queryset: QuerySet[Post], actor: User) -> QuerySet[Post]:
    comments = (
        Comment.objects.filter(post_id=OuterRef("pk"), user__is_active=True)
        .order_by()
        .values("post_id")
        .annotate(total=Count("pk"))
        .values("total")
    )
    likes = (
        Like.objects.filter(post_id=OuterRef("pk"), user__is_active=True)
        .order_by()
        .values("post_id")
        .annotate(total=Count("pk"))
        .values("total")
    )
    return queryset.annotate(
        comment_count=Coalesce(Subquery(comments, output_field=IntegerField()), Value(0)),
        like_count=Coalesce(Subquery(likes, output_field=IntegerField()), Value(0)),
        is_liked=Exists(
            Like.objects.filter(post_id=OuterRef("pk"), user_id=actor.pk, user__is_active=True)
        ),
    )


def post_fields(post: Post) -> dict[str, Any]:
    return {name: getattr(post, name) for name in ("comment_count", "like_count", "is_liked")}


def timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def comment_dto(comment: Comment, actor: User) -> dict[str, Any]:
    return {
        "id": str(comment.pk),
        "post_id": str(comment.post_id),
        "author": {
            "id": str(comment.user_id),
            "username": comment.user.username,
            "display_name": comment.user.display_name,
            "avatar": avatar(comment.user),
        },
        "is_owner": comment.user_id == actor.pk,
        "body": comment.body,
        "created_at": timestamp(comment.created_at),
        "updated_at": timestamp(comment.updated_at),
    }
