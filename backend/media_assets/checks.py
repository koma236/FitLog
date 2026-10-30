from django.conf import settings
from django.core.checks import Error, register


@register()
def private_storage_configuration(app_configs: object, **kwargs: object) -> list[Error]:
    if (
        settings.FITLOG_ENV != "local"
        or getattr(settings, "PRIVATE_MEDIA_BACKEND", "local") != "local"
    ):
        return [
            Error(
                "Private image storage requires the local adapter until S3 deployment is configured.",
                id="media_assets.E001",
            )
        ]
    return []
