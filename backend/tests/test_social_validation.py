"""Literal Unicode and JSON boundaries from the approved social contract."""

import importlib
import importlib.util
import json
from typing import Any

import pytest
from django.core.exceptions import ValidationError


def validator() -> Any:
    assert importlib.util.find_spec("social") is not None, "social input boundary is missing"
    return importlib.import_module("social.validation")


@pytest.mark.parametrize(
    "text,want",
    [
        (" x ", "x"),
        ("\x85日本語\x85", "日本語"),
        ("\ufeff", "\ufeff"),
        ("e\u0301", "e\u0301"),
        ("😀" * 500, "😀" * 500),
        (" a\r\nb\t ", "a\nb"),
        ("<script>x</script>", "<script>x</script>"),
        ("x", "x"),
    ],
)
def test_normalizes_only_contract_whitespace(text: str, want: str) -> None:
    assert validator().validate({"body": text}, creating=False) == {"body": want}


@pytest.mark.parametrize(
    "text", ["", " \n\t", "x" * 501, "a\rb", "\x00x", "\x7fx", "\x1cx", "\ud800"]
)
def test_rejects_invalid_body_before_strip(text: str) -> None:
    with pytest.raises(ValidationError):
        validator().validate({"body": text}, creating=False)


@pytest.mark.parametrize(
    "value", [{}, {"body": 1}, {"body": "x", "extra": "x"}, {"body": "x", "id": "bad"}, []]
)
def test_rejects_unknown_missing_or_wrong_types(value: object) -> None:
    with pytest.raises(ValidationError):
        validator().validate(value, creating=False)


@pytest.mark.parametrize(
    "identity",
    ["00000000-0000-0000-0000-000000000065", "00000000-0000-4000-8000-00000000006A", "bad", 1],
)
def test_create_requires_canonical_v4(identity: object) -> None:
    with pytest.raises(ValidationError):
        validator().validate({"id": identity, "body": "x"}, creating=True)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"body":"a","body":"b"}',
        b'{"body":NaN}',
        b'{"body":"\\ud800"}',
        b"\xff",
        b'{"x":[[[[]]]]}',
    ],
)
def test_decoder_rejects_duplicate_nonfinite_unicode_and_depth(raw: bytes) -> None:
    with pytest.raises((ValueError, UnicodeError)):
        validator().decode(raw)


def test_valid_create_and_depth_four() -> None:
    from uuid import UUID

    value = validator().validate(
        {"id": "00000000-0000-4000-8000-000000000065", "body": " text "}, creating=True
    )
    assert value == {"id": UUID("00000000-0000-4000-8000-000000000065"), "body": "text"}
    assert validator().decode(json.dumps({"x": [[[]]]}).encode()) == {"x": [[[]]]}
