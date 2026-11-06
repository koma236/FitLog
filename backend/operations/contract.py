"""Non-secret target metadata and in-memory private values."""
import json
import re
import secrets
import uuid
from dataclasses import dataclass

REGION = "ap-northeast-1"
KEYS = ("DJANGO_SECRET_KEY", "AUTH_RATE_LIMIT_HMAC_KEY", "POSTGRES_PASSWORD")


class BootstrapError(Exception):
    """Fixed messages only, never embed upstream exceptions or private values."""

    def __init__(self) -> None:
        super().__init__("bootstrap_failed")


def require(condition: bool) -> None:
    if not condition:
        raise BootstrapError()


@dataclass(frozen=True)
class Request:
    account: str
    environment: str
    database: str
    application_arn: str
    distribution: str
    operation: str

    def __post_init__(self) -> None:
        require(re.fullmatch(r"[0-9]{12}", self.account) is not None)
        require(len(self.environment) <= 24 and re.fullmatch(
            r"fitlog-demo-[a-z0-9]+(?:-[a-z0-9]+)*", self.environment,
        ) is not None)
        require(self.database == self.environment)
        require(re.fullmatch(
            rf"arn:aws:secretsmanager:{REGION}:{self.account}:secret:"
            + re.escape(self.environment) + r"/application-[A-Za-z0-9]{6}",
            self.application_arn,
        ) is not None)
        require(re.fullmatch(r"[A-Z0-9]{1,32}", self.distribution) is not None)
        try:
            require(str(uuid.UUID(self.operation)) == self.operation)
        except ValueError:
            raise BootstrapError() from None

    @property
    def service(self) -> str:
        return self.environment + "-backend"

    def marker(self) -> tuple[str, ...]:
        return (self.operation, self.account, REGION, self.environment,
                self.database, self.application_arn, self.operation)


@dataclass(frozen=True, repr=False)
class SecretValues:
    django: str
    hmac: str
    password: str

    def __post_init__(self) -> None:
        values = (self.django, self.hmac, self.password)
        require(all(isinstance(value, str) and re.fullmatch(
            r"[A-Za-z0-9_-]{64}", value,
        ) is not None for value in values))
        require(len(set(values)) == 3)

    @classmethod
    def generate(cls) -> "SecretValues":
        return cls(*(secrets.token_urlsafe(48) for _ in KEYS))

    @classmethod
    def decode(cls, raw: str) -> "SecretValues":
        try:
            data = json.loads(raw)
            require(isinstance(data, dict) and set(data) == set(KEYS))
            return cls(*(data[key] for key in KEYS))
        except (ValueError, TypeError, KeyError):
            raise BootstrapError() from None

    def encode(self) -> str:
        return json.dumps(dict(zip(KEYS, (self.django, self.hmac, self.password), strict=True)),
                          sort_keys=True)
