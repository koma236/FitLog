from importlib import import_module

from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class MediaAssetsConfig(AppConfig):
    name = "media_assets"

    def ready(self) -> None:
        if settings.FITLOG_ENV != "local" or settings.PRIVATE_MEDIA_BACKEND != "local":
            raise ImproperlyConfigured(
                "Private images require the local adapter until S3 is configured"
            )
        import_module("media_assets.checks")
        import_module("media_assets.signals")
