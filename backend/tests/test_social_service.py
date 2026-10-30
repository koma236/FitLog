"""Real PostgreSQL tests: fixed counts, tombstones, visibility, cursor and locks."""

import importlib
import importlib.util
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from workouts.models import Post, PostIdentity

pytestmark = pytest.mark.django_db(transaction=True)


def social() -> Any:
    assert importlib.util.find_spec("social.service") is not None, "social persistence is missing"
    return importlib.import_module("social.service")


def key(number: int) -> UUID:
    return UUID(f"00000000-0000-4000-8000-{number:012x}")


@pytest.fixture
def sample() -> tuple[User, User, User, Post]:
    actors = [
        User.objects.create(
            username=f"actor_{i}", email=f"actor_{i}@example.test", display_name=f"Actor {i}"
        )
        for i in range(3)
    ]
    now = datetime(2026, 1, 1, tzinfo=UTC)
    identity = PostIdentity.objects.create(id=key(1), author=actors[0])
    post = Post.objects.create(
        identity=identity,
        user=actors[0],
        performed_on=now.date(),
        note="unchanged",
        created_at=now,
        updated_at=now,
    )
    return actors[0], actors[1], actors[2], post


def test_crud_counts_and_tombstone(sample: tuple[User, User, User, Post]) -> None:
    a, b, c, post = sample
    service = social()
    created = service.write_comment(b, post.pk, {"id": key(101), "body": "first"})
    assert created["comment_count"] == 1
    assert created["comment"]["author"]["id"] == str(b.pk)
    for actor in (a, c):
        with pytest.raises(service.SocialError) as denied:
            service.preflight_comment(key(101), actor)
        assert denied.value.status == 403
    updated = service.write_comment(b, post.pk, {"body": "edited"}, key(101))
    assert updated["comment_count"] == 1
    assert updated["comment"]["created_at"] == created["comment"]["created_at"]
    assert updated["comment"]["body"] == "edited"
    assert service.write_comment(b, post.pk, None, key(101), delete=True) is None
    with pytest.raises(service.SocialError) as conflict:
        service.write_comment(b, post.pk, {"id": key(101), "body": "resurrection"})
    assert (conflict.value.status, conflict.value.code) == (409, "COMMENT_ID_CONFLICT")
    from social.models import Comment, CommentIdentity

    assert Comment.objects.count() == 0 and CommentIdentity.objects.count() == 1
    post.refresh_from_db()
    assert post.note == "unchanged"


def test_independent_counts_and_active_visibility(sample: tuple[User, User, User, Post]) -> None:
    a, b, c, post = sample
    service = social()
    service.write_comment(b, post.pk, {"id": key(101), "body": "one"})
    service.write_comment(c, post.pk, {"id": key(102), "body": "two"})
    for actor in (a, b, c):
        service.write_like(actor, post.pk, enabled=True)
        service.write_like(actor, post.pk, enabled=True)
    from social.presentation import post_fields, with_social

    with CaptureQueriesContext(connection) as captured:
        fields = [post_fields(row) for row in with_social(Post.objects.all(), b)]
    assert len(captured) == 1
    assert fields == [{"comment_count": 2, "like_count": 3, "is_liked": True}]
    b.is_active = False
    b.save(update_fields=["is_active"])
    actions: list[Callable[[], object]] = [
        lambda: service.detail(key(101), c),
        lambda: service.preflight_comment(key(101), c),
    ]
    for action in actions:
        with pytest.raises(service.SocialError) as hidden:
            action()
        assert hidden.value.status == 404
    page = service.listing(post.pk, c, "20", None)
    assert page["comment_count"] == 1 and [item["id"] for item in page["items"]] == [str(key(102))]
    assert post_fields(with_social(Post.objects.all(), c).get()) == {
        "comment_count": 1,
        "like_count": 2,
        "is_liked": True,
    }
    b.is_active = True
    b.save(update_fields=["is_active"])
    assert service.listing(post.pk, c, "20", None)["comment_count"] == 2
    assert service.write_like(b, post.pk, enabled=False)["like_count"] == 2
    assert service.write_like(b, post.pk, enabled=False)["like_count"] == 2
    with pytest.raises(AttributeError):
        post_fields(post)


def test_cursor_tuple_survives_deleted_boundary(sample: tuple[User, User, User, Post]) -> None:
    a, b, c, post = sample
    service = social()
    from social.models import Comment

    for number in range(101, 106):
        service.write_comment(b, post.pk, {"id": key(number), "body": str(number)})
    Comment.objects.update(created_at=datetime(2026, 1, 2, tzinfo=UTC))
    first = service.listing(post.pk, c, "2", None)
    assert [row["id"] for row in first["items"]] == [str(key(101)), str(key(102))]
    service.write_comment(b, post.pk, None, key(102), delete=True)
    second = service.listing(post.pk, c, "2", first["next_cursor"])
    third = service.listing(post.pk, c, "2", second["next_cursor"])
    assert [row["id"] for row in second["items"]] == [str(key(103)), str(key(104))]
    assert [row["id"] for row in third["items"]] == [str(key(105))]
    assert third["next_cursor"] is None
    for viewer, cursor, limit in [
        (a, first["next_cursor"], "2"),
        (c, first["next_cursor"] + "x", "2"),
        (c, None, "0"),
    ]:
        with pytest.raises(service.SocialError) as invalid:
            service.listing(post.pk, viewer, limit, cursor)
        assert (invalid.value.status, invalid.value.code) == (400, "INVALID_CURSOR")


def test_rollback_and_user_parent_cascades(sample: tuple[User, User, User, Post]) -> None:
    a, b, c, post = sample
    service = social()
    from social.models import Comment, CommentIdentity, Like

    with pytest.raises(RuntimeError), transaction.atomic():
        service.write_comment(b, post.pk, {"id": key(101), "body": "rollback"})
        raise RuntimeError("rollback")
    assert not CommentIdentity.objects.exists() and not Comment.objects.exists()
    service.write_comment(b, post.pk, {"id": key(101), "body": "saved"})
    service.write_like(b, post.pk, enabled=True)
    b.delete()
    assert not Comment.objects.exists() and not Like.objects.exists()
    assert CommentIdentity.objects.get(pk=key(101)).author_id is None
    service.write_comment(c, post.pk, {"id": key(102), "body": "saved"})
    service.write_like(c, post.pk, enabled=True)
    post.delete()
    assert not Comment.objects.exists() and not Like.objects.exists()
    assert CommentIdentity.objects.count() == 2
    actions: list[Callable[[], object]] = [
        lambda: service.write_comment(c, key(1), {"id": key(103), "body": "gone"}),
        lambda: service.write_like(c, key(1), enabled=True),
    ]
    for action in actions:
        with pytest.raises(service.SocialError) as absent:
            action()
        assert absent.value.status == 404


def test_actual_database_constraints(sample: tuple[User, User, User, Post]) -> None:
    a, b, c, post = sample
    service = social()
    from social.models import Comment, Like

    service.write_comment(b, post.pk, {"id": key(101), "body": "saved"})
    for invalid in ("", "x" * 501):
        with pytest.raises(IntegrityError), transaction.atomic():
            Comment.objects.filter(pk=key(101)).update(body=invalid)
    service.write_like(b, post.pk, enabled=True)
    with pytest.raises(IntegrityError), transaction.atomic():
        Like.objects.create(post=post, user=b)


def test_concurrent_like_is_unique_and_comment_id_is_not_reused(
    sample: tuple[User, User, User, Post],
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import connections

    a, b, c, post = sample
    service = social()
    from social.models import Comment, CommentIdentity, Like

    gate = Barrier(2)

    def write(kind: str) -> int:
        try:
            gate.wait(timeout=10)
            if kind == "like":
                service.write_like(b, post.pk, enabled=True)
            else:
                service.write_comment(b, post.pk, {"id": key(101), "body": "fixed"})
            return 200
        except service.SocialError as exc:
            assert exc.code == "COMMENT_ID_CONFLICT"
            return int(exc.status)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(write, ["like", "like"])) == [200, 200]
        assert sorted(pool.map(write, ["comment", "comment"])) == [200, 409]
    assert Like.objects.count() == Comment.objects.count() == CommentIdentity.objects.count() == 1


@pytest.mark.parametrize(
    "lock_kind,change,wanted",
    [
        ("user", "inactive", 401),
        ("post", "delete", 404),
        ("post", "inactive", 404),
        ("post", "none", 200),
    ],
)
def test_writer_waits_for_database_lock_then_rechecks_latest_state(
    sample: tuple[User, User, User, Post], lock_kind: str, change: str, wanted: int
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from queue import Queue
    from time import monotonic, sleep

    from django.db import connections

    a, b, c, post = sample
    service = social()
    from social.models import Like

    pids: Queue[int] = Queue()

    def later() -> int:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                pids.put(cursor.fetchone()[0])
            service.write_like(b, post.pk, enabled=True)
            return 200
        except service.SocialError as exc:
            return int(exc.status)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            if lock_kind == "user":
                User.objects.select_for_update().get(pk=b.pk)
            else:
                Post.objects.select_for_update().get(pk=post.pk)
            pending = pool.submit(later)
            pid = pids.get(timeout=10)
            deadline = monotonic() + 10
            while True:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", [pid]
                    )
                    row = cursor.fetchone()
                if row and row[0] == "Lock":
                    break
                assert monotonic() < deadline, (
                    "independent PostgreSQL connection never waited on the held lock"
                )
                sleep(0.01)
            assert not pending.done()
            if change == "delete":
                post.delete()
            elif change == "inactive":
                User.objects.filter(pk=b.pk if lock_kind == "user" else a.pk).update(
                    is_active=False
                )
        assert pending.result(timeout=10) == wanted
    assert Like.objects.count() == (1 if wanted == 200 else 0)


@pytest.mark.parametrize("first,last,expected", [(True, False, False), (False, True, True)])
def test_like_last_lock_holder_determines_fixed_state(
    sample: tuple[User, User, User, Post], first: bool, last: bool, expected: bool
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from queue import Queue
    from time import monotonic, sleep

    from django.db import connections

    a, b, c, post = sample
    service = social()
    from social.models import Like

    pids: Queue[int] = Queue()

    def later() -> dict[str, Any]:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                pids.put(cursor.fetchone()[0])
            return dict(service.write_like(c, post.pk, enabled=last))
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            service.write_like(c, post.pk, enabled=first)
            pending = pool.submit(later)
            pid = pids.get(timeout=10)
            deadline = monotonic() + 10
            while True:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", [pid]
                    )
                    row = cursor.fetchone()
                if row and row[0] == "Lock":
                    break
                assert monotonic() < deadline
                sleep(0.01)
        result = pending.result(timeout=10)
    assert result == {
        "viewer_id": str(c.pk),
        "post_id": str(post.pk),
        "like_count": int(expected),
        "is_liked": expected,
    }
    assert Like.objects.count() == int(expected)


def test_non_primary_integrity_error_is_not_reported_as_id_conflict(
    sample: tuple[User, User, User, Post],
) -> None:
    a, b, c, post = sample
    service = social()
    from social.models import Comment, CommentIdentity

    with pytest.raises(IntegrityError):
        service.write_comment(b, post.pk, {"id": key(101), "body": ""})
    assert Comment.objects.count() == CommentIdentity.objects.count() == 0


def test_page_count_items_share_snapshot_during_concurrent_delete(
    sample: tuple[User, User, User, Post],
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import connections

    a, b, c, post = sample
    service = social()
    service.write_comment(b, post.pk, {"id": key(101), "body": "before"})
    ready, release = Event(), Event()

    def read() -> dict[str, Any]:
        stopped = False

        def pause(execute: Any, sql: str, params: Any, many: bool, context: Any) -> Any:
            nonlocal stopped
            result = execute(sql, params, many, context)
            if not stopped and "COUNT(*)" in sql and "social_comment" in sql:
                stopped = True
                ready.set()
                assert release.wait(timeout=10)
            return result

        try:
            with connection.execute_wrapper(pause):
                return dict(service.listing(post.pk, c, "20", None))
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(read)
        assert ready.wait(timeout=10)
        try:
            service.write_comment(b, post.pk, None, key(101), delete=True)
        finally:
            release.set()
        result = pending.result(timeout=10)
    assert result["comment_count"] == 1
    assert [(row["id"], row["body"]) for row in result["items"]] == [(str(key(101)), "before")]
    assert service.listing(post.pk, c, "20", None)["comment_count"] == 0


def test_parent_deactivated_after_insert_rolls_back_with_not_found(
    sample: tuple[User, User, User, Post],
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connections

    a, b, c, post = sample
    service = social()
    from social.models import Comment, CommentIdentity

    def deactivate() -> None:
        try:
            User.objects.filter(pk=a.pk).update(is_active=False)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:

        def after_insert(execute: Any, sql: str, params: Any, many: bool, context: Any) -> Any:
            result = execute(sql, params, many, context)
            if sql.startswith('INSERT INTO "social_comment"'):
                pool.submit(deactivate).result(timeout=10)
            return result

        with connection.execute_wrapper(after_insert), pytest.raises(service.SocialError) as hidden:
            service.write_comment(b, post.pk, {"id": key(101), "body": "must rollback"})
    assert hidden.value.status == 404
    assert not Comment.objects.exists() and not CommentIdentity.objects.exists()


def test_cursor_exact_expiry_boundary(
    sample: tuple[User, User, User, Post],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    a, b, c, post = sample
    service = social()
    for number in (101, 102):
        service.write_comment(b, post.pk, {"id": key(number), "body": str(number)})
    issued_at = 1_740_000_000
    monkeypatch.setattr("django.core.signing.time.time", lambda: issued_at)
    cursor = service.listing(post.pk, c, "1", None)["next_cursor"]
    monkeypatch.setattr("django.core.signing.time.time", lambda: issued_at + 86400)
    assert [row["id"] for row in service.listing(post.pk, c, "1", cursor)["items"]] == [
        str(key(102))
    ]
    monkeypatch.setattr("django.core.signing.time.time", lambda: issued_at + 86401)
    with pytest.raises(service.SocialError) as expired:
        service.listing(post.pk, c, "1", cursor)
    assert (expired.value.status, expired.value.code) == (400, "INVALID_CURSOR")


def test_fifty_post_social_projection_stays_one_query(
    sample: tuple[User, User, User, Post],
) -> None:
    from social.models import Comment, CommentIdentity, Like
    from social.presentation import post_fields, with_social

    a, b, c, post = sample
    now = datetime(2026, 1, 2, tzinfo=UTC)
    for number in range(50):
        identity = PostIdentity.objects.create(id=key(1000 + number), author=a)
        row = Post.objects.create(
            identity=identity,
            user=a,
            performed_on=now.date(),
            note="",
            created_at=now,
            updated_at=now,
        )
        for author, offset in ((b, 0), (c, 1)):
            comment_key = CommentIdentity.objects.create(
                id=key(2000 + number * 2 + offset), author=author, post_uuid=row.pk
            )
            Comment.objects.create(
                identity=comment_key,
                post=row,
                user=author,
                body="fixed",
                created_at=now,
                updated_at=now,
            )
        for author in (a, b, c):
            Like.objects.create(post=row, user=author)
    with CaptureQueriesContext(connection) as captured:
        values = [post_fields(row) for row in with_social(Post.objects.exclude(pk=post.pk), b)]
    assert len(captured) == 1
    assert values == [{"comment_count": 2, "like_count": 3, "is_liked": True}] * 50


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
@pytest.mark.parametrize(
    "held,change,wanted",
    [
        ("user", "actor_inactive", 401),
        ("post", "parent_delete", 404),
        ("post", "parent_inactive", 404),
        ("post", "target_delete", 404),
        ("comment", "target_delete", 404),
        ("comment", "earlier_update", 200),
    ],
)
def test_comment_write_rechecks_after_real_lock_wait(
    sample: tuple[User, User, User, Post],
    method: str,
    held: str,
    change: str,
    wanted: int,
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from queue import Queue
    from time import monotonic, sleep

    from django.db import connections

    from social.models import Comment, CommentIdentity

    a, b, c, post = sample
    service = social()
    original = service.write_comment(b, post.pk, {"id": key(501), "body": "original"})
    original_created_at = original["comment"]["created_at"]
    post_id = post.pk
    # The view's preflight succeeds before the independent write blocks.
    assert service.preflight_comment(key(501), b) == post_id
    pids: Queue[int] = Queue()

    def later() -> tuple[int, dict[str, Any] | None]:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                pids.put(cursor.fetchone()[0])
            saved = service.write_comment(
                b,
                post_id,
                {"body": "last write"} if method == "PUT" else None,
                key(501),
                delete=method == "DELETE",
            )
            return 200, saved
        except service.SocialError as exc:
            return int(exc.status), None
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            if held == "user":
                User.objects.select_for_update().get(pk=b.pk)
            elif held == "post":
                Post.objects.select_for_update().get(pk=post_id)
            else:
                Comment.objects.select_for_update().get(pk=key(501))
            pending = pool.submit(later)
            pid = pids.get(timeout=10)
            deadline = monotonic() + 10
            while True:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_stat_clear_snapshot()")
                    cursor.execute(
                        "SELECT wait_event_type, query FROM pg_stat_activity WHERE pid = %s", [pid]
                    )
                    row = cursor.fetchone()
                if row and row[0] == "Lock":
                    table = {
                        "user": '"accounts_user"',
                        "post": '"workouts_post"',
                        "comment": '"social_comment"',
                    }[held]
                    assert table in row[1] and "FOR UPDATE" in row[1]
                    break
                assert monotonic() < deadline, (
                    "writer did not enter the expected PostgreSQL row lock wait"
                )
                sleep(0.01)
            assert not pending.done()
            if change == "actor_inactive":
                User.objects.filter(pk=b.pk).update(is_active=False)
            elif change == "parent_delete":
                post.delete()
            elif change == "parent_inactive":
                User.objects.filter(pk=a.pk).update(is_active=False)
            elif change == "target_delete":
                Comment.objects.filter(pk=key(501)).delete()
            else:
                Comment.objects.filter(pk=key(501)).update(body="earlier write")
        status, result = pending.result(timeout=10)
    assert status == wanted
    assert CommentIdentity.objects.filter(pk=key(501)).count() == 1
    if wanted != 200:
        assert result is None
        if change in ("parent_delete", "target_delete"):
            assert not Comment.objects.filter(pk=key(501)).exists()
        else:
            assert Comment.objects.get(pk=key(501)).body == "original"
    elif method == "PUT":
        assert result is not None
        assert result["comment"]["body"] == "last write"
        assert result["comment"]["created_at"] == original_created_at
        assert result["comment_count"] == 1
        assert Comment.objects.get(pk=key(501)).body == "last write"
    else:
        assert result is None and not Comment.objects.filter(pk=key(501)).exists()
