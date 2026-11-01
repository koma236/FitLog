"""FL08-AC1: approved fixed fields and secret sentinels, independent of implementation."""
import contextlib
import importlib
import importlib.util
import json
import logging
from collections.abc import Iterator
from io import StringIO
from typing import Any

import pytest
from django.conf import settings
from django.test import RequestFactory
from django.urls import resolve


def test_free_message_is_replaced_without_reflecting_secret(api_log_output: StringIO) -> None:
    # A formatter that uses LogRecord.getMessage() would expose the sentinel.
    secret = "private-observability-sentinel@example.test"
    logging.getLogger("fitlog.api").warning(secret)
    output = api_log_output.getvalue()
    assert "log_record_discarded" in output
    assert secret not in output


REQUEST_ID = "31be02cc-c100-4eca-8abd-f3abe0acb780"
SECRET = "private-DSN-and-capability-sentinel"


@pytest.fixture
def console_output(monkeypatch: pytest.MonkeyPatch) -> Iterator[StringIO]:
    output = StringIO()
    handlers = {id(h): h for name in ("", "fitlog.api", "fitlog.maintenance")
                for h in logging.getLogger(name).handlers
                if isinstance(h, logging.StreamHandler) and h.name == "console"}
    assert handlers, "configured output sink must exist; empty capture cannot prove safety"
    for h in handlers.values():
        monkeypatch.setattr(h, "stream", output)
    yield output


def observation() -> Any:
    assert importlib.util.find_spec("common.observability") is not None
    return importlib.import_module("common.observability")


def api_fields() -> dict[str, object]:
    return {"event": "api_request", "request_id": REQUEST_ID, "method": "GET",
            "route_template": "api/auth/me", "status": 200, "duration_ms": 7}


def record(name: str = "fitlog.api", fields: dict[str, object] | None = None) -> logging.LogRecord:
    r = logging.LogRecord(name, logging.INFO, __file__, 0, SECRET, (), None)
    r.created = 0
    r.fitlog_event = fields or api_fields()
    return r


def test_json_and_text_use_same_fixed_projection() -> None:
    obs = observation()
    r = record()
    obj = json.loads(obs.SafeFormatter(mode="json", app_version="abcdef0").format(r))
    assert obj == {**api_fields(), "timestamp": "1970-01-01T00:00:00.000Z",
                   "level": "INFO", "app_version": "abcdef0"}
    text = obs.SafeFormatter(mode="text", app_version="abcdef0").format(r)
    assert text == ("INFO api_request status=200 request_id=" + REQUEST_ID
                    + " method=GET route_template=api/auth/me duration_ms=7"
                    + " app_version=abcdef0 timestamp=1970-01-01T00:00:00.000Z")
    assert SECRET not in text


@pytest.mark.parametrize("name", ["third_party", "fitlog.maintenance", "fitlog.api.child"])
def test_wrong_logger_cannot_spoof_api_event(name: str) -> None:
    obj = json.loads(observation().SafeFormatter(mode="json").format(record(name)))
    assert set(obj) == {"timestamp", "level", "event", "request_id", "app_version"}
    assert obj["event"] == "log_record_discarded" and obj["request_id"] is None


@pytest.mark.parametrize(("key", "value"), [
    ("status", True), ("status", 500), ("request_id", SECRET),
    ("method", "GET\n" + SECRET), ("route_template", "api/" + SECRET + "?token=x"),
    ("duration_ms", -1), ("duration_ms", 1.5), ("duration_ms", True),
    ("extra", SECRET), ("event", "unknown"),
])
def test_invalid_fields_are_discarded(key: str, value: object) -> None:
    fields = api_fields()
    fields[key] = value
    obj = json.loads(observation().SafeFormatter(mode="json").format(record(fields=fields)))
    assert obj["event"] == "log_record_discarded"
    assert SECRET not in json.dumps(obj)


@pytest.mark.parametrize("version", ["", "abcdef", "a" * 41, "secret\nvalue", SECRET])
def test_untrusted_version_is_unknown(version: str) -> None:
    obj = json.loads(observation().SafeFormatter(mode="json", app_version=version).format(record()))
    assert obj["app_version"] == "unknown"


def test_root_and_maintenance_sinks_are_safe_and_do_not_propagate() -> None:
    obs = observation()
    for name in ("", "fitlog.api", "fitlog.maintenance"):
        logger = logging.getLogger(name)
        assert any(isinstance(h, obs.SafeStreamHandler) for h in logger.handlers)
    assert settings.LOGGING["handlers"]["console"]["stream"] == "ext://sys.stdout"
    assert not logging.getLogger("fitlog.api").propagate
    assert not logging.getLogger("fitlog.maintenance").propagate


def test_arbitrary_logger_has_positive_discard_control(console_output: StringIO) -> None:
    logging.getLogger("third_party.sentinel").warning(SECRET)
    assert "log_record_discarded" in console_output.getvalue()
    assert SECRET not in console_output.getvalue()


def test_write_failure_never_uses_raw_handle_error() -> None:
    class BrokenStream:
        attempts = 0
        def write(self, value: str) -> None:
            self.attempts += 1
            raise OSError(SECRET)
        def flush(self) -> None:
            pass
    obs = observation()
    stream = BrokenStream()
    handler = obs.SafeStreamHandler(stream)
    handler.setFormatter(obs.SafeFormatter(mode="json"))
    stderr = StringIO()
    with contextlib.redirect_stderr(stderr):
        handler.handle(record("third_party"))
    assert stream.attempts == 1
    assert stderr.getvalue() == ""


@pytest.mark.parametrize(("path", "template"), [
    ("/api/auth/me", "api/auth/me"),
    ("/api/media/content/private-capability", "api/media/content/<str:token>"),
    ("/api/unknown/private-path", "unmatched"),
])
def test_api_emitter_uses_template_and_no_input(path: str, template: str,
                                              console_output: StringIO) -> None:
    request = RequestFactory().get(path, {"query": SECRET}, HTTP_AUTHORIZATION=SECRET)
    request.META["FITLOG_REQUEST_ID"] = REQUEST_ID
    request.resolver_match = resolve(path)
    observation().emit_api_result(request, 200, 3)
    output = console_output.getvalue()
    assert "api_request status=200 request_id=" + REQUEST_ID in output
    assert "route_template=" + template in output
    assert SECRET not in output and "private-capability" not in output


@pytest.mark.parametrize(("status", "level"), [(200, "INFO"), (401, "WARNING"), (503, "ERROR")])
def test_api_emitter_uses_final_status(status: int, level: str,
                                     console_output: StringIO) -> None:
    request = RequestFactory().get("/api/auth/me")
    request.META["FITLOG_REQUEST_ID"] = REQUEST_ID
    observation().emit_api_result(request, status, 0)
    assert console_output.getvalue().startswith(level + " api_")
    assert "route_template=unmatched" in console_output.getvalue()
    assert len(console_output.getvalue().splitlines()) == 1


@pytest.mark.django_db(transaction=True)
def test_actual_database_refusal_then_recovery_preserves_configuration(client: Any) -> None:
    import copy
    import socket

    from django.db import connection

    assert client.get("/api/health/ready").status_code == 200
    with connection.cursor() as cursor:
        cursor.execute("SHOW statement_timeout")
        initial_timeout = cursor.fetchone()
    original = connection.settings_dict
    snapshot = copy.deepcopy(original)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as refused:
        refused.bind(("127.0.0.1", 0))  # Keep the port owned, without listen(), through the attempt.
        connection.close()
        isolated = copy.deepcopy(original)
        isolated["HOST"] = "127.0.0.1"
        isolated["PORT"] = str(refused.getsockname()[1])
        connection.settings_dict = isolated
        try:
            response = client.get("/api/health/ready")
            assert response.status_code == 503
            assert response.json() == {"status": "unavailable"}
            assert client.get("/api/health/live").status_code == 200
        finally:
            connection.close()
            connection.settings_dict = original
    assert connection.settings_dict is original and original == snapshot
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        assert cursor.fetchone() == (1,)
        cursor.execute("SHOW statement_timeout")
        assert cursor.fetchone() == initial_timeout
    assert client.get("/api/health/ready").status_code == 200


@pytest.mark.django_db(transaction=True)
def test_emitter_never_evaluates_user_or_queries_database(django_assert_num_queries: Any,
                                                          console_output: StringIO) -> None:
    from unittest.mock import patch

    from django.utils.functional import SimpleLazyObject

    def forbidden_user() -> None:
        raise AssertionError("logging must not evaluate the authenticated user")
    request = RequestFactory().get("/api/auth/me")
    request.META["FITLOG_REQUEST_ID"] = REQUEST_ID
    with patch.object(request, "user", SimpleLazyObject(forbidden_user), create=True), django_assert_num_queries(0):
        observation().emit_api_result(request, 200, 0)
    assert "api_request" in console_output.getvalue()


@pytest.mark.parametrize("method", ["TRACE", "CONNECT", "GET\n" + SECRET])
def test_unknown_method_is_fixed_other(method: str, console_output: StringIO) -> None:
    request = RequestFactory().get("/api/auth/me")
    request.method = method
    request.META["FITLOG_REQUEST_ID"] = REQUEST_ID
    observation().emit_api_result(request, 200, 0)
    assert "method=OTHER" in console_output.getvalue()
    assert SECRET not in console_output.getvalue()


@pytest.mark.parametrize("event", [[], {}, None, True])
def test_nonstr_event_still_emits_positive_discard(event: object) -> None:
    fields = api_fields()
    fields["event"] = event
    obj = json.loads(observation().SafeFormatter(mode="json").format(record(fields=fields)))
    assert obj["event"] == "log_record_discarded"


def test_bad_format_setting_has_fixed_startup_error() -> None:
    import os
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, "-c", "import config.settings"], capture_output=True, text=True,
        env={**os.environ, "FITLOG_LOG_FORMAT": SECRET}, check=False,
    )
    assert result.returncode != 0
    assert "Invalid FitLog log format" in result.stderr
    assert SECRET not in result.stderr+result.stdout


def test_successful_response_has_one_matching_api_event(client: Any,
                                                        console_output: StringIO) -> None:
    response = client.get("/api/health/live?private=" + SECRET, HTTP_X_REQUEST_ID=SECRET)
    assert response.status_code == 200
    lines = console_output.getvalue().splitlines()
    assert len(lines) == 1
    assert "INFO api_request status=200 request_id=" + response["X-Request-Id"] in lines[0]
    assert "route_template=api/health/live" in lines[0]
    assert SECRET not in lines[0]


@pytest.mark.parametrize(("path", "headers", "status", "template"), [
    ("/api/unknown/private-path", {}, 404, "unmatched"),
    ("/api/health/live", {"HTTP_HOST": "bad.invalid"}, 400, "unmatched"),
    ("/api/auth/me", {}, 401, "api/auth/me"),
])
def test_final_error_response_is_logged_once(client: Any, console_output: StringIO,
                                           path: str, headers: dict[str, str],
                                           status: int, template: str) -> None:
    response = client.get(path, **headers)
    assert response.status_code == status
    lines = console_output.getvalue().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("WARNING api_error status=" + str(status))
    assert "request_id=" + response["X-Request-Id"] in lines[0]
    assert "route_template=" + template in lines[0]
    assert "private-path" not in lines[0]


def test_view_exception_is_fixed_and_logged_once(client: Any, console_output: StringIO) -> None:
    from unittest.mock import patch
    with patch("common.health.live", side_effect=RuntimeError(SECRET)):
        response = client.get("/api/health/live")
    assert response.status_code == 500
    lines = console_output.getvalue().splitlines()
    assert len(lines) == 1 and lines[0].startswith("ERROR api_error status=500")
    assert response["X-Request-Id"] in lines[0]
    assert SECRET not in console_output.getvalue()+response.content.decode()


@pytest.mark.django_db(transaction=True)
def test_authenticated_request_query_count_does_not_increase(client: Any,
                                                            console_output: StringIO) -> None:
    from unittest.mock import patch

    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from accounts.models import User
    user = User.objects.create_user(username="logoracle", email="logoracle@example.test",
                                    display_name="Log Oracle", password="test-log-oracle-password-42")
    client.force_login(user)
    with patch("common.middleware.emit_api_result"), CaptureQueriesContext(connection) as baseline:
        before = client.get("/api/auth/me")
    console_output.truncate(0)
    console_output.seek(0)
    with CaptureQueriesContext(connection) as observed:
        after = client.get("/api/auth/me")
    assert before.status_code == after.status_code == 200
    assert before.json() == after.json()
    assert len(baseline) > 0 and len(observed) == len(baseline)
    assert len(console_output.getvalue().splitlines()) == 1
    assert "api_request status=200" in console_output.getvalue()


def test_live_with_cookie_remains_database_free(client: Any, console_output: StringIO) -> None:
    from unittest.mock import patch
    client.cookies["sessionid"] = "untrusted-session-cookie"
    with patch("django.db.backends.base.base.BaseDatabaseWrapper.cursor", side_effect=AssertionError):
        response = client.get("/api/health/live")
    assert response.status_code == 200
    assert "api_request status=200" in console_output.getvalue()


@pytest.mark.parametrize("mode", ["text", "json"])
@pytest.mark.parametrize("name", ["fitlog.api", "third_party"])
def test_record_auxiliary_fields_are_never_rendered(mode: str, name: str) -> None:
    class Untouchable:
        calls = 0
        def __str__(self) -> str:
            self.calls += 1
            raise AssertionError("arbitrary record objects must not be stringified")
    opaque = Untouchable()
    r = record(name)
    r.msg = opaque
    r.args = (opaque, SECRET)
    r.exc_info = (RuntimeError, RuntimeError(SECRET), None)
    r.exc_text = SECRET
    r.stack_info = SECRET
    r.__dict__["untrusted_extra"] = SECRET
    output = observation().SafeFormatter(mode=mode).format(r)
    expected = "api_request" if name == "fitlog.api" else "log_record_discarded"
    if mode == "json":
        assert json.loads(output)["event"] == expected
    else:
        assert expected in output
    assert SECRET not in output and opaque.calls == 0


def test_http_response_survives_configured_log_write_failure(client: Any,
                                                             console_output: StringIO,
                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    from uuid import UUID
    before = client.get("/api/health/live")
    assert before.status_code == 200 and "api_request" in console_output.getvalue()
    class BrokenStream:
        attempts = 0
        def write(self, value: str) -> None:
            self.attempts += 1
            raise OSError(SECRET)
        def flush(self) -> None:
            pass
    broken = BrokenStream()
    handlers = [h for h in logging.getLogger("fitlog.api").handlers
                if isinstance(h, observation().SafeStreamHandler)]
    assert len(handlers) == 1
    monkeypatch.setattr(handlers[0], "stream", broken)
    stderr = StringIO()
    with contextlib.redirect_stderr(stderr):
        after = client.get("/api/health/live", HTTP_X_REQUEST_ID=SECRET)
    assert after.status_code == 200 and after.json() == before.json() == {"status": "ok"}
    assert str(UUID(after["X-Request-Id"])) == after["X-Request-Id"]
    assert after["X-Request-Id"] != before["X-Request-Id"]
    assert broken.attempts == 1 and stderr.getvalue() == ""
