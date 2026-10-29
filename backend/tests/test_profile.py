"""FL-03: actor ownership and private response keys, before implementation."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.test import Client

if TYPE_CHECKING:
    from django.test.client import _MonkeyPatchedWSGIResponse

import pytest

from tests.test_auth import api_client, body, post, signup, token

pytestmark = pytest.mark.django_db(transaction=True)


def settings_body() -> dict[str, Any]:
    return {"display_name": "River", "bio": "自己紹介", "health": {
        "height": "175", "weight": "70", "age": 30, "formula": "male", "activity": "medium",
    }, "visibility": {k: "private" for k in ["height", "weight", "age", "formula", "activity", "bmr", "tdee", "intake"]}}


def test_owner_edit_and_other_response_excludes_private_keys() -> None:
    import json

    owner = api_client()
    registered = signup(owner, token(owner))
    owner_id = body(registered)["id"]
    response = owner.put("/api/users/me", data=json.dumps(settings_body()), content_type="application/json",
                         HTTP_X_CSRFTOKEN=token(owner), HTTP_X_PROFILE_OWNER=owner_id)
    assert response.status_code == 200
    assert body(response)["energy"] == {"bmr": 1649, "tdee": 2885, "intake": 2885}
    assert "email" not in body(response)
    viewer = api_client()
    assert signup(viewer, token(viewer), "viewer_user", "viewer@example.test").status_code == 201
    public = viewer.get("/api/users/river_user")
    assert public.status_code == 200
    assert body(public)["health"] == {}
    assert body(public)["energy"] == {}
    assert "visibility" not in body(public)


def test_other_session_cannot_save_an_old_owners_draft() -> None:
    import json

    client = api_client()
    old = body(signup(client, token(client)))["id"]
    old_csrf = token(client)
    assert post(client, "/api/auth/logout", {}, token(client)).status_code == 204
    assert signup(client, token(client), "new_owner", "new@example.test").status_code == 201
    assert client.put("/api/users/me", data=json.dumps(settings_body()), content_type="application/json", HTTP_X_CSRFTOKEN=old_csrf, HTTP_X_PROFILE_OWNER=old).status_code == 403
    response = client.put("/api/users/me", data=json.dumps(settings_body()), content_type="application/json",
                          HTTP_X_CSRFTOKEN=token(client), HTTP_X_PROFILE_OWNER=old)
    assert response.status_code == 409
    assert body(response)["code"] == "PROFILE_OWNER_CHANGED"
    from accounts.models import ProfileHealth
    assert not ProfileHealth.objects.exists()


@pytest.fixture
def actor() -> tuple[Client, str]:
    client = api_client()
    identity = body(signup(client, token(client)))
    return client, identity["id"]


def put_profile(client: Client, owner: str, data: object) -> _MonkeyPatchedWSGIResponse:
    import json
    return client.put("/api/users/me", data=json.dumps(data), content_type="application/json",
                      HTTP_X_CSRFTOKEN=token(client), HTTP_X_PROFILE_OWNER=owner)


def test_all_visibility_combinations_are_server_filtered(actor: Any) -> None:
    from itertools import product

    from accounts.models import ProfileHealth
    client, owner = actor
    viewer = api_client()
    assert signup(viewer, token(viewer), "viewer_user", "viewer@example.test").status_code == 201
    keys = ["height", "weight", "age", "formula", "activity", "bmr", "tdee", "intake"]
    for flags in product([False, True], repeat=8):
        data = settings_body()
        data["visibility"] = {k: "public" if public else "private" for k, public in zip(keys, flags, strict=True)}
        assert put_profile(client, owner, data).status_code == 200
        own = body(client.get("/api/users/me"))
        public = body(viewer.get("/api/users/river_user"))
        assert set(own["health"]) == set(keys[:5])
        assert set(own["energy"]) == set(keys[5:])
        assert set(public["health"]) == {k for k, flag in zip(keys[:5], flags[:5], strict=True) if flag}
        assert set(public["energy"]) == {k for k, flag in zip(keys[5:], flags[5:], strict=True) if flag}
        expected_health = {"height": "175.0", "weight": "70.0", "age": 30, "formula": "male", "activity": "medium"}
        expected_energy = {"bmr": 1649, "tdee": 2885, "intake": 2885}
        assert public["health"] == {k: expected_health[k] for k, flag in zip(keys[:5], flags[:5], strict=True) if flag}
        assert public["energy"] == {k: expected_energy[k] for k, flag in zip(keys[5:], flags[5:], strict=True) if flag}
        assert "email" not in public and "visibility" not in public
    assert ProfileHealth.objects.count() == 1


def test_shared_hand_calculated_vectors(actor: Any) -> None:
    import hashlib
    import json
    from pathlib import Path
    raw = Path(__file__).with_name("profile-calorie-vectors.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "1821ed52979638275e10012d7a3082cc54f26554d3c8c9c8a55e44529411febc"
    client, owner = actor
    for vector in json.loads(raw):
        data = settings_body()
        data["health"] = vector["health"]
        response = put_profile(client, owner, data)
        assert response.status_code == 200
        assert body(response)["energy"] == vector["energy"]


@pytest.mark.parametrize("path,value", [
    ("health.height", "99.9"), ("health.height", "250.1"), ("health.height", "0175"),
    ("health.height", "175."), ("health.height", " 175"), ("health.height", "175.00"),
    ("health.height", "1.75e2"), ("health.height", ""), ("health.height", 175),
    ("health.weight", "19.9"), ("health.weight", "350.1"), ("health.weight", "NaN"),
    ("health.age", True), ("health.age", 30.0), ("health.age", "30"), ("health.age", -1), ("health.age", 121),
    ("health.formula", "other"), ("health.activity", []),
    ("visibility.weight", "everyone"), ("visibility.weight", True),
    ("display_name", " "), ("display_name", "x" * 51), ("display_name", "a\x00b"),
    ("bio", "x" * 161), ("bio", "a\x00b"),
])
def test_field_validation_is_atomic(actor: Any, path: str, value: object) -> None:
    client, owner = actor
    data = settings_body()
    assert put_profile(client, owner, data).status_code == 200
    data["display_name"] = "Must not persist"
    parent, _, field = path.rpartition(".")
    if parent:
        data[parent][field] = value
    else:
        data[field] = value
    response = put_profile(client, owner, data)
    assert response.status_code == 400
    assert path in body(response)["fieldErrors"]
    assert body(client.get("/api/users/me"))["display_name"] == "River"


def test_defaults_methods_headers_unknown_input_and_bio(actor: Any) -> None:
    from accounts.models import ProfileHealth, User
    client, owner = actor
    assert not ProfileHealth.objects.exists()
    response = client.get("/api/users/me")
    assert response.status_code == 200
    assert body(response)["id"] == owner
    assert not ProfileHealth.objects.exists()
    for method in ["head", "options"]:
        response = getattr(client, method)("/api/users/me")
        assert response.status_code == 405
        assert response.headers["Allow"] == "GET, PUT"
    assert api_client().get("/api/users/me").status_code == 401
    assert client.get("/api/users/RIVER_USER").status_code == 404
    for data in [dict(settings_body(), email="secret-marker"), dict(settings_body(), health={"unknown-secret": 123})]:
        response = put_profile(client, owner, data)
        assert response.status_code == 400
        assert b"secret" not in response.content
    data = settings_body()
    data["bio"] = " \r\n\t川\r "
    response = put_profile(client, owner, data)
    assert body(response)["bio"] == " \n\t川\n "
    assert User.objects.get(pk=owner).bio == " \n\t川\n "


@pytest.mark.parametrize("raw,status", [
    ('{"bio":"a","bio":"b"}', 400), ('{"bio":"\\ud800"}', 400),
    ("[" * 3000 + "]" * 3000, 400), ("x" * 16385, 413),
])
def test_raw_json_errors_have_private_headers(actor: Any, raw: str, status: int) -> None:
    client, owner = actor
    response = client.put("/api/users/me", data=raw, content_type="application/json",
                          HTTP_X_CSRFTOKEN=token(client), HTTP_X_PROFILE_OWNER=owner)
    assert response.status_code == status
    assert response.headers["Cache-Control"] == "no-store"
    assert "Cookie" in response.headers["Vary"]
    assert body(response)["requestId"] == response.headers["X-Request-Id"]


def test_update_rollback_after_user_save(actor: Any) -> None:
    from unittest.mock import patch

    from django.db import DatabaseError

    from accounts.models import ProfileHealth, User
    client, owner = actor
    assert put_profile(client, owner, settings_body()).status_code == 200
    data = settings_body()
    data["display_name"] = "Must rollback"
    data["health"]["weight"] = "88"
    with patch.object(ProfileHealth, "save", side_effect=DatabaseError("secret-weight-88")):
        response = put_profile(client, owner, data)
    assert response.status_code == 503
    assert User.objects.get(pk=owner).display_name == "River"
    assert ProfileHealth.objects.get(user_id=owner).weight_kg == 70
    assert b"secret-weight" not in response.content
    assert response.cookies["sessionid"]["max-age"] == 0


def test_profile_commit_and_response_session_failure_keep_secrets_private(actor: Any) -> None:
    from unittest.mock import patch

    from django.contrib.sessions.backends.db import SessionStore
    from django.db import DatabaseError
    from django.test import override_settings

    client, _ = actor
    with override_settings(SESSION_SAVE_EVERY_REQUEST=True), patch.object(SessionStore, "save", side_effect=DatabaseError("session-secret-marker")):
        response = client.get("/api/users/me")
    assert response.status_code == 503
    assert response.cookies["sessionid"]["max-age"] == 0
    assert response.headers["Cache-Control"] == "no-store"
    assert "Cookie" in response.headers["Vary"]
    assert b"session-secret" not in response.content
    assert "health" not in body(response)


def test_profile_migration_preserves_existing_accounts() -> None:
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    from accounts.models import ProfileHealth, User

    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes("accounts")
    before = [("accounts", "0002_auth")]
    executor.migrate(before)
    historical = executor.loader.project_state(before).apps.get_model("accounts", "User")
    old = historical.objects.create(username="legacy_user", display_name="既存の表示名", email="", password="legacy-hash-marker")
    try:
        MigrationExecutor(connection).migrate(latest)
        current = User.objects.get(pk=old.pk)
        assert (current.username, current.display_name, current.email, current.password, current.bio) == ("legacy_user", "既存の表示名", "", "legacy-hash-marker", "")
        assert not ProfileHealth.objects.filter(user=current).exists()
    finally:
        MigrationExecutor(connection).migrate(latest)


def test_two_concurrent_updates_remain_complete(actor: Any) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections, connections

    client, owner = actor
    cookies = client.cookies.copy()
    barrier = Barrier(2)

    def update(index: int) -> tuple[str, str, str]:
        close_old_connections()
        try:
            thread_client = api_client()
            thread_client.cookies = cookies.copy()
            data = settings_body()
            data["bio"] = f"revision-{index}"
            data["health"]["weight"] = "71" if index == 1 else "72"
            data["visibility"]["weight"] = "public" if index == 1 else "private"
            csrf = token(thread_client)
            barrier.wait(timeout=10)
            import json
            response = thread_client.put("/api/users/me", data=json.dumps(data), content_type="application/json", HTTP_X_CSRFTOKEN=csrf, HTTP_X_PROFILE_OWNER=owner)
            assert response.status_code == 200
            value = body(response)
            return value["bio"], value["health"]["weight"], value["visibility"]["weight"]
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(update, [1, 2]))
    expected = {("revision-1", "71.0", "public"), ("revision-2", "72.0", "private")}
    assert set(values) == expected
    final = body(client.get("/api/users/me"))
    assert (final["bio"], final["health"]["weight"], final["visibility"]["weight"]) in expected


def test_debug_queries_and_errors_do_not_log_profile_input(actor: Any, api_log_output: Any) -> None:
    import logging
    from unittest.mock import patch

    from django.db import DatabaseError
    from django.test import override_settings

    from accounts.models import ProfileHealth

    client, owner = actor
    data = settings_body()
    data["bio"] = "private-bio-log-marker"
    logger = logging.getLogger("django.db.backends")
    previous = logger.level
    logger.setLevel(logging.DEBUG)
    try:
        with override_settings(DEBUG=True):
            assert put_profile(client, owner, data).status_code == 200
            with patch.object(ProfileHealth, "save", side_effect=DatabaseError("private-bio-log-marker")):
                response = put_profile(client, owner, data)
            assert response.status_code == 503
    finally:
        logger.setLevel(previous)
    logs = api_log_output.getvalue()
    assert "api_error status=503" in logs
    assert response.headers["X-Request-Id"] in logs
    assert "private-bio-log-marker" not in logs
    assert "private-bio-log-marker" not in response.content.decode()


def test_commit_failure_does_not_return_success_or_partial_profile(actor: Any) -> None:
    from unittest.mock import patch

    from django.db import DatabaseError, connection

    from accounts.models import ProfileHealth, User

    client, owner = actor
    with patch.object(connection, "commit", side_effect=DatabaseError("commit-secret-marker")):
        response = put_profile(client, owner, settings_body())
    assert response.status_code == 503
    assert User.objects.get(pk=owner).bio == ""
    assert not ProfileHealth.objects.filter(user_id=owner).exists()
    assert b"commit-secret" not in response.content


def test_profile_error_precedence_and_owner_headers(actor: Any) -> None:
    client, owner = actor
    csrf = token(client)
    assert client.put("/api/users/me", data="x" * 16385, content_type="text/plain").status_code == 403
    response = client.put("/api/users/me", data="x" * 16385, content_type="text/plain", HTTP_X_CSRFTOKEN=csrf)
    assert response.status_code == 413
    response = client.put("/api/users/me", data="{}", content_type="text/plain", HTTP_X_CSRFTOKEN=csrf)
    assert response.status_code == 415
    response = client.put("/api/users/me", data="{}", content_type="application/json", HTTP_X_CSRFTOKEN=csrf)
    assert response.status_code == 400
    assert body(response)["fieldErrors"] == {"_form": ["入力内容を確認してください。"]}
    response = client.put("/api/users/me", data="{", content_type="application/json", HTTP_X_CSRFTOKEN=csrf, HTTP_X_PROFILE_OWNER="00000000-0000-0000-0000-000000000000")
    assert response.status_code == 409
    assert body(response)["code"] == "PROFILE_OWNER_CHANGED"
    response = client.put("/api/users/me", data="{}", content_type="application/json; charset=latin-1", HTTP_X_CSRFTOKEN=csrf, HTTP_X_PROFILE_OWNER=owner)
    assert response.status_code == 415


def test_openapi_profile_schemas_use_declared_30_dialect() -> None:
    import json
    from pathlib import Path

    contract_path = Path("/app/contracts/openapi.json")
    if not contract_path.exists():
        contract_path = Path(__file__).resolve().parents[2] / "docs/api/openapi.json"
    contract = json.loads(contract_path.read_text())
    assert contract["openapi"] == "3.0.3"

    def walk(value: object) -> None:
        if isinstance(value, dict):
            assert "const" not in value
            assert not isinstance(value.get("type"), list)
            if value.get("nullable"):
                assert isinstance(value.get("type"), str)
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(contract)
    for name in ["formula", "activity"]:
        schema = contract["components"]["schemas"]["ProfileHealth"]["properties"][name]
        assert schema["nullable"] and None in schema["enum"]


@pytest.mark.parametrize("method", ["head", "options", "put", "delete"])
def test_other_profile_disallowed_methods_keep_private_headers(actor: Any, method: str) -> None:
    client, owner = actor
    response = client.generic(method.upper(), "/api/users/river_user", data="{}", content_type="application/json", HTTP_X_CSRFTOKEN=token(client), HTTP_X_PROFILE_OWNER=owner)
    assert response.status_code == 405
    assert response.headers["Allow"] == "GET"
    assert response.headers["Cache-Control"] == "no-store"
    assert "Cookie" in response.headers["Vary"]
    assert response.headers["X-Request-Id"]


def test_profile_success_and_auth_error_headers(actor: Any) -> None:
    client, owner = actor
    for response in [client.get("/api/users/me"), put_profile(client, owner, settings_body()), api_client().get("/api/users/river_user"), client.get("/api/users/nonexistent")]:
        assert response.headers["Cache-Control"] == "no-store"
        assert "Cookie" in response.headers["Vary"]
        assert response.headers["X-Request-Id"]
        if response.status_code == 401:
            assert response.headers["WWW-Authenticate"] == "Session"
        if response.status_code >= 400:
            assert body(response)["requestId"] == response.headers["X-Request-Id"]
