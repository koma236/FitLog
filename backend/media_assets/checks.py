from django.core.checks import Error, register

from media_assets.configuration import storage_configuration_valid


@register()
def private_storage_configuration(app_configs: object, **kwargs: object) -> list[Error]:
    if not storage_configuration_valid():
        return [Error("Invalid private storage environment configuration.", id="media_assets.E001")]
    return []
