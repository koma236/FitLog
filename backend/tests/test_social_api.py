"""FL-06 HTTP oracles derive from fixed actors, IDs and DB state, not DTO code."""

from typing import Any
from uuid import UUID

import pytest
from django.test import Client

from tests.test_auth import api_client, body, signup, token
from tests.test_workouts import payload, send

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def actors() -> list[tuple[Client, str]]:
    result = []
    for name in ("social_a", "social_b", "social_c"):
        client = api_client()
        result.append(
            (client, body(signup(client, token(client), name, name + "@example.test"))["id"])
        )
    return result


def social(c: Client, actor: str, method: str, path: str, data: Any = None) -> Any:
    import json

    kwargs: dict[str, Any] = {
        "HTTP_X_CSRFTOKEN": token(c),
        "HTTP_X_SOCIAL_OWNER": actor,
    }
    if data is None:
        # Client.post defaults to multipart even for {}, which is a nonempty body.
        return c.generic(method, path, data=b"", **kwargs)
    kwargs.update(data=json.dumps(data), content_type="application/json")
    return getattr(c, method.lower())(path, **kwargs)


def cid(number: int) -> str:
    return str(UUID(f"00000000-0000-4000-8000-{number:012x}"))


def test_record_has_authoritative_social_state(actors: list[tuple[Client, str]]) -> None:
    c, owner = actors[0]
    record = body(send(c, owner, "POST", "/api/posts", payload()))
    assert (record["comment_count"], record["like_count"], record["is_liked"]) == (0, 0, False)


def test_comment_and_like_have_member_bound_responses(actors: list[tuple[Client, str]]) -> None:
    a, aid = actors[0]
    b, bid = actors[1]
    record = body(send(a, aid, "POST", "/api/posts", payload()))
    path = "/api/posts/" + record["id"]
    comment = social(
        b,
        bid,
        "POST",
        path + "/comments",
        {"id": "00000000-0000-4000-8000-000000000065", "body": "ナイス！"},
    )
    assert comment.status_code == 201
    value = body(comment)
    assert value["viewer_id"] == bid and value["post_id"] == record["id"]
    assert value["comment_count"] == 1 and value["comment"]["body"] == "ナイス！"
    like = social(b, bid, "POST", path + "/like")
    assert like.status_code == 200
    assert body(like) == {
        "viewer_id": bid,
        "post_id": record["id"],
        "like_count": 1,
        "is_liked": True,
    }


def test_comment_author_only_and_record_fields_unchanged(actors: list[tuple[Client, str]]) -> None:
    a, aid = actors[0]
    b, bid = actors[1]
    c, cid_actor = actors[2]
    record = body(send(a, aid, "POST", "/api/posts", payload()))
    parent = "/api/posts/" + record["id"]
    comment_id = cid(102)
    created = body(
        social(
            b,
            bid,
            "POST",
            parent + "/comments",
            {"id": comment_id, "body": "  よくできました\r\n次も！  "},
        )
    )
    assert created["comment"]["body"] == "よくできました\n次も！"
    comment_path = "/api/comments/" + comment_id
    for client, owner in [(a, aid), (c, cid_actor)]:
        assert social(client, owner, "PUT", comment_path, {"body": "不正更新"}).status_code == 403
        assert social(client, owner, "DELETE", comment_path).status_code == 403
    updated = body(social(b, bid, "PUT", comment_path, {"body": "更新しました"}))
    assert (
        updated["comment_count"] == 1
        and updated["comment"]["created_at"] == created["comment"]["created_at"]
    )
    assert body(a.get(comment_path))["comment"]["is_owner"] is False
    current = body(a.get(parent))
    assert current["comment_count"] == 1
    for key in (
        "note",
        "created_at",
        "updated_at",
        "exercises",
        "energy",
        "energy_input",
        "visibility",
        "image",
    ):
        assert current[key] == record[key]
    deleted = social(b, bid, "DELETE", comment_path)
    assert deleted.status_code == 204 and deleted.content == b""
    assert b.get(comment_path).status_code == 404
    assert body(a.get(parent))["comment_count"] == 0
    assert (
        social(
            b, bid, "POST", parent + "/comments", {"id": comment_id, "body": "復活禁止"}
        ).status_code
        == 409
    )


def test_like_is_idempotent_and_viewer_specific(actors: list[tuple[Client, str]]) -> None:
    a, aid = actors[0]
    b, bid = actors[1]
    c, third = actors[2]
    record = body(send(a, aid, "POST", "/api/posts", payload()))
    parent = "/api/posts/" + record["id"]
    for _ in range(2):
        response = social(b, bid, "POST", parent + "/like")
        assert response.status_code == 200 and body(response)["like_count"] == 1
    assert body(social(c, third, "POST", parent + "/like"))["like_count"] == 2
    for client, expected in [(a, False), (b, True), (c, True)]:
        result = body(client.get(parent))
        assert result["like_count"] == 2 and result["is_liked"] is expected
    for _ in range(2):
        result = social(b, bid, "DELETE", parent + "/like")
        assert result.status_code == 200 and body(result)["like_count"] == 1
    assert body(social(a, aid, "POST", parent + "/like"))["like_count"] == 2


def test_inactive_comments_and_likes_share_read_and_write_visibility(
    actors: list[tuple[Client, str]],
) -> None:
    from accounts.models import User

    a, aid = actors[0]
    b, bid = actors[1]
    c, third = actors[2]
    parent = "/api/posts/" + body(send(a, aid, "POST", "/api/posts", payload()))["id"]
    comment_path = "/api/comments/" + cid(103)
    assert (
        social(
            b, bid, "POST", parent + "/comments", {"id": cid(103), "body": "Bのコメント"}
        ).status_code
        == 201
    )
    assert social(b, bid, "POST", parent + "/like").status_code == 200
    User.objects.filter(pk=bid).update(is_active=False)
    page = body(c.get(parent + "/comments"))
    assert page["comment_count"] == 0 and page["items"] == []
    assert c.get(comment_path).status_code == 404
    assert social(c, third, "PUT", comment_path, {"body": "他人"}).status_code == 404
    assert social(c, third, "DELETE", comment_path).status_code == 404
    state = body(a.get(parent))
    assert state["comment_count"] == 0 and state["like_count"] == 0
    User.objects.filter(pk=bid).update(is_active=True)
    assert body(a.get(parent))["comment_count"] == 1
    assert body(a.get(parent))["like_count"] == 1
    assert body(c.get(parent + "/comments"))["items"][0]["body"] == "Bのコメント"


def test_social_error_priority_and_cache_headers(actors: list[tuple[Client, str]]) -> None:
    a, aid = actors[0]
    b, bid = actors[1]
    parent = "/api/posts/" + body(send(a, aid, "POST", "/api/posts", payload()))["id"]
    comment_path = "/api/comments/" + cid(104)
    assert (
        social(
            b, bid, "POST", parent + "/comments", {"id": cid(104), "body": "所有者B"}
        ).status_code
        == 201
    )
    assert social(a, aid, "PUT", comment_path, {"body": ""}).status_code == 403
    foreign = social(
        b, aid, "POST", "/api/posts/" + cid(999) + "/comments", {"id": cid(105), "body": ""}
    )
    assert foreign.status_code == 409 and body(foreign)["code"] == "SOCIAL_OWNER_CHANGED"
    missing_header = b.put(
        comment_path, "{}", content_type="application/json", HTTP_X_CSRFTOKEN=token(b)
    )
    assert missing_header.status_code == 400 and body(missing_header)["code"] == "INVALID_REQUEST"
    stranger = api_client()
    assert stranger.post(parent + "/like").status_code == 403
    assert stranger.post(parent + "/like", HTTP_X_CSRFTOKEN=token(stranger)).status_code == 401
    for url in [parent + "/comments", comment_path]:
        response = a.get(url)
        assert response["Cache-Control"] == "no-store" and "Cookie" in response["Vary"]
        assert response["X-Request-Id"]
    bad_like = b.post(
        parent + "/like",
        "{}",
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token(b),
        HTTP_X_SOCIAL_OWNER=bid,
    )
    assert bad_like.status_code == 400 and body(bad_like)["code"] == "INVALID_REQUEST"


@pytest.mark.parametrize("value", ["", " \n\t", "a" * 501, "\x00", "x\ry", "\ud800"])
def test_comment_body_rejects_invalid_values(actors: list[tuple[Client, str]], value: str) -> None:
    c, owner = actors[0]
    parent = "/api/posts/" + body(send(c, owner, "POST", "/api/posts", payload()))["id"]
    result = social(c, owner, "POST", parent + "/comments", {"id": cid(200), "body": value})
    assert result.status_code == 400 and body(result)["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    "value,expected",
    [
        ("a", "a"),
        ("😀" * 500, "😀" * 500),
        ("\u0085yes\u0085", "yes"),
        ("\ufeffyes\ufeff", "\ufeffyes\ufeff"),
        ("e\u0301", "e\u0301"),
        ("<script>alert(1)</script>", "<script>alert(1)</script>"),
    ],
)
def test_comment_body_fixed_unicode_oracles(
    actors: list[tuple[Client, str]],
    value: str,
    expected: str,
) -> None:
    c, owner = actors[0]
    parent = "/api/posts/" + body(send(c, owner, "POST", "/api/posts", payload()))["id"]
    result = social(c, owner, "POST", parent + "/comments", {"id": cid(201), "body": value})
    assert result.status_code == 201 and body(result)["comment"]["body"] == expected


def test_comment_cursor_has_fixed_order_and_actor_parent_binding(
    actors: list[tuple[Client, str]],
) -> None:
    from datetime import UTC, datetime

    from social.models import Comment

    a, aid = actors[0]
    b, bid = actors[1]
    parent = "/api/posts/" + body(send(a, aid, "POST", "/api/posts", payload()))["id"]
    other_parent = "/api/posts/" + body(send(a, aid, "POST", "/api/posts", payload()))["id"]
    for number in [5, 3, 4, 1, 2]:
        assert (
            social(
                b, bid, "POST", parent + "/comments", {"id": cid(number), "body": str(number)}
            ).status_code
            == 201
        )
    Comment.objects.all().update(created_at=datetime(2026, 10, 29, 1, 2, 3, 456789, tzinfo=UTC))
    first = body(a.get(parent + "/comments", {"limit": "2"}))
    assert [row["id"] for row in first["items"]] == [cid(1), cid(2)]
    second = body(a.get(parent + "/comments", {"limit": "2", "cursor": first["next_cursor"]}))
    assert [row["id"] for row in second["items"]] == [cid(3), cid(4)]
    third = body(a.get(parent + "/comments", {"limit": "2", "cursor": second["next_cursor"]}))
    assert [row["id"] for row in third["items"]] == [cid(5)] and third["next_cursor"] is None
    for client, path, query in [
        (b, parent, {"cursor": first["next_cursor"]}),
        (a, other_parent, {"cursor": first["next_cursor"]}),
        (a, parent, {"limit": "0"}),
        (a, parent, {"unused": "1"}),
        (a, parent, {"limit": ["2", "3"]}),
    ]:
        response = client.get(path + "/comments", query)
        assert response.status_code == 400 and body(response)["code"] == "INVALID_CURSOR"


def test_comment_raw_json_boundaries_and_duplicate_keys(actors: list[tuple[Client, str]]) -> None:
    import json

    from social.models import Comment

    c, owner = actors[0]
    parent = "/api/posts/" + body(send(c, owner, "POST", "/api/posts", payload()))["id"]

    def raw(value: bytes, content_type: str = "application/json") -> Any:
        return c.post(
            parent + "/comments",
            value,
            content_type=content_type,
            HTTP_X_CSRFTOKEN=token(c),
            HTTP_X_SOCIAL_OWNER=owner,
        )

    value = json.dumps({"id": cid(300), "body": "境界"}).encode()
    assert raw(value + b" " * (16384 - len(value))).status_code == 201
    assert raw(b" " * 16385).status_code == 413
    assert raw(b"{}", "text/plain").status_code == 415
    assert (
        raw(b'{"body":"a","body":"b","id":"00000000-0000-4000-8000-00000000012d"}').status_code
        == 400
    )
    assert (
        raw(json.dumps({"id": cid(301), "body": "ok", "extra": True}).encode()).status_code == 400
    )
    assert (
        raw(
            json.dumps({"id": cid(301), "body": {"a": {"b": {"c": {"d": "no"}}}}}).encode()
        ).status_code
        == 400
    )
    assert Comment.objects.count() == 1


def test_comment_rollback_does_not_leave_identity(
    actors: list[tuple[Client, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from django.db import IntegrityError

    from social.models import Comment, CommentIdentity

    c, owner = actors[0]
    parent = "/api/posts/" + body(send(c, owner, "POST", "/api/posts", payload()))["id"]

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise IntegrityError("synthetic non-primary failure")

    monkeypatch.setattr(Comment, "save", broken)
    response = social(
        c, owner, "POST", parent + "/comments", {"id": cid(302), "body": "一部保存しない"}
    )
    assert response.status_code == 500 and body(response)["code"] == "INTERNAL_ERROR"
    assert not Comment.objects.exists() and not CommentIdentity.objects.exists()


def test_comment_commit_ack_loss_has_one_identity_and_readable_state(
    actors: list[tuple[Client, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from typing import cast

    from django.db import OperationalError, connection

    from social.models import Comment, CommentIdentity
    from tests.test_auth import PASSWORD

    c, owner = actors[0]
    parent = "/api/posts/" + body(send(c, owner, "POST", "/api/posts", payload()))["id"]
    identity = cid(303)
    original = cast(Any, connection)._commit
    injected = False

    def lost_ack() -> None:
        nonlocal injected
        exists = Comment.objects.filter(pk=UUID(identity)).exists()
        original()
        if exists and not injected:
            injected = True
            raise OperationalError("synthetic acknowledged commit response loss")

    with monkeypatch.context() as patch:
        patch.setattr(connection, "_commit", lost_ack)
        response = social(
            c, owner, "POST", parent + "/comments", {"id": identity, "body": "保存済み"}
        )
    assert injected and response.status_code == 503
    assert response.cookies["sessionid"].value == ""
    assert Comment.objects.count() == 1 and CommentIdentity.objects.count() == 1
    login = c.post(
        "/api/auth/login",
        {"email": "social_a@example.test", "password": PASSWORD},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token(c),
    )
    assert login.status_code == 200
    recovered = c.get("/api/comments/" + identity)
    assert recovered.status_code == 200 and body(recovered)["comment"]["body"] == "保存済み"
    duplicate = social(c, owner, "POST", parent + "/comments", {"id": identity, "body": "保存済み"})
    assert duplicate.status_code == 409 and body(duplicate)["code"] == "COMMENT_ID_CONFLICT"
    assert Comment.objects.count() == 1 and CommentIdentity.objects.count() == 1


def test_two_sessions_of_same_author_keep_last_committed_edit(
    actors: list[tuple[Client, str]],
) -> None:
    from tests.test_auth import PASSWORD

    a, aid = actors[0]
    b, bid = actors[1]
    other_tab = api_client()
    assert (
        other_tab.post(
            "/api/auth/login",
            {"email": "social_b@example.test", "password": PASSWORD},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token(other_tab),
        ).status_code
        == 200
    )
    parent = "/api/posts/" + body(send(a, aid, "POST", "/api/posts", payload()))["id"]
    created = body(
        social(b, bid, "POST", parent + "/comments", {"id": cid(401), "body": "original"})
    )["comment"]
    target = "/api/comments/" + cid(401)
    assert social(b, bid, "PUT", target, {"body": "first committed"}).status_code == 200
    assert social(other_tab, bid, "PUT", target, {"body": "last committed"}).status_code == 200
    for client in (b, other_tab):
        current = body(client.get(target))
        assert current["comment"]["body"] == "last committed"
        assert current["comment"]["created_at"] == created["created_at"]
        assert current["comment_count"] == 1


@pytest.mark.parametrize("encoding", ["multipart", "urlencoded"])
@pytest.mark.parametrize(
    "endpoint,oversized,wanted,code",
    [
        ("comments", False, 415, "UNSUPPORTED_MEDIA_TYPE"),
        ("comments", True, 413, "PAYLOAD_TOO_LARGE"),
        ("like", False, 400, "INVALID_REQUEST"),
    ],
)
def test_social_rejects_csrf_preparsed_form_bodies(
    actors: list[tuple[Client, str]],
    encoding: str,
    endpoint: str,
    oversized: bool,
    wanted: int,
    code: str,
) -> None:
    from django.test.client import BOUNDARY, MULTIPART_CONTENT, encode_multipart

    from social.models import Comment, CommentIdentity, Like

    c, owner = actors[0]
    parent = "/api/posts/" + body(send(c, owner, "POST", "/api/posts", payload()))["id"]
    csrf = token(c)
    fields = {"body": "x" * (16385 if oversized else 1)}
    if encoding == "multipart":
        raw = encode_multipart(BOUNDARY, fields)
        content_type = MULTIPART_CONTENT
    else:
        raw = ("body=" + fields["body"]).encode()
        content_type = "application/x-www-form-urlencoded"
    c.raise_request_exception = False
    response = c.generic(
        "POST",
        parent + "/" + endpoint,
        raw,
        content_type=content_type,
        HTTP_X_CSRFTOKEN=csrf,
        HTTP_X_SOCIAL_OWNER=owner,
    )
    assert response.status_code == wanted
    assert body(response)["code"] == code
    assert Comment.objects.count() == CommentIdentity.objects.count() == Like.objects.count() == 0


@pytest.mark.parametrize("endpoint", ["comments", "like"])
@pytest.mark.parametrize(
    "phase,wanted,code",
    [
        ("csrf", 403, "CSRF_FAILED"),
        ("method", 405, "METHOD_NOT_ALLOWED"),
        ("auth", 401, "AUTH_REQUIRED"),
        ("owner_missing", 400, "INVALID_REQUEST"),
        ("owner_changed", 409, "SOCIAL_OWNER_CHANGED"),
        ("missing_post", 404, "NOT_FOUND"),
    ],
)
def test_preparsed_form_size_never_overtakes_policy_checks(
    actors: list[tuple[Client, str]],
    endpoint: str,
    phase: str,
    wanted: int,
    code: str,
) -> None:
    from django.test.client import BOUNDARY, MULTIPART_CONTENT, encode_multipart

    c, owner = actors[0]
    parent = "/api/posts/" + body(send(c, owner, "POST", "/api/posts", payload()))["id"]
    headers: dict[str, Any] = {"HTTP_X_CSRFTOKEN": token(c), "HTTP_X_SOCIAL_OWNER": owner}
    method = "POST"
    if phase == "csrf":
        headers.pop("HTTP_X_CSRFTOKEN")
    elif phase == "method":
        method = "PATCH"
    elif phase == "auth":
        c = api_client()
        headers["HTTP_X_CSRFTOKEN"] = token(c)
    elif phase == "owner_missing":
        headers.pop("HTTP_X_SOCIAL_OWNER")
    elif phase == "owner_changed":
        headers["HTTP_X_SOCIAL_OWNER"] = actors[1][1]
    elif phase == "missing_post":
        parent = "/api/posts/" + cid(999)
    raw = encode_multipart(BOUNDARY, {"body": "x" * 16385})
    response = c.generic(
        method, parent + "/" + endpoint, raw, content_type=MULTIPART_CONTENT, **headers
    )
    assert response.status_code == wanted
    assert body(response)["code"] == code
