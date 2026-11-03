from importlib import import_module

from django.apps import AppConfig
from django.core.exceptions import ImproperlyConfigured

from media_assets.configuration import storage_configuration_valid


class MediaAssetsConfig(AppConfig):
    name = "media_assets"

    def ready(self) -> None:
        if not storage_configuration_valid():
            raise ImproperlyConfigured(
                "Invalid private storage environment configuration"
            )
        import_module("media_assets.checks")
        import_module("media_assets.signals")
