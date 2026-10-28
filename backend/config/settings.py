"""FL-01のローカル設定。実認証情報を保存しない。"""
import os
from typing import Any

from django.core.exceptions import ImproperlyConfigured

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY.strip():
    raise ImproperlyConfigured("DJANGO_SECRET_KEY is required")
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "backend"]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "rest_framework",
    "accounts",
]
MIDDLEWARE = [
    "common.middleware.ApiBoundaryMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]
AUTH_USER_MODEL = "accounts.User"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
DATABASES: dict[str, Any] = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "fitlog"),
        "USER": os.environ.get("POSTGRES_USER", "fitlog"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "postgres"),
        "PORT": "5432",
        "OPTIONS": {"connect_timeout": 5},
        "TEST": {"NAME": "test_fitlog"},
    },
}
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "common.errors.api_exception_handler",
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
}
LANGUAGE_CODE = "ja"
TIME_ZONE = "UTC"
USE_TZ = True
APPEND_SLASH = False
CSRF_FAILURE_VIEW = "common.errors.csrf_failure"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
# Djangoの標準エラーロガーは例外本文・リクエストを渡すため、そのまま出力しない。
# API境界の固定event/code/request-idだけを出す。
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"safe": {"format": "%(levelname)s %(message)s"}},
    "handlers": {
        "null": {"class": "logging.NullHandler"},
        "console": {"class": "logging.StreamHandler", "formatter": "safe"},
    },
    "loggers": {
        "django": {"handlers": ["null"], "propagate": False},
        "fitlog.api": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
