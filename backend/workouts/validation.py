"""Strict JSON boundary: never reflect untrusted keys or values in errors."""

import re
import unicodedata
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.utils import timezone

from accounts.profile_validation import decode_profile

FORM = "入力内容を確認してください。"
WHITE_SPACE = "\t\n\v\f\r \x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000"
BIDI = set("\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")
KINDS = {"general", "squat", "vigorous"}


def canonical_uuid(value: object, *, v4: bool = False) -> UUID:
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", value.lower()
    ):
        raise ValueError("Invalid UUID")
    result = UUID(value)
    if v4 and result.version != 4:
        raise ValueError("Invalid UUID version")
    return result


def decode(raw: bytes) -> object:
    value = decode_profile(raw)

    def depth(item: object, level: int) -> None:
        if isinstance(item, (dict, list)):
            if level > 8:
                raise ValueError("Too deep")
            for child in item.values() if isinstance(item, dict) else item:
                depth(child, level + 1)
        elif isinstance(item, float):
            # JSON NaN/Infinity are never accepted, including in unknown fields.
            import math

            if not math.isfinite(item):
                raise ValueError("Non-finite")

    depth(value, 1)
    return value


def validate(value: object, *, creating: bool) -> dict[str, Any]:
    errors: dict[str, list[str]] = {}

    def invalid(path: str, message: str = FORM) -> None:
        if len(errors) < 32:
            errors[path] = [message]

    def fields(item: object, keys: set[str], prefix: str = "") -> dict[str, Any]:
        if not isinstance(item, dict):
            invalid(prefix + "_form")
            return {}
        if set(item) != keys:
            invalid(prefix + "_form")
        return item

    keys = {
        "performed_on",
        "note",
        "exercises",
        "energy_input",
        "visibility",
        "id" if creating else "recalculate",
    }
    data = fields(value, keys)
    result: dict[str, Any] = {}
    if creating:
        try:
            result["id"] = canonical_uuid(data.get("id"), v4=True)
        except ValueError:
            invalid("id")
    elif type(data.get("recalculate")) is not bool:
        invalid("recalculate", "再計算の指定を確認してください。")
    else:
        result["recalculate"] = data["recalculate"]
    day = data.get("performed_on")
    try:
        if not isinstance(day, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day):
            raise ValueError("Date")
        performed = date.fromisoformat(day)
        if performed > timezone.now().astimezone(ZoneInfo("Asia/Tokyo")).date():
            raise ValueError("Future")
        result["performed_on"] = performed
    except ValueError:
        invalid("performed_on", "トレーニング日は今日以前の正しい日付を入力してください。")
    note = data.get("note")
    if isinstance(note, str):
        note = note.replace("\r\n", "\n").replace("\r", "\n")
    if (
        not isinstance(note, str)
        or len(note) > 500
        or any(c in BIDI or (unicodedata.category(c) == "Cc" and c not in "\n\t") for c in note)
    ):
        invalid("note", "メモは500文字以内で入力してください。")
    result["note"] = note
    energy = fields(data.get("energy_input"), {"minutes", "kind"}, "energy_input.")
    minutes, kind = energy.get("minutes"), energy.get("kind")
    if minutes is not None and (type(minutes) is not int or not 1 <= minutes <= 240):
        invalid("energy_input.minutes", "運動時間は1〜240分の整数で入力してください。")
    if kind is not None and (not isinstance(kind, str) or kind not in KINDS):
        invalid("energy_input.kind", "トレーニングの種類を選択肢から選んでください。")
    result.update(minutes=minutes, kind=kind)
    flags = fields(data.get("visibility"), {"minutes", "kind"}, "visibility.")
    for key in ["minutes", "kind"]:
        if not isinstance(flags.get(key), str) or flags[key] not in {"public", "private"}:
            invalid("visibility." + key, "公開範囲を選択してください。")
        result[key + "_public"] = flags.get(key) == "public"
    exercises = data.get("exercises")
    result["exercises"] = []
    if not isinstance(exercises, list) or not 1 <= len(exercises) <= 10:
        invalid("exercises", "種目は1〜10個で入力してください。")
    else:
        for i, exercise in enumerate(exercises):
            prefix = f"exercises.{i}."
            ex = fields(exercise, {"name", "sets"}, prefix)
            name = ex.get("name")
            name = name.strip(WHITE_SPACE) if isinstance(name, str) else ""
            if not 1 <= len(name) <= 80 or any(
                c in BIDI or unicodedata.category(c) == "Cc" for c in name
            ):
                invalid(prefix + "name", "種目名は1〜80文字で入力してください。")
            sets = ex.get("sets")
            rows = []
            if not isinstance(sets, list) or not 1 <= len(sets) <= 20:
                invalid(prefix + "sets", "セットは1〜20個で入力してください。")
            else:
                for j, row in enumerate(sets):
                    path = prefix + f"sets.{j}."
                    item = fields(row, {"weight_kg", "reps"}, path)
                    weight, reps = item.get("weight_kg"), item.get("reps")
                    number = None
                    if not isinstance(weight, str) or not re.fullmatch(
                        r"(0|[1-9][0-9]{0,2})(\.[0-9]{1,2})?", weight
                    ):
                        invalid(
                            path + "weight_kg", "重量は0〜999.99kg、小数2桁までで入力してください。"
                        )
                    else:
                        number = Decimal(weight)
                    if type(reps) is not int or not 1 <= reps <= 999:
                        invalid(path + "reps", "回数は1〜999の整数で入力してください。")
                    rows.append({"weight_kg": number, "reps": reps})
            result["exercises"].append({"name": name, "sets": rows})
    if errors:
        raise ValidationError(errors)
    return result
