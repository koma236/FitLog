"""Explicit production settings; public deployment still requires FL-09B."""
import os
import re
import ssl
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from config import settings as base
from media_assets.configuration import S3Configuration

# Inherit the trusted project's settings without a wildcard import or duplication.
globals().update({name: value for name, value in vars(base).items() if name.isupper()})


def required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value or value != value.strip():
        raise ImproperlyConfigured("Production configuration is incomplete")
    return value


if base.FITLOG_ENV != "production":
    raise ImproperlyConfigured("Production settings require the production environment")
if (len(base.SECRET_KEY) < 50
        or base.SECRET_KEY == "fitlog-local-only-public-key-never-use-in-production"
        or base.SECRET_KEY == base.LOCAL_HMAC_SAMPLE
        or base.AUTH_RATE_LIMIT_HMAC_KEY == "fitlog-local-only-public-key-never-use-in-production"
        or base.SECRET_KEY == base.AUTH_RATE_LIMIT_HMAC_KEY):
    raise ImproperlyConfigured("Production requires distinct private secrets")

DEBUG = False
PUBLIC_HOST = required("FITLOG_PUBLIC_HOST")
if not re.fullmatch(r"[a-z0-9]{1,63}\.cloudfront\.net", PUBLIC_HOST):
    raise ImproperlyConfigured("Invalid production public host")
ALLOWED_HOSTS = [PUBLIC_HOST]
CSRF_TRUSTED_ORIGINS = ["https://" + PUBLIC_HOST]
PRIVATE_MEDIA_BACKEND = os.environ.get("PRIVATE_MEDIA_BACKEND", "s3")
if PRIVATE_MEDIA_BACKEND != "s3":
    raise ImproperlyConfigured("Production requires S3 storage")
PRIVATE_MEDIA_BUCKET = required("PRIVATE_MEDIA_BUCKET")
PRIVATE_MEDIA_EXPECTED_OWNER = required("PRIVATE_MEDIA_EXPECTED_OWNER")
PRIVATE_MEDIA_REGION = required("AWS_REGION")
try:
    S3Configuration(PRIVATE_MEDIA_BUCKET, PRIVATE_MEDIA_EXPECTED_OWNER, PRIVATE_MEDIA_REGION)
except ValueError:
    raise ImproperlyConfigured("Invalid production storage configuration") from None

_proxy = os.environ.get("FITLOG_TRUST_PROXY", "0")
if _proxy not in {"0", "1"}:
    raise ImproperlyConfigured("Invalid production proxy configuration")
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FITLOG_FORWARDED_PROTO", "https") if _proxy == "1" else None
SECURE_SSL_REDIRECT = False  # HTTPS enforcement belongs to the isolated ingress.
SECURE_HSTS_SECONDS = 3600 if _proxy == "1" else 0

_ca = required("POSTGRES_SSLROOTCERT")
try:
    if not Path(_ca).is_file():
        raise OSError
    ssl.create_default_context(cafile=_ca)
except (OSError, ssl.SSLError):
    raise ImproperlyConfigured("A valid production database CA is required") from None
DATABASES = {**base.DATABASES, "default": {
    **base.DATABASES["default"],
    "HOST": required("POSTGRES_HOST"), "PASSWORD": required("POSTGRES_PASSWORD"),
    "NAME": required("POSTGRES_DB"), "USER": required("POSTGRES_USER"),
    "OPTIONS": {"connect_timeout": 5, "sslmode": "verify-full", "sslrootcert": _ca},
}}
