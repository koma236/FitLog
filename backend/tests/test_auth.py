"""FL-02: real HTTP/session/CSRF invariants, independent of view implementation."""
from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

import pytest
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import Client
from django.utils import timezone

if TYPE_CHECKING:
    from django.test.client import _MonkeyPatchedWSGIResponse

pytestmark = pytest.mark.django_db(transaction=True)
PASSWORD = "River-lantern-42!pine"


@pytest.fixture(autouse=True)
def fixed_auth_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("django.utils.timezone.now", lambda: datetime(2026, 10, 29, 12, 34, 56, tzinfo=UTC))


def body(response: _MonkeyPatchedWSGIResponse) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(response.content))


def api_client() -> Client:
    return Client(enforce_csrf_checks=True, raise_request_exception=False, SERVER_NAME="localhost")


def token(client: Client) -> str:
    response = client.get("/api/auth/csrf")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    return str(body(response)["csrf_token"])


def post(client: Client, path: str, body: Mapping[str, object], csrf: str) -> _MonkeyPatchedWSGIResponse:
    return client.post(path, data=json.dumps(body), content_type="application/json", HTTP_X_CSRFTOKEN=csrf)


def signup(client: Client, csrf: str, username: str = "river_user", email: str = "river@example.test") -> _MonkeyPatchedWSGIResponse:
    return post(client, "/api/auth/signup", {"username": username, "display_name": "River", "email": email, "password": PASSWORD}, csrf)


def test_registration_persists_user_and_session_and_logout_invalidates() -> None:
    client = api_client()
    csrf = token(client)
    created = signup(client, csrf)
    assert created.status_code == 201
    user = get_user_model().objects.get(username="river_user")
    assert user.check_password(PASSWORD)
    assert user.password != PASSWORD
    assert set(body(created)) == {"id", "username", "display_name", "email"}
    assert body(created)["id"] == str(user.pk)
    assert client.get("/api/auth/me").json() == body(created)
    key = client.cookies["sessionid"].value
    assert Session.objects.get(session_key=key).expire_date <= timezone.now() + timedelta(days=7, seconds=2)
    stale = api_client()
    stale.cookies["sessionid"] = key
    # Login rotates CSRF; the pre-login token must no longer authorize mutations.
    assert post(client, "/api/auth/logout", {}, csrf).status_code == 403
    assert post(client, "/api/auth/logout", {}, token(client)).status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    assert stale.get("/api/auth/me").status_code == 401
    assert not Session.objects.filter(session_key=key).exists()


def test_registration_and_login_require_csrf() -> None:
    client = api_client()
    for path in ["/api/auth/signup", "/api/auth/login", "/api/auth/logout"]:
        response = client.post(path, data="{}", content_type="application/json")
        assert response.status_code == 403
        assert body(response)["code"] == "CSRF_FAILED"
        assert response.headers["Cache-Control"] == "no-store"


def test_unknown_login_and_wrong_password_are_indistinguishable() -> None:
    client = api_client()
    csrf = token(client)
    assert signup(client, csrf).status_code == 201
    assert post(client, "/api/auth/logout", {}, token(client)).status_code == 204
    csrf = token(client)
    responses = [post(client, "/api/auth/login", {"email": email, "password": "incorrect-42!password"}, csrf) for email in ["unknown@example.test", "river@example.test"]]
    for response in responses:
        assert response.status_code == 401
        assert body(response)["code"] == "INVALID_CREDENTIALS"
        assert PASSWORD not in response.content.decode()
    assert body(responses[0])["message"] == body(responses[1])["message"]


def test_ten_attempts_share_signup_login_window(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed = datetime(2026, 10, 29, 12, 34, 20, tzinfo=UTC)
    monkeypatch.setattr("time.time", lambda: fixed.timestamp())
    monkeypatch.setattr("django.utils.timezone.now", lambda: fixed)
    client = api_client()
    csrf = token(client)
    for _ in range(10):
        response = post(client, "/api/auth/login", {"email": "nobody@example.test", "password": PASSWORD}, csrf)
        assert response.status_code == 401
    response = post(client, "/api/auth/signup", {}, csrf)
    assert response.status_code == 429
    assert 1 <= int(response.headers["Retry-After"]) <= 60


@pytest.mark.parametrize("data", [
    {}, {"email": "bad", "password": PASSWORD},
    {"email": "é@example.test", "password": PASSWORD},
    {"email": "a" * 255, "password": PASSWORD},
    {"email": "river@example.test", "password": ""},
    {"email": "river@example.test", "password": "a" * 129},
    {"email": "river@example.test", "password": 42},
    {"email": "river@example.test", "password": PASSWORD, "extra": True},
])
def test_login_rejects_malformed_input_before_hash(data: dict[str, object]) -> None:
    from unittest.mock import patch

    client = api_client()
    csrf = token(client)
    with patch("accounts.backends.User.set_password", side_effect=AssertionError("must not hash")):
        response = post(client, "/api/auth/login", data, csrf)
    assert response.status_code == 400
    assert body(response)["code"] == "VALIDATION_ERROR"


def test_signup_normalization_and_duplicate_priority() -> None:
    from accounts.models import AuthRateLimit, User

    client = api_client()
    response = post(client, "/api/auth/signup", {
        "username": " River_User ", "display_name": "  川  ",
        "email": " River@Example.test ", "password": PASSWORD,
    }, token(client))
    assert response.status_code == 201
    assert body(response)["username"] == "river_user"
    assert body(response)["display_name"] == "川"
    assert User.objects.get().email == "river@example.test"
    assert post(client, "/api/auth/logout", {}, token(client)).status_code == 204
    csrf = token(client)
    response = signup(client, csrf, "RIVER_USER", "RIVER@EXAMPLE.TEST")
    assert response.status_code == 409
    assert body(response)["code"] == "DUPLICATE_USERNAME"
    response = signup(client, csrf, "other_user", "RIVER@EXAMPLE.TEST")
    assert response.status_code == 409
    assert body(response)["fieldErrors"] == {"email": ["すでに使われています。"]}
    assert AuthRateLimit.objects.get().count == 3


@pytest.mark.parametrize("field,value", [
    ("username", "me"), ("username", "search"), ("username", "a-b"),
    ("username", "ab"), ("username", "a" * 31),
    ("display_name", "  "), ("display_name", "a\x00b"), ("display_name", "川" * 51),
    ("password", "a" * 11), ("password", "a" * 129),
    ("password", "123456789012345"), ("password", "password1234"),
    ("password", "river_user@example.test"),
])
def test_signup_validation(field: str, value: str) -> None:
    from accounts.models import User

    client = api_client()
    data = {"username": "river_user", "display_name": "River", "email": "river@example.test", "password": PASSWORD}
    data[field] = value
    response = post(client, "/api/auth/signup", data, token(client))
    assert response.status_code == 400
    assert field in body(response)["fieldErrors"]
    assert not User.objects.exists()


def test_fixed_session_expiry_and_already_authenticated(monkeypatch: pytest.MonkeyPatch) -> None:
    from accounts.models import AuthRateLimit

    start = datetime(2026, 10, 29, 12, 34, 56, tzinfo=UTC)
    now = start
    monkeypatch.setattr("django.utils.timezone.now", lambda: now)
    client = api_client()
    # anonymous session makes key rotation observable
    session = client.session
    session["anonymous"] = True
    session.save()
    old_key = session.session_key
    csrf = token(client)
    assert signup(client, csrf).status_code == 201
    key = client.cookies["sessionid"].value
    assert key != old_key
    assert not Session.objects.filter(session_key=old_key).exists()
    expiry = start + timedelta(days=7)
    assert Session.objects.get(session_key=key).expire_date == expiry
    now = start + timedelta(days=1)
    session = client.session
    session["other"] = True
    session.save()
    assert Session.objects.get(session_key=key).expire_date == expiry
    csrf = token(client)
    for path in ["signup", "login"]:
        response = post(client, f"/api/auth/{path}", {}, csrf)
        assert response.status_code == 409
        assert body(response)["code"] == "ALREADY_AUTHENTICATED"
        assert client.cookies["sessionid"].value == key
        assert Session.objects.get(session_key=key).expire_date == expiry
    assert AuthRateLimit.objects.order_by("window_start").last() is not None
    now = expiry - timedelta(microseconds=1)
    assert client.get("/api/auth/me").status_code == 200
    now = expiry
    assert client.get("/api/auth/me").status_code == 401


def test_counter_method_csrf_body_limit_and_next_window(monkeypatch: pytest.MonkeyPatch) -> None:
    from accounts.models import AuthRateLimit

    now = datetime(2026, 10, 29, 12, 34, 56, tzinfo=UTC)
    monkeypatch.setattr("django.utils.timezone.now", lambda: now)
    client = api_client()
    csrf = token(client)
    assert client.get("/api/auth/login").status_code == 405
    assert client.put("/api/auth/login", data="{}").status_code == 403
    assert client.put("/api/auth/login", data="{}", HTTP_X_CSRFTOKEN=csrf).status_code == 405
    assert not AuthRateLimit.objects.exists()
    for _ in range(10):
        assert post(client, "/api/auth/login", {}, csrf).status_code == 400
    response = post(client, "/api/auth/signup", {}, csrf)
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "4"
    now += timedelta(seconds=4)
    response = client.post("/api/auth/login", data="x" * 16385, content_type="application/json", HTTP_X_CSRFTOKEN=csrf)
    assert response.status_code == 413
    assert body(response)["code"] == "PAYLOAD_TOO_LARGE"
    assert sorted(AuthRateLimit.objects.values_list("count", flat=True)) == [1, 11]


def test_unknown_backend_hash_and_legacy_email_and_inactive() -> None:
    from unittest.mock import patch

    from accounts.models import User

    user = User.objects.create_user("river_user", "river@example.test", PASSWORD, display_name="River")
    User.objects.filter(pk=user.pk).update(email="River@Example.test")
    client = api_client()
    csrf = token(client)
    assert post(client, "/api/auth/login", {"email": " river@example.test ", "password": PASSWORD}, csrf).status_code == 200
    assert post(client, "/api/auth/logout", {}, token(client)).status_code == 204
    csrf = token(client)
    original = User.set_password
    with patch.object(User, "set_password", autospec=True, side_effect=original) as hasher:
        unknown = post(client, "/api/auth/login", {"email": "nobody@example.test", "password": PASSWORD}, csrf)
        assert hasher.call_count == 1
    User.objects.filter(pk=user.pk).update(is_active=False)
    inactive = post(client, "/api/auth/login", {"email": "river@example.test", "password": PASSWORD}, csrf)
    for response in [unknown, inactive]:
        assert response.status_code == 401
        assert body(response)["code"] == "INVALID_CREDENTIALS"
        assert response.headers["WWW-Authenticate"] == "Session"
    assert {k: v for k, v in body(unknown).items() if k != "requestId"} == {
        k: v for k, v in body(inactive).items() if k != "requestId"
    }


def test_counter_failure_and_session_save_failure_are_safe_503() -> None:
    from unittest.mock import patch

    from django.db import OperationalError

    from accounts.models import User

    client = api_client()
    csrf = token(client)
    with patch("accounts.views.consume_attempt", side_effect=OperationalError("secret db")), patch(
        "accounts.models.User.set_password", side_effect=AssertionError("must not hash"),
    ):
        response = signup(client, csrf)
    assert response.status_code == 503
    assert not User.objects.exists()
    from django.contrib.sessions.backends.db import SessionStore

    original_save = SessionStore.save

    def response_save_failure(store: SessionStore, must_create: bool = False) -> None:
        if must_create:
            original_save(store, must_create=True)
        else:
            raise OperationalError("secret db")

    with patch.object(SessionStore, "save", response_save_failure):
        response = signup(client, csrf)
    assert response.status_code == 503
    assert body(response)["code"] == "SERVICE_UNAVAILABLE"
    assert response.headers["Cache-Control"] == "no-store"
    assert body(response)["requestId"] == response.headers["X-Request-Id"]
    assert response.cookies["sessionid"]["max-age"] == 0
    assert User.objects.count() == 1  # account commit preceded response-time session failure


def test_no_store_secret_nonexposure_and_cookie_attributes(api_log_output: object) -> None:
    from io import StringIO

    assert isinstance(api_log_output, StringIO)
    client = api_client()
    csrf = token(client)
    secret = "SECRET-password-cookie-marker"
    client.cookies["sessionid"] = secret
    response = post(client, "/api/auth/login", {"email": "secret-marker@example.test", "password": secret}, csrf)
    assert response.status_code == 401
    assert response.headers["Cache-Control"] == "no-store"
    logs = api_log_output.getvalue()
    assert "api_error status=401" in logs
    assert response.headers["X-Request-Id"] in logs
    for value in [secret, "secret-marker@example.test", csrf]:
        assert value not in logs
        assert value not in response.content.decode()
    client = api_client()
    created = signup(client, token(client))
    assert created.status_code == 201
    for name in ["sessionid", "csrftoken"]:
        assert client.cookies[name]["httponly"]
        assert client.cookies[name]["samesite"] == "Lax"
        assert client.cookies[name]["path"] == "/"
        assert client.cookies[name]["domain"] == ""
    for method, path in [("get", "login"), ("post", "logout"), ("get", "me")]:
        result = getattr(api_client(), method)(f"/api/auth/{path}")
        assert result.headers["Cache-Control"] == "no-store"
        assert body(result)["requestId"] == result.headers["X-Request-Id"]


def test_ip_network_normalization_and_forwarding_headers() -> None:
    from accounts.models import AuthRateLimit
    from accounts.rate_limit import ip_network

    assert ip_network("192.0.2.1") == "192.0.2.1/32"
    assert ip_network("::ffff:192.0.2.1") == "192.0.2.1/32"
    assert ip_network("2001:db8::1") == ip_network("2001:db8::ffff") == "2001:db8::/64"
    client = api_client()
    csrf = token(client)
    for forwarded in ["192.0.2.1", "192.0.2.2"]:
        assert client.post("/api/auth/login", data="{}", content_type="application/json", HTTP_X_CSRFTOKEN=csrf,
                           HTTP_X_FORWARDED_FOR=forwarded).status_code == 400
    assert AuthRateLimit.objects.count() == 1
    counter = AuthRateLimit.objects.get()
    assert counter.count == 2
    assert len(counter.ip_digest) == 64
    assert "127.0.0.1" not in counter.ip_digest
    assert client.post("/api/auth/login", data="{}", content_type="application/json",
                       HTTP_X_CSRFTOKEN=csrf, REMOTE_ADDR="invalid").status_code == 503


def test_success_error_openapi_and_password_whitespace() -> None:
    from accounts.models import User
    from tests.test_foundation import assert_contract

    password = PASSWORD + "  "
    client = api_client()
    response = post(client, "/api/auth/signup", {
        "username": "river_user", "display_name": "River", "email": "river@example.test", "password": password,
    }, token(client))
    assert response.status_code == 201
    assert_contract(response, "AuthAccount")
    user = User.objects.get()
    assert user.check_password(password)
    assert not user.check_password(PASSWORD)
    assert_contract(client.get("/api/auth/me"), "AuthAccount")
    csrf = token(client)
    assert post(client, "/api/auth/logout", {}, csrf).status_code == 204
    assert post(client, "/api/auth/logout", {}, csrf).status_code == 204
    response = post(client, "/api/auth/login", {"email": "river@example.test", "password": "x"}, csrf)
    assert response.status_code == 401  # login does not reapply signup's minimum length
    assert_contract(response, "Error")
    response = post(client, "/api/auth/login", {"email": "river@example.test", "password": password}, csrf)
    assert response.status_code == 200
    assert_contract(response, "AuthAccount")


def test_signup_rejects_unknown_fields_and_bad_json_before_hash() -> None:
    from unittest.mock import patch

    from accounts.models import AuthRateLimit, User

    client = api_client()
    csrf = token(client)
    with patch("accounts.models.User.set_password", side_effect=AssertionError("must not hash")):
        response = post(client, "/api/auth/signup", {
            "username": "river_user", "display_name": "River", "email": "river@example.test",
            "password": PASSWORD, "is_staff": True,
        }, csrf)
        assert response.status_code == 400
        for raw, media, expected in [("{", "application/json", 400), ("[]", "application/json", 400), ("{}", "text/plain", 415)]:
            response = client.post("/api/auth/signup", data=raw, content_type=media, HTTP_X_CSRFTOKEN=csrf)
            assert response.status_code == expected
    assert not User.objects.exists()
    assert AuthRateLimit.objects.get().count == 4
