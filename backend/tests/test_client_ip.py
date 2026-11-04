"""承認仕様の固定IP/時刻を使い、認証POSTと実DBで信頼境界を検証する。"""
from datetime import UTC, datetime
from typing import Any

import pytest

from accounts.models import AuthRateLimit, User
from tests.test_auth import PASSWORD, api_client, token

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("django.utils.timezone.now", lambda: datetime(2026, 10, 29, 12, 34, 56, tzinfo=UTC))


@pytest.mark.parametrize("path", ["login", "signup"])
@pytest.mark.parametrize("value", [None, "", " " , "192.0.2.1 ", "192.0.2.1,192.0.2.2",
    "192.0.2.1:443", "[2001:db8::1]:443", "fe80::1%eth0", "not-an-ip", "1" * 46])
def test_bad_cloudfront_ip_refuses_before_writes(
    settings: Any, path: str, value: str | None, capsys: pytest.CaptureFixture[str],
) -> None:
    settings.FITLOG_AUTH_CLIENT_IP_SOURCE = "cloudfront"
    client = api_client()
    csrf = token(client)
    if value is not None:
        client.defaults["HTTP_X_FITLOG_CLIENT_IP"] = value
    response = client.post(f"/api/auth/{path}", data={"username": "ip_user", "display_name": "IP",
        "email": "ip@example.test", "password": PASSWORD}, content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf, REMOTE_ADDR="10.0.1.8", HTTP_X_FORWARDED_FOR="192.0.2.99")
    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"
    assert not AuthRateLimit.objects.exists()
    assert not User.objects.exists()
    assert response.headers["Cache-Control"] == "no-store"
    captured = capsys.readouterr()
    output = response.content.decode() + captured.out + captured.err
    for secret in ["10.0.1.8", "192.0.2.99", "ip@example.test", PASSWORD, "not-an-ip", "fe80::1%eth0"]:
        assert secret not in output
    if value and value.strip():
        assert value not in output


@pytest.mark.parametrize("first,second,same", [
    ("192.0.2.1", "192.0.2.2", False),
    ("2001:db8::1", "2001:db8::ffff", True),
    ("2001:db8::1", "2001:db8:0:1::1", False),
    ("192.0.2.1", "::ffff:192.0.2.1", True),
])
def test_cloudfront_network_budgets_and_endpoint_sharing(settings: Any, first: str, second: str, same: bool) -> None:
    settings.FITLOG_AUTH_CLIENT_IP_SOURCE = "cloudfront"
    client = api_client()
    csrf = token(client)
    for index in range(10):
        response = client.post(f"/api/auth/{'login' if index % 2 else 'signup'}", data="{}",
            content_type="application/json", HTTP_X_CSRFTOKEN=csrf,
            REMOTE_ADDR="10.0.1.8", HTTP_X_FITLOG_CLIENT_IP=first)
        assert response.status_code == 400
    response = client.post("/api/auth/login", data="{}", content_type="application/json", HTTP_X_CSRFTOKEN=csrf,
        REMOTE_ADDR="10.0.1.8", HTTP_X_FITLOG_CLIENT_IP=second, HTTP_X_FORWARDED_FOR="192.0.2.250")
    assert response.status_code == (429 if same else 400)
    if same:
        assert response.headers["Retry-After"] == "4"
    assert sorted(AuthRateLimit.objects.values_list("count", flat=True)) == ([11] if same else [1, 10])


def test_direct_mode_ignores_all_forwarding_headers(settings: Any) -> None:
    settings.FITLOG_AUTH_CLIENT_IP_SOURCE = "remote_addr"
    client = api_client()
    csrf = token(client)
    for index in range(11):
        response = client.post("/api/auth/login", data="{}", content_type="application/json", HTTP_X_CSRFTOKEN=csrf,
            REMOTE_ADDR="192.0.2.1", HTTP_X_FITLOG_CLIENT_IP=f"192.0.2.{index + 10}",
            HTTP_X_FORWARDED_FOR=f"192.0.2.{index + 20}")
        assert response.status_code == (400 if index < 10 else 429)
    assert AuthRateLimit.objects.get().count == 11


def test_existing_csrf_and_method_guards_precede_ip(settings: Any) -> None:
    settings.FITLOG_AUTH_CLIENT_IP_SOURCE = "cloudfront"
    client = api_client()
    assert client.post("/api/auth/login", data="{}", content_type="application/json").status_code == 403
    assert client.get("/api/auth/signup").status_code == 405
    assert not AuthRateLimit.objects.exists()
