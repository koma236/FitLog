"""FitLogの環境設定。実認証情報を保存しない。"""
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
    "common.middleware.AuthSessionMiddleware",
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
        "ATOMIC_REQUESTS": False,
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

# HTTPSが既定。ローカルHTTPを使う場合だけ2つの明示設定が必要。
FITLOG_ENV = os.environ.get("FITLOG_ENV", "production")
FITLOG_LOCAL_HTTP = os.environ.get("FITLOG_LOCAL_HTTP", "0")
if FITLOG_ENV not in {"local", "production"} or FITLOG_LOCAL_HTTP not in {"0", "1"}:
    raise ImproperlyConfigured("Invalid FitLog environment configuration")
if FITLOG_ENV != "local" and FITLOG_LOCAL_HTTP == "1":
    raise ImproperlyConfigured("Local HTTP is only permitted in local environment")
AUTH_RATE_LIMIT_HMAC_KEY = os.environ.get("AUTH_RATE_LIMIT_HMAC_KEY", "")
LOCAL_HMAC_SAMPLE = "fitlog-local-only-public-hmac-key-never-use-in-production"
if len(AUTH_RATE_LIMIT_HMAC_KEY) < 32 or (
    FITLOG_ENV == "production" and AUTH_RATE_LIMIT_HMAC_KEY == LOCAL_HMAC_SAMPLE
):
    raise ImproperlyConfigured("A private AUTH_RATE_LIMIT_HMAC_KEY of at least 32 characters is required")
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 7 * 24 * 60 * 60
SESSION_SAVE_EVERY_REQUEST = False
SESSION_COOKIE_SECURE = not (FITLOG_ENV == "local" and FITLOG_LOCAL_HTTP == "1")
SESSION_COOKIE_PATH = "/"
SESSION_COOKIE_DOMAIN = None
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_PATH = "/"
CSRF_COOKIE_DOMAIN = None
CSRF_TRUSTED_ORIGINS: list[str] = []
AUTHENTICATION_BACKENDS = ["accounts.backends.EmailBackend"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
     "OPTIONS": {"user_attributes": ["username", "email", "display_name"]}},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
