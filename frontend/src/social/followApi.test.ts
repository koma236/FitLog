import { afterEach, expect, it, vi } from 'vitest'
import { searchUsers, writeFollow } from './followApi'
import { validProfile } from '../profile/api'

const actor = '11111111-1111-4111-8111-111111111111'
const id = '22222222-2222-4222-8222-222222222222'
const user = { id, username: 'bob', display_name: 'Bob', avatar: null, is_owner: false, is_following: false, follower_count: 0, following_count: 7 }
const page = { viewer_id: actor, items: [user], next_cursor: null }
const signal = () => new AbortController().signal
const respond = (v: unknown, status = 200) => { vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(JSON.stringify(v), { status })))) }
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

it.each([
  { ...page, email: 'private' }, { ...page, viewer_id: 'other' },
  ...[-1, 0.5, Number.MAX_SAFE_INTEGER + 1, '1', null].map(n => ({ ...page, items: [{ ...user, follower_count: n }] })),
  ...[{ email: 'private' }, { is_owner: true }, { is_following: 'false' }, { id: 'invalid' }, { health: {} }].map(extra => ({ ...page, items: [{ ...user, ...extra }] })),
  { ...page, items: [user, user] }, { ...page, next_cursor: '' }, { ...page, next_cursor: 'é' },
])('rejects private, malformed and owner-mismatched search results %j', async value => {
  respond(value)
  await expect(searchUsers('a', actor, signal())).rejects.toMatchObject({ code: value.viewer_id === 'other' ? 'SOCIAL_OWNER_CHANGED' : 'INVALID_RESPONSE' })
})

it('sends untrimmed Unicode and literal wildcard input in URLSearchParams', async () => {
  respond(page); await searchUsers(' \ufeff%_\\🙂 ', actor, signal(), 'opaque')
  const call = vi.mocked(fetch).mock.calls[0]
  if (!call) throw new Error('Search did not send its request')
  const url = new URL(typeof call[0] === 'string' ? call[0] : call[0] instanceof URL ? call[0].href : call[0].url, 'http://localhost')
  expect(url.searchParams.get('q')).toBe(' \ufeff%_\\🙂 ')
  expect(url.searchParams.get('cursor')).toBe('opaque')
  expect(call[1]).toMatchObject({ credentials: 'same-origin', cache: 'no-store' })
})

it.each([
  { viewer_id: actor, user_id: id, is_following: false, follower_count: 1, following_count: 1 },
  { viewer_id: actor, user_id: actor, is_following: true, follower_count: 1, following_count: 1 },
  { viewer_id: 'other', user_id: id, is_following: true, follower_count: 1, following_count: 1 },
  { viewer_id: actor, user_id: id, is_following: true, follower_count: -1, following_count: 1 },
])('rejects a write response that cannot confirm its intended relationship %j', async value => {
  respond(value)
  await expect(writeFollow(id, true, actor, 'csrf', signal())).rejects.toMatchObject({ code: value.viewer_id === 'other' ? 'SOCIAL_OWNER_CHANGED' : 'INVALID_RESPONSE' })
})

it('requires new relation fields on profiles without permitting private extras', () => {
  const profile = { viewer_id: actor, ...user, bio: '', health: {}, energy: {} }
  expect(validProfile(profile, actor)).toBe(true)
  expect(validProfile({ ...profile, is_following: undefined }, actor)).toBe(false)
  expect(validProfile({ ...profile, email: 'private' }, actor)).toBe(false)
})
