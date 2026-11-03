"""Configuration errors must be rejected before serving or contacting AWS."""
import json
import os
import ssl
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


def test_storage_truth_table_adds_only_production_s3(settings: Any) -> None:
    from media_assets.checks import private_storage_configuration

    settings.PRIVATE_MEDIA_BUCKET = "fitlog-test-private"
    settings.PRIVATE_MEDIA_EXPECTED_OWNER = "123456789012"
    settings.PRIVATE_MEDIA_REGION = "ap-northeast-1"
    for environment, backend, ok in [("local", "local", True), ("production", "s3", True), ("local", "s3", False), ("production", "local", False), ("other", "s3", False)]:
        settings.FITLOG_ENV = environment
        settings.PRIVATE_MEDIA_BACKEND = backend
        assert (not private_storage_configuration(None)) == ok


def test_local_factory_does_not_initialize_sdk(settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from media_assets.storage import LocalStorage, get_storage

    settings.FITLOG_ENV = "local"
    settings.PRIVATE_MEDIA_BACKEND = "local"
    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Local mode attempted AWS credential discovery")
    monkeypatch.setattr("boto3.client", forbidden)
    assert isinstance(get_storage(), LocalStorage)


@pytest.fixture
def production_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("AWS_", "DJANGO_", "PRIVATE_MEDIA_", "FITLOG_", "POSTGRES_", "AUTH_RATE_"))}
    env.update(DJANGO_SETTINGS_MODULE="config.production", FITLOG_ENV="production", DJANGO_SECRET_KEY="S" * 64, AUTH_RATE_LIMIT_HMAC_KEY="H" * 64, FITLOG_PUBLIC_HOST="d111111abcdef8.cloudfront.net", PRIVATE_MEDIA_BUCKET="fitlog-test-private", PRIVATE_MEDIA_EXPECTED_OWNER="123456789012", AWS_REGION="ap-northeast-1", POSTGRES_HOST="demo.example.rds.amazonaws.com", POSTGRES_DB="fitlog", POSTGRES_USER="fitlog", POSTGRES_PASSWORD="test-only-database-password", POSTGRES_SSLROOTCERT=str(ssl.get_default_verify_paths().cafile), AWS_EC2_METADATA_DISABLED="true")
    return env


def run_settings(env: dict[str, str], code: str = "") -> subprocess.CompletedProcess[str]:
    script = "import django; django.setup(); from django.conf import settings; " + (code or "print(settings.PRIVATE_MEDIA_BACKEND)")
    return subprocess.run([sys.executable, "-c", script], env=env, cwd=Path(__file__).parents[1], text=True, capture_output=True, timeout=15)


def test_production_module_initializes_s3_without_network(production_env: dict[str, str]) -> None:
    r = run_settings(production_env, "import json; print(json.dumps([settings.ALLOWED_HOSTS, settings.SESSION_COOKIE_SECURE, settings.DATABASES['default']['OPTIONS']['sslmode'], settings.DEBUG]))")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [["d111111abcdef8.cloudfront.net"], True, "verify-full", False]


@pytest.mark.parametrize("name,value", [("DJANGO_SECRET_KEY", "short"), ("DJANGO_SECRET_KEY", "fitlog-local-only-public-hmac-key-never-use-in-production"), ("AUTH_RATE_LIMIT_HMAC_KEY", "fitlog-local-only-public-key-never-use-in-production"), ("PRIVATE_MEDIA_BACKEND", "local"), ("AUTH_RATE_LIMIT_HMAC_KEY", "fitlog-local-only-public-hmac-key-never-use-in-production"), ("FITLOG_PUBLIC_HOST", "*.cloudfront.net"), ("FITLOG_PUBLIC_HOST", "http://d111111abcdef8.cloudfront.net"), ("PRIVATE_MEDIA_EXPECTED_OWNER", "123"), ("AWS_REGION", "us-east-1"), ("POSTGRES_PASSWORD", ""), ("POSTGRES_SSLROOTCERT", "/missing/ca.pem"), ("FITLOG_TRUST_PROXY", "yes")])
def test_invalid_production_config_fails_without_echoing_values(production_env: dict[str, str], name: str, value: str) -> None:
    production_env[name] = value
    r = run_settings(production_env)
    assert r.returncode != 0
    assert production_env["POSTGRES_PASSWORD"] not in r.stderr if production_env["POSTGRES_PASSWORD"] else True
    assert "S" * 64 not in r.stderr and "H" * 64 not in r.stderr


def test_health_host_exception_is_exact_and_production_only(production_env: dict[str, str]) -> None:
    script = "from django.test import Client; c=Client(SERVER_NAME='10.0.1.8'); print([c.get(p).status_code for p in ['/api/health/live','/api/health/ready','/api/health/livex','/api/auth/csrf']])"
    r = run_settings(production_env, script)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().splitlines()[-1] == "[200, 400, 400, 400]"


@pytest.mark.parametrize("enabled,want", [("0", False), ("1", True)])
def test_only_explicit_proxy_mode_trusts_dedicated_header(production_env: dict[str, str], enabled: str, want: bool) -> None:
    production_env["FITLOG_TRUST_PROXY"] = enabled
    r = run_settings(production_env, "from django.test import RequestFactory; r=RequestFactory().get('/',HTTP_X_FITLOG_FORWARDED_PROTO='https',HTTP_X_FORWARDED_PROTO='https'); print(r.is_secure())")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == str(want)
