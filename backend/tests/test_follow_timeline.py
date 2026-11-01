"""FL07-AC1..7: fixed actors/sets and real PostgreSQL, independent of DTO helpers."""

import importlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import Client
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from tests.test_auth import api_client, body, signup, token
from tests.test_social_api import social
from workouts.models import Post, PostIdentity

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def members() -> list[tuple[Client, User]]:
    result = []
    for i, name in enumerate(('alice', 'ali_name', 'charlie')):
        client = api_client()
        value = body(signup(client, token(client), name, name + '@example.test'))
        user = User.objects.get(pk=value['id'])
        user.display_name = ('Alice', '別名_%\\', '日本語')[i]
        user.date_joined = datetime(2026, 1, 1, tzinfo=UTC)
        user.save()
        result.append((client, user))
    return result


def test_follow_idempotence_counts_profile_and_private_search(members: Any) -> None:
    a, actor = members[0]
    _, target = members[1]
    path = f'/api/users/{target.pk}/follow'
    expected = {'viewer_id': str(actor.pk), 'user_id': str(target.pk),
                'is_following': True, 'follower_count': 1, 'following_count': 1}
    for _ in range(2):
        response = social(a, str(actor.pk), 'POST', path)
        assert response.status_code == 200
        assert body(response) == expected
    own = body(a.get('/api/users/me'))
    other = body(a.get('/api/users/ali_name'))
    assert (own['following_count'], own['follower_count'], own['is_following']) == (1, 0, False)
    assert (other['following_count'], other['follower_count'], other['is_following']) == (0, 1, True)
    results = body(a.get('/api/users/search'))
    assert results['viewer_id'] == str(actor.pk)
    assert len(results['items']) == 3
    for item in results['items']:
        assert set(item) == {'id', 'username', 'display_name', 'avatar', 'is_owner',
                             'is_following', 'follower_count', 'following_count'}
    for _ in range(2):
        deleted = body(social(a, str(actor.pk), 'DELETE', path))
        assert (deleted['is_following'], deleted['follower_count'], deleted['following_count']) == (False, 0, 0)


@pytest.mark.parametrize('method', ['POST', 'DELETE'])
def test_follow_boundaries_and_precedence(members: Any, method: str) -> None:
    a, actor = members[0]
    _, target = members[1]
    owner = str(actor.pk)
    path = f'/api/users/{target.pk}/follow'
    assert social(a, owner, method, '/api/users/not-uuid/follow').status_code == 404
    assert social(a, owner, method, f'/api/users/{actor.pk}/follow', {'x': 1}).json()['code'] == 'SELF_FOLLOW'
    assert social(a, str(target.pk), method, f'/api/users/{actor.pk}/follow').status_code == 409
    assert social(a, owner, method, path + '?x=1').json()['code'] == 'INVALID_REQUEST'
    for data in [b' ', b'x' * 20480]:
        response = a.generic(method, path, data=data, content_type='application/json',
                             HTTP_X_CSRFTOKEN=token(a), HTTP_X_SOCIAL_OWNER=owner)
        assert (response.status_code, response.json()['code']) == (400, 'INVALID_REQUEST')
    assert a.generic(method, path, HTTP_X_CSRFTOKEN=token(a)).status_code == 400
    assert a.generic(method, path, HTTP_X_SOCIAL_OWNER=owner).status_code == 403
    anonymous = api_client()
    valid_csrf = token(anonymous)
    denied = anonymous.generic(method, path, HTTP_X_CSRFTOKEN=valid_csrf)
    assert (denied.status_code, denied.json()['code']) == (401, 'AUTH_REQUIRED')
    denied = anonymous.generic(method, path)
    assert (denied.status_code, denied.json()['code']) == (403, 'CSRF_FAILED')
    target.is_active = False
    target.save()
    assert social(a, owner, method, path).status_code == 404


@pytest.mark.parametrize(('q', 'names'), [('', {'alice', 'ali_name', 'charlie'}),
    (' ALI ', {'alice', 'ali_name'}), ('\u3000別名\u3000', {'ali_name'}),
    ('日本', {'charlie'}), ('%', {'ali_name'}), ('_', {'ali_name'}),
    ('\\', {'ali_name'}), ('\ufeff', set())])
def test_search_literal_sets(members: Any, q: str, names: set[str]) -> None:
    response = members[0][0].get('/api/users/search', {'q': q})
    assert response.status_code == 200
    assert {item['username'] for item in body(response)['items']} == names


@pytest.mark.parametrize('suffix,code', [
    ('?q=' + 'a' * 51, 'VALIDATION_ERROR'), ('?q=%00', 'VALIDATION_ERROR'),
    ('?q=%7F', 'VALIDATION_ERROR'), ('?q=a&q=b', 'INVALID_CURSOR'),
    ('?q=%00&unknown=x', 'INVALID_CURSOR'), ('?limit=01', 'INVALID_CURSOR'),
    ('?limit=050', 'INVALID_CURSOR'), ('?limit=0', 'INVALID_CURSOR'),
    ('?limit=51', 'INVALID_CURSOR'), ('?limit=%EF%BC%91', 'INVALID_CURSOR'),
    ('?cursor=', 'INVALID_CURSOR'), ('?cursor=%C3%A9', 'INVALID_CURSOR'),
    ('?cursor=' + 'a' * 2049, 'INVALID_CURSOR')])
def test_search_input_errors(members: Any, suffix: str, code: str) -> None:
    response = members[0][0].get('/api/users/search' + suffix)
    assert (response.status_code, body(response)['code']) == (400, code)


def test_keysets_scope_viewer_query_and_active_members(members: Any) -> None:
    a, actor = members[0]
    b, target = members[1]
    social(a, str(actor.pk), 'POST', f'/api/users/{target.pk}/follow')
    at = datetime(2026, 1, 1, tzinfo=UTC)
    for i, (_, user) in enumerate(members):
        key = UUID(f'00000000-0000-4000-8000-{i+1:012x}')
        identity = PostIdentity.objects.create(id=key, author=user)
        Post.objects.create(identity=identity, user=user, performed_on=at.date(),
                            created_at=at, updated_at=at, note=user.username)
    for scope, ids in [('following', [2, 1]), ('all', [3, 2, 1])]:
        path = f'/api/timeline/{scope}'
        seen = []
        cursor = None
        while True:
            response = a.get(path, {'limit': '1', **({'cursor': cursor} if cursor else {})})
            assert response.status_code == 200
            page = body(response)
            seen += [UUID(item['id']).int for item in page['items']]
            cursor = page['next_cursor']
            if cursor is None:
                break
            assert b.get(path, {'cursor': cursor}).status_code == 400
            other = 'all' if scope == 'following' else 'following'
            assert a.get(f'/api/timeline/{other}', {'cursor': cursor}).status_code == 400
            assert a.get('/api/users/search', {'cursor': cursor}).status_code == 400
        assert seen == [UUID(f'00000000-0000-4000-8000-{i:012x}').int for i in ids]
    cursor = body(a.get('/api/users/search', {'q': 'ali', 'limit': 1}))['next_cursor']
    assert cursor
    assert a.get('/api/users/search', {'q': 'a', 'cursor': cursor}).status_code == 400
    assert b.get('/api/users/search', {'q': 'ali', 'cursor': cursor}).status_code == 400
    assert a.get('/api/users/search', {'q': 'ali', 'cursor': cursor + 'x'}).status_code == 400
    target.is_active = False
    target.save()
    assert body(a.get('/api/users/me'))['following_count'] == 0
    assert len(body(a.get('/api/timeline/following'))['items']) == 1


def test_database_constraints_and_concurrent_opposite_follows(members: Any) -> None:
    models = importlib.import_module('social.models')
    assert hasattr(models, 'Follow'), 'Follow DB constraints are missing'
    follow = models.Follow
    actor, target = members[0][1], members[1][1]
    with pytest.raises(IntegrityError), transaction.atomic():
        follow.objects.create(follower=actor, followee=actor)
    follow.objects.create(follower=actor, followee=target)
    with pytest.raises(IntegrityError), transaction.atomic():
        follow.objects.create(follower=actor, followee=target)
    follow.objects.all().delete()
    service = importlib.import_module('social.follow_service')

    def write(pair: tuple[User, User]) -> None:
        close_old_connections()
        try:
            service.write_follow(pair[0], pair[1].pk, enabled=True)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(write, [(actor, target), (target, actor)] * 2))
    assert follow.objects.count() == 2


def test_search_query_count_does_not_grow_per_member(members: Any) -> None:
    client = members[0][0]
    with CaptureQueriesContext(connection) as first:
        assert client.get('/api/users/search', {'limit': 1}).status_code == 200
    for i in range(20):
        User.objects.create(username=f'extra_{i}', email=f'extra{i}@example.test', display_name='Extra')
    with CaptureQueriesContext(connection) as many:
        assert client.get('/api/users/search', {'limit': 20}).status_code == 200
    assert len(many) <= len(first) + 1


def test_search_pages_and_http_guard_precedence(members: Any) -> None:
    a, actor = members[0]
    expected = [str(user.pk) for _, user in sorted(members, key=lambda pair: pair[1].pk, reverse=True)]
    seen = []
    cursor = None
    for _ in range(3):
        page = body(a.get('/api/users/search', {'limit': '1', **({'cursor': cursor} if cursor else {})}))
        seen += [item['id'] for item in page['items']]
        cursor = page['next_cursor']
    assert seen == expected and cursor is None
    assert a.get('/api/users/search', {'q': ' ' + 'a' * 50 + ' ', 'limit': '50'}).status_code == 200
    assert a.get('/api/users/search?q=%00&limit=0').json()['code'] == 'VALIDATION_ERROR'
    for path in ['/api/users/search', '/api/timeline/following', '/api/timeline/all']:
        anonymous = api_client()
        response = anonymous.get(path + '?unknown=1')
        assert (response.status_code, response.json()['code']) == (401, 'AUTH_REQUIRED')
        assert response['WWW-Authenticate'] == 'Session'
        assert anonymous.head(path + '?unknown=1').status_code == 405
        response = a.options(path + '?unknown=1')
        assert response.status_code == 405 and response['Allow'] == 'GET'
        assert a.get(path + '?limit=1&limit=2').status_code == 400
        assert a.get(path + '?unknown=1&cursor=bad').json()['code'] == 'INVALID_CURSOR'
        assert a.get(path)['Cache-Control'] == 'no-store'
        assert 'Cookie' in a.get(path)['Vary']
    response = social(a, str(actor.pk), 'DELETE', f'/api/users/{actor.pk}/follow')
    assert response.json()['message'] == '自分自身はフォローできません。'


def test_expired_and_signed_malformed_cursors_are_rejected(members: Any) -> None:
    from time import time
    from unittest.mock import patch

    from django.core import signing

    a, actor = members[0]
    cursor = body(a.get('/api/users/search', {'limit': '1'}))['next_cursor']
    with patch('django.core.signing.time.time', return_value=time() + 86401):
        assert a.get('/api/users/search', {'cursor': cursor}).status_code == 400
    base = {'v': 1, 'viewer': str(actor.pk), 'scope': 'search', 'q': '', 'at': '2026-01-01T00:00:00+00:00', 'id': str(actor.pk)}
    variants: list[dict[str, object]] = [{'v': True}, {'v': 2}, {'at': '2026-01-01T00:00:00'}, {'at': None}, {'id': 'bad'}, {'extra': 1}, {'q': 'other'}, {'scope': 'all'}]
    for extra in variants:
        value = signing.dumps({**base, **extra}, salt='social.members.search')
        assert a.get('/api/users/search', {'cursor': value}).status_code == 400


def test_follow_transaction_rechecks_active_and_cascades(members: Any) -> None:
    service = importlib.import_module('social.follow_service')
    from social.models import Follow
    from social.service import SocialError

    actor, target = members[0][1], members[1][1]
    service.write_follow(actor, target.pk, enabled=True)
    actor.is_active = False
    actor.save()
    with pytest.raises(SocialError) as failure:
        service.write_follow(actor, target.pk, enabled=False)
    assert failure.value.status == 401
    target.delete()
    assert Follow.objects.count() == 0


def test_openapi_search_follow_and_profile_responses(members: Any) -> None:
    import json
    from pathlib import Path

    from jsonschema import Draft7Validator

    path = Path('/app/contracts/openapi.json')
    if not path.exists():
        path = Path(__file__).resolve().parents[2] / 'docs/api/openapi.json'
    contract = json.loads(path.read_text())

    def nullable(value: Any) -> Any:
        if isinstance(value, list):
            return [nullable(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {key: nullable(item) for key, item in value.items()}
        if value.get('nullable') and isinstance(value.get('type'), str):
            result['type'] = [value['type'], 'null']
        return result

    components = nullable(contract['components'])
    a, actor = members[0]
    target = members[1][1]
    values = [('UserPage', body(a.get('/api/users/search'))),
              ('FollowResult', body(social(a, str(actor.pk), 'POST', f'/api/users/{target.pk}/follow'))),
              ('OwnerProfile', body(a.get('/api/users/me'))),
              ('PublicProfile', body(a.get('/api/users/ali_name')))]
    for name, value in values:
        Draft7Validator({'$ref': '#/components/schemas/' + name, 'components': components}).validate(value)


@pytest.mark.parametrize('failure_at', ['listing', 'auth', 'session', 'unexpected'])
def test_timeline_failure_boundary_keeps_json_cache_and_session_policy(members: Any, failure_at: str) -> None:
    from unittest.mock import patch

    from django.contrib.sessions.backends.db import SessionStore
    from django.db import DatabaseError
    from django.test import override_settings

    client = members[0][0]
    if failure_at == 'auth':
        fault = patch.object(SessionStore, 'load', side_effect=DatabaseError('private-session-marker'))
    elif failure_at == 'session':
        fault = patch.object(SessionStore, 'save', side_effect=DatabaseError('private-session-marker'))
    else:
        fault = patch('workouts.timeline.listing', side_effect=RuntimeError('private-marker') if failure_at == 'unexpected' else DatabaseError('private-db-marker'))
    with override_settings(SESSION_SAVE_EVERY_REQUEST=failure_at == 'session'), fault:
        response = client.get('/api/timeline/following')
    expected = 500 if failure_at == 'unexpected' else 503
    assert response.status_code == expected
    assert body(response)['code'] == ('INTERNAL_ERROR' if expected == 500 else 'SERVICE_UNAVAILABLE')
    assert response['Cache-Control'] == 'no-store'
    assert 'Cookie' in response['Vary']
    assert 'private' not in response.content.decode()
    if expected == 503:
        assert response.cookies['sessionid']['max-age'] == 0


def test_timeline_queries_do_not_grow_per_post_and_keep_active_social_fields(members: Any) -> None:
    from decimal import Decimal

    from social.models import Follow, Like
    from workouts.models import WorkoutExercise, WorkoutSet

    client, actor = members[0]
    Follow.objects.create(follower=actor, followee=members[1][1])
    at = datetime(2026, 1, 1, tzinfo=UTC)

    def create(number: int) -> None:
        owner = members[number % 3][1]
        key = UUID(f'00000000-0000-4000-8000-{number+1000:012x}')
        identity = PostIdentity.objects.create(id=key, author=owner)
        post = Post.objects.create(identity=identity, user=owner, performed_on=at.date(), created_at=at, updated_at=at)
        exercise = WorkoutExercise.objects.create(post=post, name='Squat', position=0)
        WorkoutSet.objects.create(exercise=exercise, position=0, weight_kg=Decimal('60.00'), reps=10)
        Like.objects.create(post=post, user=actor)

    create(0)
    with CaptureQueriesContext(connection) as first:
        assert client.get('/api/timeline/all', {'limit': 1}).status_code == 200
    for i in range(1, 20):
        create(i)
    with CaptureQueriesContext(connection) as many:
        page = body(client.get('/api/timeline/all', {'limit': 20}))
    assert len(page['items']) == 20
    assert all(item['like_count'] == 1 and item['is_liked'] and item['comment_count'] == 0 for item in page['items'])
    assert len(many) <= len(first) + 1
    with CaptureQueriesContext(connection) as following:
        page = body(client.get('/api/timeline/following', {'limit': 20}))
    # A/B each author 7 of the twenty fixed records, C authors 6.
    assert len(page['items']) == 14
    assert len(following) <= len(first) + 1


@pytest.fixture
def fixed_timeline_posts(members: Any) -> list[Post]:
    from social.models import Follow

    Follow.objects.create(follower=members[0][1], followee=members[1][1])
    posts = []
    for i, (_, owner) in enumerate(members):
        at = datetime(2026, 1, i + 1, tzinfo=UTC)
        identity = PostIdentity.objects.create(id=UUID(f'00000000-0000-4000-8000-{i+2000:012x}'), author=owner)
        posts.append(Post.objects.create(identity=identity, user=owner, performed_on=at.date(), created_at=at, updated_at=at, note='Original'))
    return posts


def timeline_ids(client: Client, scope: str, cursor: str | None = None) -> list[str]:
    ids: list[str] = []
    for _ in range(10):
        params: dict[str, str] = {'limit': '1'}
        if cursor is not None:
            params['cursor'] = cursor
        response = client.get('/api/timeline/' + scope, params)
        assert response.status_code == 200
        page = body(response)
        ids += [item['id'] for item in page['items']]
        cursor = page['next_cursor']
        if cursor is None:
            return ids
    pytest.fail('Timeline did not reach its null terminator')


def test_edit_and_performed_date_do_not_reorder_either_timeline(members: Any, fixed_timeline_posts: list[Post]) -> None:
    from tests.test_workouts import payload, send

    client, actor = members[0]
    older = fixed_timeline_posts[0]
    expected = {'following': [str(fixed_timeline_posts[1].pk), str(older.pk)],
                'all': [str(fixed_timeline_posts[2].pk), str(fixed_timeline_posts[1].pk), str(older.pk)]}
    for scope in expected:
        assert timeline_ids(client, scope) == expected[scope]
    update = {key: value for key, value in payload().items() if key != 'id'}
    update.update(performed_on='2026-01-20', note='Edited oldest post', recalculate=False)
    response = send(client, str(actor.pk), 'PUT', f'/api/posts/{older.pk}', update)
    assert response.status_code == 200
    older.refresh_from_db()
    assert older.created_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert older.updated_at > fixed_timeline_posts[2].created_at
    assert older.performed_on.isoformat() == '2026-01-20'
    for scope in expected:
        assert timeline_ids(client, scope) == expected[scope]
        assert [item['id'] for item in body(client.get('/api/timeline/' + scope))['items']] == expected[scope]


def test_deleted_post_disappears_from_both_scopes_and_preissued_cursors(members: Any, fixed_timeline_posts: list[Post]) -> None:
    from tests.test_workouts import send

    client = members[0][0]
    cursors = {scope: body(client.get('/api/timeline/' + scope, {'limit': 1}))['next_cursor'] for scope in ['following', 'all']}
    b, owner = members[1]
    deleted = fixed_timeline_posts[1]
    assert send(b, str(owner.pk), 'DELETE', f'/api/posts/{deleted.pk}').status_code == 204
    for scope in ['following', 'all']:
        assert cursors[scope]
        # Both old cursors now continue directly to A, even though following's anchor B was deleted.
        assert timeline_ids(client, scope, cursors[scope]) == [str(fixed_timeline_posts[0].pk)]
        expected = [str(fixed_timeline_posts[0].pk)] if scope == 'following' else [str(fixed_timeline_posts[2].pk), str(fixed_timeline_posts[0].pk)]
        assert timeline_ids(client, scope) == expected
