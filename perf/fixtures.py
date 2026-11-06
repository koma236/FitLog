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
    """Complete fixed Post contract, independently specified from OpenAPI."""
    owner = index % 5
    value = {"id": str(post_id(index)), "viewer_id": str(user_id(actor)),
             "author": {"id": str(user_id(owner)), "username": username(owner),
                        "display_name": f"性能試験 {owner}", "avatar": None},
             "is_owner": owner == actor, "image": None,
             "created_at": timestamp(index).isoformat(timespec="microseconds").replace("+00:00", "Z"),
             "updated_at": timestamp(index).isoformat(timespec="microseconds").replace("+00:00", "Z"),
             "energy": None, "energy_input": {"minutes": None, "kind": None} if owner == actor else {},
             "like_count": 2, "comment_count": 2,
             "is_liked": actor in {(owner + 1) % 5, (owner + 2) % 5},
             **{k: v for k, v in payload(scenario).items() if k in {"exercises", "note", "performed_on"}}}
    if owner == actor:
        value["visibility"] = {"minutes": "private", "kind": "private"}
    return value


def check_post(value, index, actor, scenario, liked=None):
    expected = post_dto(index, actor, scenario)
    if (not isinstance(value, dict) or set(value) != set(expected)
            or type(value["is_owner"]) is not bool or type(value["comment_count"]) is not int):
        raise ValueError("post required shape mismatch")
    if any(value[k] != v for k, v in expected.items() if k not in {"updated_at", "is_liked", "like_count"}):
        raise ValueError("post content mismatch")
    if not isinstance(value["updated_at"], str):
        raise ValueError("post timestamp missing")
    updated = datetime.fromisoformat(value["updated_at"].replace("Z", "+00:00"))
    if updated.utcoffset() != timedelta(0) or updated < timestamp(index):
        raise ValueError("post timestamp mismatch")
    enabled = liked if liked is not None else expected["is_liked"]
    count = 2 + int(liked) if liked is not None else 2
    if (type(value["is_liked"]) is not bool or value["is_liked"] is not enabled
            or type(value["like_count"]) is not int or value["like_count"] != count):
        raise ValueError("post social state mismatch")


def search_dto(actor):
    return {"viewer_id": str(user_id(actor)), "next_cursor": None, "items": [
        {"id": str(user_id(a)), "username": username(a), "display_name": f"性能試験 {a}",
         "avatar": None, "is_owner": a == actor, "follower_count": 2, "following_count": 2,
         "is_following": a in {(actor + 1) % 5, (actor + 2) % 5}}
        for a in reversed(range(5))]}


def check_search(value, actor):
    if (value != search_dto(actor) or any(type(item[k]) is not bool
                                        for item in value["items"] for k in ("is_owner", "is_following"))):
        raise ValueError("search shape, order, count or contents mismatch")


def check_listing(value, actor, scope, page, scenario):
    expected = indices(actor, scope)[page * 20:(page + 1) * 20]
    if (not isinstance(value, dict) or value.get("viewer_id") != str(user_id(actor))
            or not isinstance(value.get("items"), list) or len(value["items"]) != len(expected)
            or not isinstance(value.get("next_cursor"), str) or not value["next_cursor"]):
        raise ValueError("listing shape mismatch")
    for item, index in zip(value["items"], expected, strict=True):
        check_post(item, index, actor, scenario)
