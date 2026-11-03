"""Gunicorn logs retain only fixed operational events, never request data."""
import json
import logging
from io import StringIO
from typing import Any

import pytest


@pytest.mark.parametrize("level,event", [(logging.INFO, "server_info"), (logging.WARNING, "server_warning"), (logging.ERROR, "server_error"), (logging.CRITICAL, "server_critical")])
def test_gunicorn_drops_message_arguments_and_traceback(level: int, event: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from gunicorn.config import Config

    from common.gunicorn_logging import SafeGunicornLogger

    monkeypatch.setenv("FITLOG_LOG_FORMAT", "json")
    sink = StringIO()
    logger = SafeGunicornLogger(Config())
    for handler in logger.error_log.handlers:
        monkeypatch.setattr(handler, "stream", sink)
    try:
        raise ValueError("PRIVATE-TRACE-TOKEN")
    except ValueError:
        logger.error_log.log(level, "Error handling /api/media/content/%s", "PRIVATE-URL-TOKEN", exc_info=True)
    data = sink.getvalue()
    assert "PRIVATE" not in data and "Traceback" not in data
    row = json.loads(data)
    assert row["event"] == event
    assert row["level"] == logging.getLevelName(level)
    assert set(row) == {"timestamp", "level", "event", "request_id", "app_version"}


def test_gunicorn_access_sink_is_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from gunicorn.config import Config

    from common.gunicorn_logging import SafeGunicornLogger

    logger = SafeGunicornLogger(Config())
    assert logger.access_log.disabled and not logger.access_log.handlers


def test_broken_server_log_sink_never_dumps_original_record(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    from gunicorn.config import Config

    from common.gunicorn_logging import SafeGunicornLogger

    class Broken:
        def write(self, value: str) -> None:
            raise OSError("PRIVATE-PIPE")
        def flush(self) -> None:
            pass

    logger = SafeGunicornLogger(Config())
    for handler in logger.error_log.handlers:
        monkeypatch.setattr(handler, "stream", Broken())
    logger.error_log.error("PRIVATE-MESSAGE")
    assert "PRIVATE" not in capsys.readouterr().err
