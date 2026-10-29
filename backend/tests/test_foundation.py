"""FL01-AC1/2: 独立した設計文言・OpenAPIを期待値にする。"""
import json
import logging
import os
import subprocess
import sys
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import UUID

import pytest
from django.core import exceptions as django_exceptions
from django.core.management import call_command
from django.db import OperationalError, connection
from django.db.migrations.executor import MigrationExecutor
from django.http import Http404, HttpResponse
from django.test import Client, RequestFactory, override_settings
from jsonschema import Draft202012Validator
from rest_framework import exceptions

from accounts.models import User
from common.errors import CsrfFailure, api_exception_handler

SECRET = "postgresql://secret-user:secret-password@private-host/secret-db"
CONTRACT_PATH = Path("/app/contracts/openapi.json")
if not CONTRACT_PATH.exists():
    CONTRACT_PATH = Path(__file__).resolve().parents[2] / "docs/api/openapi.json"
CONTRACT = json.loads(CONTRACT_PATH.read_text())


def assert_contract(response: Any, schema_name: str) -> None:
    assert response["Content-Type"].split(";")[0] == "application/json"
    schema = {"$ref": f"#/components/schemas/{schema_name}", **CONTRACT}
    Draft202012Validator(schema).validate(json.loads(response.content))
    assert str(UUID(response["X-Request-Id"])) == response["X-Request-Id"]
    if schema_name == "Error":
        assert json.loads(response.content)["requestId"] == response["X-Request-Id"]
    assert SECRET not in response.content.decode()


@pytest.mark.django_db(transaction=True)
def test_uuid_and_initial_migration_reapplication() -> None:
    assert connection.vendor == "postgresql"
    assert connection.settings_dict["NAME"] == "test_fitlog"
    executor = MigrationExecutor(connection)
    assert executor.migration_plan(executor.loader.graph.leaf_nodes()) == []
    assert ("accounts", "0001_initial") in executor.loader.applied_migrations
    user = User.objects.create_user(username="foundation", email="foundation@example.test",
                                    display_name="Foundation", password="River-lantern-42!pine")
    assert isinstance(user.pk, UUID)
    saved = User.objects.get(username="foundation")
    assert saved.pk == user.pk
    assert str(UUID(str(saved.pk))) == str(user.pk)
    call_command("migrate", interactive=False, verbosity=0)
    executor = MigrationExecutor(connection)
    assert executor.migration_plan(executor.loader.graph.leaf_nodes()) == []
    assert User.objects.get(pk=user.pk).username == "foundation"


def test_live_never_connects_to_database(client: Client) -> None:
    # DB access is forbidden by pytest-django in this test as well as the injected failure.
    with patch("django.db.backends.base.base.BaseDatabaseWrapper.cursor", side_effect=AssertionError):
        response = client.get("/api/health/live", HTTP_X_REQUEST_ID="untrusted")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response["X-Request-Id"] != "untrusted"
    assert_contract(response, "Health")
    assert client.get("/api/health/live")["X-Request-Id"] != response["X-Request-Id"]


@pytest.mark.django_db(transaction=True)
def test_ready_uses_real_database_and_restores_timeout(client: Client) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SHOW statement_timeout")
        original = cursor.fetchone()
    response = client.get("/api/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert_contract(response, "Health")
    with connection.cursor() as cursor:
        cursor.execute("SHOW statement_timeout")
        assert cursor.fetchone() == original
    assert connection.settings_dict["OPTIONS"]["connect_timeout"] == 5


@pytest.mark.django_db
@pytest.mark.parametrize("failure", ["connection", "migration"])
def test_ready_unavailable(client: Client, failure: str, api_log_output: StringIO) -> None:
    target = "common.health.connection.cursor" if failure == "connection" else (
        "common.health.MigrationExecutor.migration_plan"
    )
    kwargs: dict[str, Any] = {"side_effect": OperationalError(SECRET)} if failure == "connection" else {
        "return_value": [(object(), False)]
    }
    with patch(target, **kwargs):
        response = client.get("/api/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert_contract(response, "Health")
    output = api_log_output.getvalue()
    assert "api_error status=503" in output
    assert response["X-Request-Id"] in output
    assert SECRET not in output


@pytest.mark.parametrize("debug", [True, False])
def test_json_unknown_and_exception(client: Client, debug: bool, api_log_output: StringIO) -> None:
    with override_settings(DEBUG=debug):
        response = client.get("/api/not-implemented")
        assert response.status_code == 404
        assert response.json()["code"] == "NOT_FOUND"
        assert_contract(response, "Error")
        with patch("common.health.live", side_effect=RuntimeError(SECRET)):
            response = client.get("/api/health/live")
        assert response.status_code == 500
        assert json.loads(response.content)["code"] == "INTERNAL_ERROR"
        assert_contract(response, "Error")
    output = api_log_output.getvalue()
    assert "api_error status=500" in output
    assert response["X-Request-Id"] in output
    assert SECRET not in output


@pytest.mark.parametrize("path", ["/api/health/live", "/api/health/ready"])
def test_health_post_is_json_405(client: Client, path: str) -> None:
    response = client.post(path)
    assert response.status_code == 405
    assert response.json()["code"] == "METHOD_NOT_ALLOWED"
    assert "GET" in response["Allow"].split(", ")
    assert_contract(response, "Error")
    assert "Allow" in CONTRACT["components"]["responses"]["Error405"]["headers"]


def test_unacceptable_response_stays_json(client: Client) -> None:
    response = client.get("/api/health/live", HTTP_ACCEPT="text/html")
    assert response.status_code == 406
    assert response.json()["code"] == "NOT_ACCEPTABLE"
    assert_contract(response, "Error")


@pytest.mark.parametrize(("exc", "status", "code"), [
    (exceptions.ParseError(SECRET), 400, "VALIDATION_ERROR"),
    (exceptions.ValidationError(SECRET), 400, "VALIDATION_ERROR"),
    (django_exceptions.SuspiciousOperation(SECRET), 400, "VALIDATION_ERROR"),
    (django_exceptions.BadRequest(SECRET), 400, "VALIDATION_ERROR"),
    (exceptions.NotAuthenticated(SECRET), 401, "AUTH_REQUIRED"),
    (exceptions.AuthenticationFailed(SECRET), 401, "INVALID_CREDENTIALS"),
    (exceptions.PermissionDenied(SECRET), 403, "FORBIDDEN"),
    (django_exceptions.PermissionDenied(SECRET), 403, "FORBIDDEN"),
    (CsrfFailure(SECRET), 403, "CSRF_FAILED"),
    (exceptions.NotFound(SECRET), 404, "NOT_FOUND"),
    (Http404(SECRET), 404, "NOT_FOUND"),
    (exceptions.MethodNotAllowed("POST", SECRET), 405, "METHOD_NOT_ALLOWED"),
    (exceptions.NotAcceptable(SECRET), 406, "NOT_ACCEPTABLE"),
    (exceptions.UnsupportedMediaType("bad", SECRET), 415, "UNSUPPORTED_MEDIA_TYPE"),
    (exceptions.Throttled(wait=3, detail=SECRET), 429, "RATE_LIMITED"),
    (RuntimeError(SECRET), 500, "INTERNAL_ERROR"),
])
@pytest.mark.parametrize("debug", [True, False])
def test_exception_table(exc: Exception, status: int, code: str, debug: bool) -> None:
    request = RequestFactory().get("/api/test")
    request_id = "d49e076f-8264-4261-a8f0-d2c746226a73"
    request.META["FITLOG_REQUEST_ID"] = request_id
    with override_settings(DEBUG=debug):
        response = api_exception_handler(exc, {"request": request})
    assert response.status_code == status
    body = json.loads(response.content)
    assert body["code"] == code
    assert body["requestId"] == request_id
    assert SECRET not in response.content.decode()
    if status == 429:
        assert response["Retry-After"] == "3"


def test_authenticate_header_is_preserved() -> None:
    class AuthenticationRequiredWithHeader(exceptions.NotAuthenticated):
        auth_header: str

    exc = AuthenticationRequiredWithHeader(SECRET)
    exc.auth_header = 'Session realm="api"'
    response = api_exception_handler(exc, {"request": RequestFactory().get("/api/test")})
    assert response["WWW-Authenticate"] == 'Session realm="api"'


@pytest.mark.parametrize("debug", [True, False])
@pytest.mark.parametrize(("status", "code"), [
    (400, "VALIDATION_ERROR"), (403, "FORBIDDEN"), (404, "NOT_FOUND"), (500, "INTERNAL_ERROR"),
])
def test_django_html_errors_are_normalized(status: int, code: str, debug: bool) -> None:
    from common.middleware import ApiBoundaryMiddleware

    request = RequestFactory().get("/api/example", HTTP_HOST="localhost")
    middleware = ApiBoundaryMiddleware(lambda _: HttpResponse(SECRET, status=status))
    with override_settings(DEBUG=debug):
        response = middleware(request)
    assert json.loads(response.content)["code"] == code
    assert_contract(response, "Error")


@pytest.mark.parametrize("secret", [None, "", "   "])
def test_secret_key_required(secret: str | None) -> None:
    env = {**os.environ}
    env.pop("DJANGO_SECRET_KEY", None)
    if secret is not None:
        env["DJANGO_SECRET_KEY"] = secret
    result = subprocess.run(
        [sys.executable, "-c", "import config.settings"], env=env,
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY is required" in result.stderr


def test_debug_defaults_false() -> None:
    env = {**os.environ, "DJANGO_SECRET_KEY": "local-test-only"}
    env.pop("DJANGO_DEBUG", None)
    result = subprocess.run(
        [sys.executable, "-c", "import config.settings as s; print(s.DEBUG); print(s.ALLOWED_HOSTS)"],
        env=env, capture_output=True, text=True, check=True,
    )
    assert result.stdout.splitlines() == ["False", "['localhost', '127.0.0.1', 'backend']"]


@pytest.mark.django_db(transaction=True)
def test_ready_timeout_is_local_and_unknown_failure_is_500(client: Client) -> None:
    def inspect_timeout(*args: Any, **kwargs: Any) -> list[Any]:
        with connection.cursor() as cursor:
            cursor.execute("SHOW statement_timeout")
            assert cursor.fetchone() == ("2s",)
        return []

    with patch("common.health.MigrationExecutor.migration_plan", side_effect=inspect_timeout):
        assert client.get("/api/health/ready").status_code == 200
    with patch("common.health.MigrationExecutor.migration_plan", side_effect=RuntimeError(SECRET)):
        response = client.get("/api/health/ready")
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert_contract(response, "Error")


@pytest.mark.parametrize("debug", [True, False])
@pytest.mark.parametrize("exc", [django_exceptions.BadRequest(SECRET), django_exceptions.PermissionDenied(SECRET), Http404(SECRET), RuntimeError(SECRET)])
def test_django_exceptions_through_http(client: Client, debug: bool, exc: Exception) -> None:
    from django.urls import path

    def failing_view(request: Any) -> HttpResponse:
        raise exc

    class TestUrls:
        urlpatterns = [path("api/error", failing_view)]

    expected = 400 if isinstance(exc, django_exceptions.BadRequest) else 403 if isinstance(exc, django_exceptions.PermissionDenied) else 404 if isinstance(exc, Http404) else 500
    with override_settings(DEBUG=debug, ROOT_URLCONF=TestUrls):
        response = client.get("/api/error")
    assert response.status_code == expected
    assert_contract(response, "Error")


def test_django_log_policy_does_not_emit_exception_text(api_log_output: StringIO) -> None:
    logging.getLogger("django.request").error(SECRET)
    logging.getLogger("fitlog.api").warning("log_policy_probe")
    output = api_log_output.getvalue()
    assert "log_policy_probe" in output
    assert SECRET not in output


@pytest.mark.parametrize("path", ["/api/error", "/outside"])
def test_process_exception_boundary(path: str) -> None:
    from common.middleware import ApiBoundaryMiddleware

    request = RequestFactory().get(path, HTTP_HOST="localhost")
    request.META["FITLOG_REQUEST_ID"] = "d49e076f-8264-4261-a8f0-d2c746226a73"
    middleware = ApiBoundaryMiddleware(lambda _: HttpResponse())
    response = middleware.process_exception(request, RuntimeError(SECRET))
    if path == "/outside":
        assert response is None
    else:
        assert response is not None
        assert response.status_code == 500
        assert json.loads(response.content)["code"] == "INTERNAL_ERROR"
        assert_contract(response, "Error")


@pytest.mark.parametrize(("status", "header", "value"), [
    (405, "Allow", "GET, HEAD, OPTIONS"),
    (401, "WWW-Authenticate", 'Session realm="api"'),
    (429, "Retry-After", "3"),
    (500, "X-Content-Type-Options", "nosniff"),
    (500, "Referrer-Policy", "same-origin"),
    (500, "Cross-Origin-Opener-Policy", "same-origin"),
    (500, "Strict-Transport-Security", "max-age=3600"),
    (500, "X-Frame-Options", "DENY"),
])
def test_html_normalization_keeps_headers(status: int, header: str, value: str) -> None:
    from common.middleware import ApiBoundaryMiddleware

    request = RequestFactory().get("/api/example", HTTP_HOST="localhost")
    middleware = ApiBoundaryMiddleware(lambda _: HttpResponse(SECRET, status=status, headers={header: value}))
    response = middleware(request)
    assert response.status_code == status
    assert response[header] == value
    assert_contract(response, "Error")


@pytest.mark.parametrize("method", ["post", "put", "delete"])
def test_missing_api_is_404_with_real_csrf_checks(method: str) -> None:
    client = Client(enforce_csrf_checks=True, SERVER_NAME="localhost")
    response = getattr(client, method)("/api/not-implemented")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
    assert_contract(response, "Error")


@pytest.mark.parametrize(("host", "status"), [("evil.example", 400), ("localhost", 200), ("backend", 200)])
def test_allowed_host_is_enforced(client: Client, host: str, status: int) -> None:
    response = client.get("/api/health/live", HTTP_HOST=host)
    assert response.status_code == status
    assert_contract(response, "Error" if status == 400 else "Health")
    if status == 400:
        assert response.json()["code"] == "VALIDATION_ERROR"
