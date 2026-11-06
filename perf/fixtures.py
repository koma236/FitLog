"""Independent fixed fixture specification; no imports from product services."""
import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

VERSION = "fl10b-v1"
PASSWORD = "Perf-only-2026-fixed-password!"
USERS = 5
POSTS = 1000


def identity(kind, number):
    return UUID(bytes=hashlib.sha256(f"{VERSION}:{kind}:{number}".encode()).digest()[:16], version=4)


def user_id(actor):
    return identity("user", actor)


def post_id(index):
    return identity("post", index)


def username(actor):
    return f"perf_member_{actor}"


def dimensions(scenario):
    if scenario not in {"normal", "boundary"}:
        raise ValueError("unknown fixed scenario")
    return (3, 3) if scenario == "normal" else (10, 20)


def timestamp(index):
    return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=index)


def indices(actor, scope):
    allowed = {actor} if scope == "user" else {actor, (actor + 1) % 5, (actor + 2) % 5}
    return [i for i in reversed(range(POSTS)) if scope == "all" or i % 5 in allowed]


def payload(scenario):
    exercises, sets = dimensions(scenario)
    return {"performed_on": "2026-01-01", "note": "固定性能試験",
            "exercises": [{"name": f"Exercise {e}", "sets": [
                {"weight_kg": "60.00", "reps": 10} for _ in range(sets)]}
                for e in range(exercises)],
            "energy_input": {"minutes": None, "kind": None},
            "visibility": {"minutes": "private", "kind": "private"}, "recalculate": False}


def post_dto(index, actor, scenario):
    """Minimal independently specified fields for validator tests."""
    return {"id": str(post_id(index)), "viewer_id": str(user_id(actor)),
            "author": {"id": str(user_id(index % 5))}, "is_owner": index % 5 == actor,
            **{k: v for k, v in payload(scenario).items() if k in {"exercises", "note", "performed_on"}}}


def check_post(value, index, actor, scenario):
    expected = post_dto(index, actor, scenario)
    if not isinstance(value, dict) or any(value.get(k) != v for k, v in expected.items()
                                          if k != "author"):
        raise ValueError("post content mismatch")
    if not isinstance(value.get("author"), dict) or value["author"].get("id") != expected["author"]["id"]:
        raise ValueError("post owner mismatch")


def check_listing(value, actor, scope, page, scenario):
    expected = indices(actor, scope)[page * 20:(page + 1) * 20]
    if (not isinstance(value, dict) or value.get("viewer_id") != str(user_id(actor))
            or not isinstance(value.get("items"), list) or len(value["items"]) != len(expected)
            or not isinstance(value.get("next_cursor"), str) or not value["next_cursor"]):
        raise ValueError("listing shape mismatch")
    for item, index in zip(value["items"], expected, strict=True):
        check_post(item, index, actor, scenario)
