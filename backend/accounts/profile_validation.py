"""プロフィール更新の厳密な入力境界。未知のキーや値をエラーへ反射しない。"""
import json
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from typing import cast

from django.core.exceptions import ValidationError

from accounts.validation import normalized_display_name

HEALTH_KEYS = ("height", "weight", "age", "formula", "activity")
ENERGY_KEYS = ("bmr", "tdee", "intake")
PROFILE_KEYS = HEALTH_KEYS + ENERGY_KEYS
DECIMAL_TEXT = re.compile(r"(0|[1-9][0-9]{0,2})(\.[0-9])?")


@dataclass(frozen=True)
class ProfileUpdate:
    display_name: str
    bio: str
    height: Decimal | None
    weight: Decimal | None
    age: int | None
    formula: str | None
    activity: str | None
    visibility: dict[str, bool]


def unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def valid_unicode(value: object) -> None:
    if isinstance(value, str):
        value.encode("utf-8")
    elif isinstance(value, dict):
        for key, item in value.items():
            valid_unicode(key)
            valid_unicode(item)
    elif isinstance(value, list):
        for item in value:
            valid_unicode(item)


def decode_profile(raw: bytes) -> object:
    value: object = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs)
    valid_unicode(value)
    return value


def validate_profile(value: object) -> ProfileUpdate:
    errors: dict[str, list[str]] = {}

    def invalid(path: str, message: str = "入力を確認してください。") -> None:
        errors[path] = [message]

    def fields(raw: object, keys: tuple[str, ...], prefix: str = "") -> dict[str, object]:
        form = prefix + "_form"
        if not isinstance(raw, dict):
            invalid(form, "入力内容を確認してください。")
            return {}
        data = cast(dict[str, object], raw)
        if set(data) - set(keys):
            invalid(form, "入力内容を確認してください。")
        for key in set(keys) - set(data):
            invalid(prefix + key)
        return data

    data = fields(value, ("display_name", "bio", "health", "visibility"))
    name = data.get("display_name")
    display_name = ""
    if isinstance(name, str):
        try:
            display_name = normalized_display_name(name)
        except ValidationError:
            invalid("display_name", "表示名は1〜50文字で入力してください。")
    else:
        invalid("display_name", "表示名は1〜50文字で入力してください。")
    text = data.get("bio")
    bio = text.replace("\r\n", "\n").replace("\r", "\n") if isinstance(text, str) else ""
    if not isinstance(text, str) or len(bio) > 160 or any(unicodedata.category(c) == "Cc" and c not in "\n\t" for c in bio):
        invalid("bio", "自己紹介は160文字以内で入力してください。")
    health = fields(data.get("health"), HEALTH_KEYS, "health.")
    visibility = fields(data.get("visibility"), PROFILE_KEYS, "visibility.")

    def decimal(key: str, low: int, high: int) -> Decimal | None:
        item = health.get(key)
        if item is None:
            return None
        if not isinstance(item, str) or DECIMAL_TEXT.fullmatch(item) is None:
            invalid("health." + key)
            return None
        number = Decimal(item)
        if not low <= number <= high:
            invalid("health." + key)
        return number

    height, weight = decimal("height", 100, 250), decimal("weight", 20, 350)
    age = health.get("age")
    if age is not None and (not isinstance(age, int) or isinstance(age, bool) or not 0 <= age <= 120):
        invalid("health.age")
    formula, activity = health.get("formula"), health.get("activity")
    for key, item, options in [("formula", formula, {"male", "female"}), ("activity", activity, {"low", "medium", "high"})]:
        if item is not None and (not isinstance(item, str) or item not in options):
            invalid("health." + key)
    flags: dict[str, bool] = {}
    for key in PROFILE_KEYS:
        item = visibility.get(key)
        if not isinstance(item, str) or item not in {"public", "private"}:
            invalid("visibility." + key)
        flags[key] = item == "public"
    if errors:
        raise ValidationError(errors)
    return ProfileUpdate(display_name, bio, height, weight, cast(int | None, age), cast(str | None, formula), cast(str | None, activity), flags)
