"""Pure storage configuration checks; never instantiate an AWS client."""
import re
from dataclasses import dataclass

from django.conf import settings


@dataclass(frozen=True)
class S3Configuration:
    bucket: str
    owner: str
    region: str
    prefix: str = "images/"

    def __post_init__(self) -> None:
        if (type(self.bucket) is not str
                or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", self.bucket)
                or self.bucket.endswith(("-s3alias", "--ol-s3", "--x-s3", "--table-s3"))
                or type(self.owner) is not str or not re.fullmatch(r"[0-9]{12}", self.owner)
                or self.region != "ap-northeast-1" or self.prefix != "images/"):
            raise ValueError("Invalid private S3 configuration")


def s3_configuration() -> S3Configuration:
    return S3Configuration(
        getattr(settings, "PRIVATE_MEDIA_BUCKET", ""),
        getattr(settings, "PRIVATE_MEDIA_EXPECTED_OWNER", ""),
        getattr(settings, "PRIVATE_MEDIA_REGION", ""),
    )


def storage_configuration_valid() -> bool:
    pair = (settings.FITLOG_ENV, settings.PRIVATE_MEDIA_BACKEND)
    if pair == ("local", "local"):
        return True
    if pair != ("production", "s3"):
        return False
    try:
        s3_configuration()
    except ValueError:
        return False
    return True
