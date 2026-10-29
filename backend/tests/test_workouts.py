"""FL-04 observable HTTP and PostgreSQL contract, written before implementation."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC
from typing import Any
from uuid import uuid4

import pytest
from django.test import Client

from tests.test_auth import api_client, body, signup, token

pytestmark = pytest.mark.django_db(transaction=True)


def payload() -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "performed_on": "2024-02-29",
        "note": "フォームを意識した。",
        "exercises": [
            {"name": "ベンチプレス", "sets": [{"weight_kg": "60", "reps": 10} for _ in range(3)]}
        ],
        "energy_input": {"minutes": 30, "kind": "general"},
        "visibility": {"minutes": "private", "kind": "private"},
    }


@pytest.fixture
def actor() -> tuple[Client, str]:
    c = api_client()
    return c, body(signup(c, token(c)))["id"]


def send(c: Client, actor_id: str, method: str, path: str, data: object = None) -> Any:
    return c.generic(
        method,
        path,
        data=json.dumps(data),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token(c),
        HTTP_X_RECORD_OWNER=actor_id,
    )


def test_create_persist_full_sets_and_private_projection(actor: tuple[Client, str]) -> None:
    c, owner = actor
    data = payload()
    response = send(c, owner, "POST", "/api/posts", data)
    assert response.status_code == 201
    value = body(response)
    assert value["id"] == data["id"] and value["viewer_id"] == owner
    assert value["exercises"] == [
        {"name": "ベンチプレス", "sets": [{"weight_kg": "60.00", "reps": 10}] * 3}
    ]
    assert value["energy"] is None
    assert value["visibility"] == data["visibility"]
    assert body(c.get("/api/posts/" + data["id"])) == value
    viewer = api_client()
    assert signup(viewer, token(viewer), "viewer_user", "viewer@example.test").status_code == 201
    public = body(viewer.get("/api/posts/" + data["id"]))
    assert public["energy_input"] == {} and "visibility" not in public and "email" not in public
    assert (
        send(viewer, public["viewer_id"], "DELETE", "/api/posts/" + data["id"]).status_code == 403
    )


def test_delete_never_reuses_id_and_put_does_not_resurrect(actor: tuple[Client, str]) -> None:
    c, owner = actor
    data = payload()
    assert send(c, owner, "POST", "/api/posts", data).status_code == 201
    assert send(c, owner, "DELETE", "/api/posts/" + data["id"]).status_code == 204
    assert send(c, owner, "POST", "/api/posts", data).status_code == 409
    update = {k: v for k, v in data.items() if k != "id"} | {"recalculate": False}
    assert send(c, owner, "PUT", "/api/posts/" + data["id"], update).status_code == 404


def test_fixed_calories_and_history_rules(actor: tuple[Client, str]) -> None:
    from decimal import Decimal
    from pathlib import Path

    from accounts.models import ProfileHealth

    c, owner = actor
    health = ProfileHealth.objects.create(user_id=owner, weight_kg=Decimal("60"), age=30)
    import hashlib

    raw = Path(__file__).with_name("workout-calorie-vectors.json").read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "a0fb973ce4f6bcc907508602ffeeebb05dd2da95caa118f54bead5e14ecc17e3"
    )
    for vector in json.loads(raw):
        health.weight_kg = Decimal(vector["weight"])
        health.save()
        data = payload()
        data["energy_input"] = {"minutes": vector["minutes"], "kind": vector["kind"]}
        response = send(c, owner, "POST", "/api/posts", data)
        assert response.status_code == 201
        assert body(response)["energy"] == {"kcal": vector["kcal"], "method": "met-gross-v1"}
    health.weight_kg = Decimal("60")
    health.save()
    data = payload()
    result = send(c, owner, "POST", "/api/posts", data)
    assert body(result)["energy"]["kcal"] == 105
    health.weight_kg = Decimal("80")
    health.save()
    update = {k: v for k, v in data.items() if k != "id"} | {"recalculate": False}
    path = "/api/posts/" + data["id"]
    assert body(send(c, owner, "PUT", path, update))["energy"]["kcal"] == 105
    update["recalculate"] = True
    assert body(send(c, owner, "PUT", path, update))["energy"]["kcal"] == 140
    update["recalculate"] = False
    update["energy_input"]["minutes"] = 60
    assert body(send(c, owner, "PUT", path, update))["energy"]["kcal"] == 280
    health.age = 60
    health.save()
    update["recalculate"] = True
    assert body(send(c, owner, "PUT", path, update))["energy"] is None


def test_all_energy_projection_states(actor: tuple[Client, str]) -> None:
    from itertools import product

    c, owner = actor
    viewer = api_client()
    viewer_id = body(signup(viewer, token(viewer), "viewer_user", "viewer@example.test"))["id"]
    for minutes, kind, mp, kp in product(
        [None, 30], [None, "general"], ["private", "public"], ["private", "public"]
    ):
        data = payload()
        data["energy_input"] = {"minutes": minutes, "kind": kind}
        data["visibility"] = {"minutes": mp, "kind": kp}
        own = body(send(c, owner, "POST", "/api/posts", data))
        assert (
            own["energy_input"] == data["energy_input"] and own["visibility"] == data["visibility"]
        )
        public = body(viewer.get("/api/posts/" + data["id"]))
        expected: dict[str, object] = {}
        if minutes is not None and mp == "public":
            expected["minutes"] = minutes
        if kind is not None and kp == "public":
            expected["kind"] = kind
        assert public["energy_input"] == expected and public["viewer_id"] == viewer_id
        assert set(public) == set(own) - {"visibility"}
        assert not {"weight", "age", "health", "email"} & set(public)


@pytest.mark.parametrize(
    "path,value",
    [
        ("exercises", []),
        ("exercises", [{}] * 11),
        ("exercises.0.name", " "),
        ("exercises.0.name", "x" * 81),
        ("exercises.0.name", "a\u202eb"),
        ("exercises.0.sets", []),
        ("exercises.0.sets", [{}] * 21),
        ("exercises.0.sets.0.weight_kg", "1000"),
        ("exercises.0.sets.0.weight_kg", "-1"),
        ("exercises.0.sets.0.weight_kg", "01"),
        ("exercises.0.sets.0.weight_kg", 60),
        ("exercises.0.sets.0.weight_kg", "60\n"),
        ("exercises.0.sets.0.weight_kg", "1e1"),
        ("exercises.0.sets.0.weight_kg", "1.001"),
        ("exercises.0.sets.0.reps", 0),
        ("exercises.0.sets.0.reps", True),
        ("exercises.0.sets.0.reps", 10.0),
        ("exercises.0.sets.0.reps", 1000),
        ("performed_on", "2025-02-29"),
        ("performed_on", "9999-12-31"),
        ("performed_on", "2024-02-29\n"),
        ("note", "x" * 501),
        ("note", "a\x00b"),
        ("note", "a\u2066b"),
        ("energy_input.minutes", True),
        ("energy_input.minutes", 0),
        ("energy_input.minutes", 241),
        ("energy_input.minutes", 30.0),
        ("energy_input.kind", []),
        ("energy_input.kind", "other"),
        ("visibility.minutes", True),
        ("visibility.kind", "everyone"),
        ("id", "urn:uuid:123"),
    ],
)
def test_strict_boundaries_never_partially_save(
    actor: tuple[Client, str], path: str, value: object
) -> None:
    from workouts.models import Post, PostIdentity

    c, owner = actor
    data = payload()
    target: Any = data
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    part = parts[-1]
    if isinstance(target, list):
        target[int(part)] = value
    else:
        target[part] = value
    response = send(c, owner, "POST", "/api/posts", data)
    assert response.status_code == 400
    assert body(response)["fieldErrors"]
    assert not Post.objects.exists() and not PostIdentity.objects.exists()


def test_update_rollback_all_children_and_identity_atomic(actor: tuple[Client, str]) -> None:
    from unittest.mock import patch

    from django.db import DatabaseError

    from workouts.models import PostIdentity, WorkoutSet

    c, owner = actor
    data = payload()
    value = body(send(c, owner, "POST", "/api/posts", data))
    path = "/api/posts/" + data["id"]
    update = {k: v for k, v in data.items() if k != "id"} | {"recalculate": False}
    update["note"] = "must roll back"
    update["exercises"][0]["sets"][2]["reps"] = 11
    with patch.object(
        WorkoutSet.objects, "bulk_create", side_effect=DatabaseError("private-secret")
    ):
        response = send(c, owner, "PUT", path, update)
    assert response.status_code == 503 and b"private-secret" not in response.content
    # 503 intentionally clears the session. Reauthenticate before checking persisted state.
    from accounts.models import User

    c.force_login(User.objects.get(pk=owner))
    assert body(c.get(path)) == value
    assert PostIdentity.objects.count() == 1


def test_error_precedence_owner_guard_and_headers(actor: tuple[Client, str]) -> None:
    c, owner = actor
    data = payload()
    csrf = token(c)
    assert c.post("/api/posts", data="{}", content_type="application/json").status_code == 403
    assert api_client().get("/api/posts/not-uuid").status_code == 401
    response = send(c, str(uuid4()), "POST", "/api/posts", data)
    assert response.status_code == 409 and body(response)["code"] == "RECORD_OWNER_CHANGED"
    responses = [
        response,
        c.get("/api/posts/not-uuid"),
        api_client().get("/api/posts/" + data["id"]),
    ]
    for raw, content_type, status in [
        ("x" * 32769, "application/json", 413),
        ("{}", "text/plain", 415),
        ('{"note":"a","note":"b"}', "application/json", 400),
        ('{"x":"\\ud800"}', "application/json", 400),
        ("[" * 1000 + "]" * 1000, "application/json", 400),
    ]:
        r = c.post(
            "/api/posts",
            data=raw,
            content_type=content_type,
            HTTP_X_CSRFTOKEN=csrf,
            HTTP_X_RECORD_OWNER=owner,
        )
        assert r.status_code == status
        responses.append(r)
    for method in ["HEAD", "OPTIONS", "GET", "DELETE"]:
        r = send(c, owner, method, "/api/posts")
        assert r.status_code == 405 and r.headers["Allow"] == "POST"
        responses.append(r)
    for r in responses:
        assert (
            r.headers["Cache-Control"] == "no-store"
            and "Cookie" in r.headers["Vary"]
            and r.headers["X-Request-Id"]
        )
        if r.status_code == 401:
            assert r.headers["WWW-Authenticate"] == "Session"


def test_keyset_same_timestamp_and_context_bound_cursor(actor: tuple[Client, str]) -> None:
    from datetime import datetime

    from workouts.models import Post

    c, owner = actor
    ids = []
    for _ in range(5):
        data = payload()
        assert send(c, owner, "POST", "/api/posts", data).status_code == 201
        ids.append(data["id"])
    Post.objects.update(created_at=datetime(2024, 3, 1, 0, 0, 0, 123456, tzinfo=UTC))
    page = body(c.get("/api/users/river_user/posts?limit=2"))
    seen = [p["id"] for p in page["items"]]
    cursor = page["next_cursor"]
    viewer = api_client()
    signup(viewer, token(viewer), "viewer_user", "viewer@example.test")
    assert viewer.get("/api/users/river_user/posts", {"cursor": cursor}).status_code == 400
    assert c.get("/api/users/river_user/posts", {"cursor": cursor + "x"}).status_code == 400
    while page["next_cursor"]:
        page = body(
            c.get("/api/users/river_user/posts", {"limit": 2, "cursor": page["next_cursor"]})
        )
        seen += [p["id"] for p in page["items"]]
    assert seen == sorted(ids, reverse=True)


def test_maximum_escaped_input_and_normalized_unicode(actor: tuple[Client, str]) -> None:
    c, owner = actor
    data = payload()
    data["note"] = "😀" * 500
    data["exercises"] = [
        {"name": "😀" * 80, "sets": [{"weight_kg": "999.99", "reps": 999} for _ in range(20)]}
        for _ in range(10)
    ]
    assert len(json.dumps(data, ensure_ascii=True).encode()) < 32768
    assert send(c, owner, "POST", "/api/posts", data).status_code == 201
    data = payload()
    data["note"] = "a\r\n" * 250
    data["exercises"][0]["name"] = "\u3000種目\u3000"
    r = send(c, owner, "POST", "/api/posts", data)
    assert (
        r.status_code == 201
        and body(r)["note"] == "a\n" * 250
        and body(r)["exercises"][0]["name"] == "種目"
    )


def test_competing_creates_and_foreign_reuse_are_rejected(actor: tuple[Client, str]) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import connections

    from workouts.models import Post, PostIdentity

    c, owner = actor
    viewer = api_client()
    other = body(signup(viewer, token(viewer), "viewer_user", "viewer@example.test"))["id"]
    gate = Barrier(2)
    data = payload()

    def create(pair: tuple[Client, str]) -> int:
        client, identity = pair
        worker = api_client()
        worker.cookies = deepcopy(client.cookies)
        try:
            csrf = token(worker)
            gate.wait(timeout=10)
            return worker.post(
                "/api/posts",
                data=json.dumps(data),
                content_type="application/json",
                HTTP_X_CSRFTOKEN=csrf,
                HTTP_X_RECORD_OWNER=identity,
            ).status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(create, [(c, owner), (viewer, other)]))
    assert sorted(statuses) == [201, 409]
    assert Post.objects.count() == PostIdentity.objects.count() == 1
    winning_client, winning_owner = (c, owner) if statuses[0] == 201 else (viewer, other)
    assert (
        send(winning_client, winning_owner, "DELETE", "/api/posts/" + data["id"]).status_code == 204
    )
    assert send(c, owner, "POST", "/api/posts", data).status_code == 409
    assert send(viewer, other, "POST", "/api/posts", data).status_code == 409
    assert not Post.objects.exists() and PostIdentity.objects.count() == 1


@pytest.mark.parametrize("first_action", ["PUT", "DELETE"])
def test_post_is_rechecked_after_wait_and_recalculation_uses_latest_row(
    actor: tuple[Client, str], monkeypatch: pytest.MonkeyPatch, first_action: str
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from decimal import Decimal
    from threading import Event

    from django.db import connections

    from accounts.models import ProfileHealth
    from workouts import service
    from workouts.models import Post, PostIdentity, WorkoutSet

    c, owner = actor
    ProfileHealth.objects.create(user_id=owner, weight_kg=Decimal("60"), age=30)
    data = payload()
    assert send(c, owner, "POST", "/api/posts", data).status_code == 201
    path = "/api/posts/" + data["id"]
    update = {k: v for k, v in data.items() if k != "id"} | {"recalculate": False}
    ready, release = Event(), Event()
    original = service.preflight

    def paused(identity: Any, user: Any) -> None:
        original(identity, user)
        if __import__("threading").current_thread().name.startswith("later"):
            ready.set()
            assert release.wait(timeout=10)

    monkeypatch.setattr(service, "preflight", paused)

    def later() -> Any:
        worker = api_client()
        worker.cookies = deepcopy(c.cookies)
        try:
            return send(worker, owner, "PUT", path, update)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="later") as pool:
        pending = pool.submit(later)
        assert ready.wait(timeout=10)
        first = json.loads(json.dumps(update))
        first["energy_input"]["minutes"] = 60
        try:
            response = send(c, owner, first_action, path, first)
            assert response.status_code == (200 if first_action == "PUT" else 204)
        finally:
            release.set()
        result = pending.result(timeout=10)
    if first_action == "PUT":
        assert result.status_code == 200 and body(result)["energy"]["kcal"] == 105
    else:
        assert result.status_code == 404 and Post.objects.count() == WorkoutSet.objects.count() == 0
        assert PostIdentity.objects.count() == 1


def test_read_snapshot_keeps_children_from_before_concurrent_replace(
    actor: tuple[Client, str],
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import connection, connections

    c, owner = actor
    data = payload()
    old = body(send(c, owner, "POST", "/api/posts", data))
    path = "/api/posts/" + data["id"]
    ready, release = Event(), Event()

    def read() -> Any:
        worker = api_client()
        worker.cookies = deepcopy(c.cookies)
        stopped = False

        def execute(executor: Any, sql: str, params: Any, many: bool, context: Any) -> Any:
            nonlocal stopped
            result = executor(sql, params, many, context)
            if not stopped and sql.lstrip().startswith("SELECT") and 'FROM "workouts_post"' in sql:
                stopped = True
                ready.set()
                assert release.wait(timeout=10)
            return result

        try:
            with connection.execute_wrapper(execute):
                return worker.get(path)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(read)
        assert ready.wait(timeout=10)
        update = {k: v for k, v in data.items() if k != "id"} | {"recalculate": False}
        update["note"] = "new whole snapshot"
        update["exercises"] = [{"name": "new exercise", "sets": [{"weight_kg": "80", "reps": 8}]}]
        try:
            assert send(c, owner, "PUT", path, update).status_code == 200
        finally:
            release.set()
        response = pending.result(timeout=10)
    assert response.status_code == 200 and body(response) == old
    assert body(c.get(path))["note"] == "new whole snapshot"


@pytest.mark.parametrize(
    "instant,day,status",
    [
        ("2026-10-28T14:59:59+00:00", "2026-10-29", 400),
        ("2026-10-28T15:00:00+00:00", "2026-10-29", 201),
    ],
)
def test_jst_future_boundary(
    actor: tuple[Client, str], monkeypatch: pytest.MonkeyPatch, instant: str, day: str, status: int
) -> None:
    from datetime import datetime

    from django.utils import timezone

    c, owner = actor
    monkeypatch.setattr(timezone, "now", lambda: datetime.fromisoformat(instant))
    data = payload()
    data["performed_on"] = day
    assert send(c, owner, "POST", "/api/posts", data).status_code == status


@pytest.mark.parametrize("age,expected", [(18, None), (19, 105), (59, 105), (60, None)])
def test_calorie_eligibility_age_boundaries(
    actor: tuple[Client, str], age: int, expected: int | None
) -> None:
    from decimal import Decimal

    from accounts.models import ProfileHealth

    c, owner = actor
    ProfileHealth.objects.create(user_id=owner, weight_kg=Decimal("60"), age=age)
    response = send(c, owner, "POST", "/api/posts", payload())
    assert response.status_code == 201
    assert body(response)["energy"] == (
        None if expected is None else {"kcal": expected, "method": "met-gross-v1"}
    )


def test_disable_after_preflight_returns_401_without_update(
    actor: tuple[Client, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from accounts.models import User
    from workouts import service
    from workouts.models import Post

    c, owner = actor
    data = payload()
    assert send(c, owner, "POST", "/api/posts", data).status_code == 201
    original = service.preflight

    def disable(identity: Any, user: Any) -> None:
        original(identity, user)
        User.objects.filter(pk=owner).update(is_active=False)

    monkeypatch.setattr(service, "preflight", disable)
    update = {k: v for k, v in data.items() if k != "id"} | {"recalculate": False}
    update["note"] = "must not save"
    response = send(c, owner, "PUT", "/api/posts/" + data["id"], update)
    assert response.status_code == 401 and response.headers["WWW-Authenticate"] == "Session"
    assert Post.objects.get(pk=data["id"]).note == data["note"]


def test_create_commit_failure_rolls_back_identity_and_input_is_not_logged(
    actor: tuple[Client, str], api_log_output: Any
) -> None:
    from unittest.mock import patch

    from django.db import DatabaseError, connection

    from workouts.models import Post, PostIdentity

    c, owner = actor
    data = payload()
    data["note"] = "private-workout-marker"
    with patch.object(connection, "commit", side_effect=DatabaseError("private-workout-marker")):
        response = send(c, owner, "POST", "/api/posts", data)
    assert response.status_code == 503 and "private-workout-marker" not in response.content.decode()
    assert not Post.objects.exists() and not PostIdentity.objects.exists()
    logs = api_log_output.getvalue()
    assert "api_error status=503" in logs and "private-workout-marker" not in logs


def test_check_violation_is_not_reported_as_id_conflict(actor: tuple[Client, str]) -> None:
    from unittest.mock import patch

    from django.db import connection

    from workouts.models import WorkoutSet

    c, owner = actor

    def invalid(rows: Any) -> None:
        row = rows[0]
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO workouts_workoutset (id, exercise_id, position, weight_kg, reps) VALUES (%s,%s,0,60,0)",
                [str(uuid4()), str(row.exercise_id)],
            )

    with patch.object(WorkoutSet.objects, "bulk_create", side_effect=invalid):
        response = send(c, owner, "POST", "/api/posts", payload())
    assert response.status_code == 500 and body(response)["code"] == "INTERNAL_ERROR"


def test_malformed_actor_header_has_documented_code(actor: tuple[Client, str]) -> None:
    c, owner = actor
    for header in ["", "urn:uuid:" + owner, "{" + owner + "}", owner.replace("-", "")]:
        r = send(c, header, "POST", "/api/posts", payload())
        assert r.status_code == 400 and body(r)["code"] == "INVALID_REQUEST"
