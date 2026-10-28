"""テストは開発DBから分離したPostgreSQL DBに限定する。"""
import logging
from collections.abc import Iterator
from io import StringIO
from typing import Any

import pytest
from django.db import connection
from django.test import Client


@pytest.fixture
def client() -> Client:
    return Client(raise_request_exception=False, SERVER_NAME="localhost")


@pytest.fixture
def api_log_output(monkeypatch: pytest.MonkeyPatch) -> StringIO:
    """Capture configured sinks without changing propagation or adding handlers."""
    output = StringIO()
    seen: set[int] = set()
    for name in ("fitlog.api", "django.request", "django"):
        current: logging.Logger | None = logging.getLogger(name)
        while current is not None:
            for handler in current.handlers:
                if isinstance(handler, logging.StreamHandler) and id(handler) not in seen:
                    monkeypatch.setattr(handler, "stream", output)
                    seen.add(id(handler))
            if not current.propagate:
                break
            current = current.parent
    return output


@pytest.fixture(scope="session")
def django_db_setup(
    django_db_setup: Any, django_db_blocker: Any,
) -> Iterator[None]:
    # pytest-djangoの同名fixtureを先に実行し、新規DBへmigrationを適用する。
    with django_db_blocker.unblock():
        assert connection.vendor == "postgresql"
        assert connection.settings_dict["NAME"] == "test_fitlog"
    yield
