"""固定窓の別接続・rollback境界と移行互換性を実PostgreSQLで検証する。"""
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event
from typing import Any
from unittest.mock import patch

import pytest
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import (
    DatabaseError,
    IntegrityError,
    close_old_connections,
    connection,
    connections,
    transaction,
)
from django.db.migrations.executor import MigrationExecutor

from accounts.models import AuthRateLimit, User
from accounts.rate_limit import consume_attempt
from tests.test_auth import PASSWORD, api_client, body, post, signup, token

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def fixed_auth_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("django.utils.timezone.now", lambda: datetime(2026, 10, 29, 12, 34, 56, tzinfo=UTC))


def test_parallel_counter_allows_exactly_ten_and_is_committed() -> None:
    barrier = Barrier(12)

    def attempt() -> int | None:
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return consume_attempt("192.0.2.44")
        finally:
            connections.close_all()

    with patch("accounts.rate_limit.timezone.now", return_value=datetime(2026, 10, 29, 12, 34, 56, tzinfo=UTC)):
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(lambda _: attempt(), range(12)))
    assert results.count(None) == 10
    assert results.count(4) == 2
    assert AuthRateLimit.objects.get().count == 12


def test_counter_survives_user_rollback_and_no_outer_transaction() -> None:
    client = api_client()
    csrf = token(client)
    states: list[bool] = []
    original = User.save

    def fail_save(user: User, *args: Any, **kwargs: Any) -> None:
        states.append(connection.in_atomic_block)
        original(user, *args, **kwargs)
        raise IntegrityError("unknown-constraint-secret")

    with patch.object(User, "save", fail_save):
        response = signup(client, csrf)
    assert response.status_code == 503
    assert states == [True]
    assert not User.objects.exists()

    def read_counter() -> int:
        close_old_connections()
        try:
            return AuthRateLimit.objects.get().count
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(read_counter).result(timeout=10) == 1
    with transaction.atomic(), pytest.raises(DatabaseError, match="autocommit") as error:
        consume_attempt("192.0.2.1")
    assert isinstance(error.value, DatabaseError)


def test_password_hash_does_not_hold_counter_lock() -> None:
    entered = Event()
    release = Event()
    original = User.set_password

    def waiting_hash(user: User, raw_password: str | None) -> None:
        entered.set()
        assert release.wait(timeout=10)
        original(user, raw_password)

    first = api_client()
    first_csrf = token(first)

    def login() -> int:
        close_old_connections()
        try:
            return post(first, "/api/auth/login", {"email": "none@example.test", "password": PASSWORD}, first_csrf).status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool, patch.object(User, "set_password", waiting_hash):
        pending = pool.submit(login)
        try:
            assert entered.wait(timeout=10)
            # First HTTP request has committed its counter, while its hasher is blocked.
            second = api_client()
            second_csrf = token(second)
            with connection.cursor() as cursor:
                cursor.execute("SHOW statement_timeout")
                timeout = cursor.fetchone()
                assert timeout is not None
                cursor.execute("SET statement_timeout = '3000ms'")
            try:
                response = post(second, "/api/auth/login", {}, second_csrf)
                assert response.status_code == 400
                assert AuthRateLimit.objects.get().count == 2
            finally:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('statement_timeout', %s, false)", [timeout[0]])
        finally:
            release.set()
        assert pending.result(timeout=10) == 401


@pytest.mark.parametrize("different_case", [False, True])
@pytest.mark.parametrize("duplicate", ["username", "email"])
def test_concurrent_signup_known_constraints(duplicate: str, different_case: bool) -> None:
    from accounts import services

    barrier = Barrier(2)
    original = services.duplicate_field

    def simultaneous_check(username: str, email: str) -> str | None:
        result = original(username, email)
        if result is None:
            barrier.wait(timeout=10)
        return result

    def register(index: int) -> tuple[int, str | None]:
        close_old_connections()
        try:
            client = api_client()
            username = "river_user" if duplicate == "username" else f"river_{index}"
            email = "river@example.test" if duplicate == "email" else f"river{index}@example.test"
            if index and different_case:
                username, email = username.upper(), email.upper()
            response = signup(client, token(client), username, email)
            return response.status_code, body(response).get("code")
        finally:
            connections.close_all()

    with patch("accounts.services.duplicate_field", simultaneous_check), ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(register, range(2)))
    assert sorted(status for status, _ in results) == [201, 409]
    expected = "DUPLICATE_USERNAME" if duplicate == "username" else "DUPLICATE_EMAIL"
    assert (409, expected) in results
    assert User.objects.count() == 1
    assert AuthRateLimit.objects.get().count == 2


def test_existing_plain_username_constraint_is_introspected() -> None:
    # A duplicate of the standard username constraint remains a 409. Force the
    # race after the precheck, then let PostgreSQL choose its actual constraint.
    client = api_client()
    csrf = token(client)
    User.objects.create_user("river_user", "existing@example.test", PASSWORD, display_name="River")
    with patch("accounts.services.duplicate_field", side_effect=[None, "username"]):
        response = signup(client, csrf)
    assert response.status_code == 409
    assert body(response)["code"] == "DUPLICATE_USERNAME"
    assert AuthRateLimit.objects.get().count == 1


def test_cleanup_preserves_current_and_recent_windows_and_live_sessions() -> None:
    from django.contrib.sessions.backends.db import SessionStore
    from django.contrib.sessions.models import Session

    now = datetime(2026, 10, 29, 12, 34, 56, tzinfo=UTC)
    current = now.replace(second=0)
    for minutes in [0, 1, 2, 3]:
        AuthRateLimit.objects.create(ip_digest="a" * 64, window_start=current - timedelta(minutes=minutes), count=1)
    live = SessionStore()
    live["test"] = "live"
    live.set_expiry(now + timedelta(days=1))
    live.save()
    expired = SessionStore()
    expired["test"] = "expired"
    expired.set_expiry(now - timedelta(seconds=1))
    expired.save()
    with patch("django.utils.timezone.now", return_value=now):
        call_command("cleanup_auth_security", verbosity=0)
    assert set(AuthRateLimit.objects.values_list("window_start", flat=True)) == {current, current - timedelta(minutes=1)}
    assert Session.objects.filter(session_key=live.session_key).exists()
    assert not Session.objects.filter(session_key=expired.session_key).exists()


def test_manager_and_backend_have_no_username_fallback() -> None:
    from django.conf import settings

    assert settings.AUTHENTICATION_BACKENDS == ["accounts.backends.EmailBackend"]
    user = User.objects.create_superuser("river_user", "river@example.test", PASSWORD, display_name="River")
    assert user.is_staff and user.is_superuser
    assert authenticate(username="river@example.test", password=PASSWORD) is None
    with pytest.raises(ValidationError):
        User.objects.create_user("second_user", password=PASSWORD, display_name="River")
    with pytest.raises(ValidationError):
        User.objects.create_superuser("third_user", "third@example.test", "short", display_name="River")


@pytest.mark.parametrize("env,http,key,ok", [
    ("local", "1", "x" * 32, True), ("production", "0", "x" * 32, True),
    ("local", "0", "x" * 32, True), ("unknown", "0", "x" * 32, False),
    ("production", "1", "x" * 32, False), ("local", "1", "x" * 31, False),
    ("local", "1", "", False),
    ("production", "0", "fitlog-local-only-public-hmac-key-never-use-in-production", False),
])
def test_secure_environment_configuration(env: str, http: str, key: str, ok: bool) -> None:
    environment = {**os.environ, "FITLOG_ENV": env, "FITLOG_LOCAL_HTTP": http, "AUTH_RATE_LIMIT_HMAC_KEY": key}
    result = subprocess.run([sys.executable, "-c", "from config import settings; print(settings.SESSION_COOKIE_SECURE, settings.CSRF_COOKIE_SECURE)"],
                            env=environment, capture_output=True, text=True, check=False)
    assert (result.returncode == 0) is ok
    if ok:
        secure = not (env == "local" and http == "1")
        assert result.stdout.strip() == f"{secure} {secure}"


@pytest.mark.parametrize("invalid", ["", "username", "email", "legacy_email"])
def test_migration_preserves_legacy_or_stops_without_secret_values(invalid: str) -> None:
    executor = MigrationExecutor(connection)
    before = [("accounts", "0001_initial")]
    after = [("accounts", "0002_auth")]
    executor.migrate(before)
    old = executor.loader.project_state(before).apps.get_model("accounts", "User")
    secret = "existing-password-hash-marker"
    user = old.objects.create(username="foundation", email="", password=secret)
    if invalid == "username":
        old.objects.create(username="a" * 51, email="", password=secret)
    elif invalid == "email":
        old.objects.create(username="other", email="Secret-Marker@Example.test", password=secret)
        old.objects.create(username="another", email="secret-marker@example.test", password=secret)
    elif invalid == "legacy_email":
        old.objects.create(username="other", email=" secret-marker@example.test ", password=secret)
    try:
        if invalid:
            with pytest.raises(RuntimeError) as failure:
                MigrationExecutor(connection).migrate(after)
            assert "Account migration stopped:" in str(failure.value)
            assert "secret-marker" not in str(failure.value).lower()
            assert secret not in str(failure.value)
            assert old.objects.get(pk=user.pk).password == secret
            old.objects.exclude(pk=user.pk).delete()
        MigrationExecutor(connection).migrate(after)
        migrated = User.objects.get(pk=user.pk)
        assert migrated.password == secret
        assert migrated.email == ""
        assert migrated.display_name == "foundation"
        assert migrated.pk == user.pk
    finally:
        old.objects.exclude(pk=user.pk).delete()
        MigrationExecutor(connection).migrate(after)


def test_migration_detects_lowercase_collisions_before_mutation() -> None:
    # Run the data migration's preflight against a historical model with the
    # case-sensitive 0001 constraints, where these collisions can exist.
    executor = MigrationExecutor(connection)
    before = [("accounts", "0001_initial")]
    after = [("accounts", "0002_auth")]
    executor.migrate(before)
    old = executor.loader.project_state(before).apps.get_model("accounts", "User")
    old.objects.create(username="River_User", email="", password="preserve")
    old.objects.create(username="river_user", email="", password="preserve")
    try:
        with pytest.raises(RuntimeError, match="duplicate_username"):
            MigrationExecutor(connection).migrate(after)
        assert old.objects.count() == 2
        assert set(old.objects.values_list("password", flat=True)) == {"preserve"}
    finally:
        old.objects.all().delete()
        MigrationExecutor(connection).migrate(after)
