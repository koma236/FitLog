"""Strict social JSON and Unicode boundary, without reflecting submitted input."""

import math
from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError

from accounts.profile_validation import decode_profile

FORM = "入力内容を確認してください。"


def canonical_uuid(value: object, *, v4: bool = False) -> UUID:
    if not isinstance(value, str):
        raise ValueError("UUID type")
    try:
        identity = UUID(value)
    except ValueError:
        raise ValueError("UUID format") from None
    if str(identity) != value or (v4 and identity.version != 4):
        raise ValueError("UUID format")
    return identity


def decode(raw: bytes) -> object:
    value = decode_profile(raw)

    def inspect(item: object, depth: int) -> None:
        if isinstance(item, (dict, list)):
            if depth > 4:
                raise ValueError("JSON depth")
            for child in item.values() if isinstance(item, dict) else item:
                inspect(child, depth + 1)
        elif isinstance(item, float) and not math.isfinite(item):
            raise ValueError("JSON number")

    inspect(value, 1)
    return value


def validate(value: object, *, creating: bool) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != ({"id", "body"} if creating else {"body"}):
        raise ValidationError({"_form": [FORM]})
    result: dict[str, Any] = {}
    if creating:
        try:
            result["id"] = canonical_uuid(value["id"], v4=True)
        except ValueError:
            raise ValidationError({"id": [FORM]}) from None
    body = value["body"]
    if not isinstance(body, str):
        raise ValidationError({"body": [FORM]})
    body = body.replace("\r\n", "\n")
    if any(
        (ord(c) < 32 and c not in "\n\t") or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF
        for c in body
    ):
        raise ValidationError({"body": [FORM]})
    body = body.strip()
    if not 1 <= len(body) <= 500:
        raise ValidationError({"body": [FORM]})
    result["body"] = body
    return result
