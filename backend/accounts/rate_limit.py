"""検証済み接続元IPの固定窓。UPSERTをautocommitしてからhash処理へ進む。"""
import hashlib
import hmac
import ipaddress
import math
from datetime import UTC, datetime

from django.conf import settings
from django.db import DatabaseError, connection
from django.http import HttpRequest
from django.utils import timezone

MAX_IP_LITERAL_LENGTH = 45


def client_ip(request: HttpRequest) -> str:
    """明示した信頼経路だけを使い、不正な転送IPからfallbackしない。"""
    if settings.FITLOG_AUTH_CLIENT_IP_SOURCE == "remote_addr":
        return str(request.META.get("REMOTE_ADDR", ""))
    value = request.META.get("HTTP_X_FITLOG_CLIENT_IP", "")
    if not isinstance(value, str) or not value or len(value) > MAX_IP_LITERAL_LENGTH or "%" in value:
        raise DatabaseError("Invalid client address")
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        raise DatabaseError("Invalid client address") from None


def ip_network(value: str) -> str:
    address = ipaddress.ip_address(value)
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    prefix = 32 if isinstance(address, ipaddress.IPv4Address) else 64
    return str(ipaddress.ip_network(f"{address}/{prefix}", strict=False))


def consume_attempt(remote_addr: str) -> int | None:
    """許可ならNone、超過ならRetry-After秒。外側transactionは許可しない。"""
    if not connection.get_autocommit() or connection.in_atomic_block:
        raise DatabaseError("Auth counter requires autocommit")
    try:
        network = ip_network(remote_addr)
    except ValueError as exc:
        raise DatabaseError("Invalid connection address") from exc
    now = timezone.now().timestamp()
    window_seconds = math.floor(now / 60) * 60
    window_start = datetime.fromtimestamp(window_seconds, tz=UTC)
    digest = hmac.new(
        settings.AUTH_RATE_LIMIT_HMAC_KEY.encode(), network.encode(), hashlib.sha256,
    ).hexdigest()
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO accounts_authratelimit (ip_digest, window_start, count) "
            "VALUES (%s, %s, 1) ON CONFLICT (ip_digest, window_start) "
            "DO UPDATE SET count = accounts_authratelimit.count + 1 RETURNING count",
            [digest, window_start],
        )
        row = cursor.fetchone()
    if row is None:
        raise DatabaseError("Auth counter did not return a count")
    return min(60, max(1, math.ceil(window_seconds + 60 - now))) if row[0] > 10 else None
