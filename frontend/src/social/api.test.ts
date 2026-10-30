import { afterEach, expect, it, vi } from 'vitest'
import { validPost } from '../workouts/api'
const actor = '11111111-1111-4111-8111-111111111111'
const post = { image: null, viewer_id: actor, id: '33333333-3333-4333-8333-333333333333', author: { id: actor, username: 'river', display_name: 'River', avatar: null }, is_owner: true, performed_on: '2026-10-30', note: '', created_at: '2026-10-30T00:00:00Z', updated_at: '2026-10-30T00:00:00Z', exercises: [{ name: 'Squat', sets: [{ weight_kg: '60.00', reps: 10 }] }], energy: null, energy_input: { minutes: null, kind: null }, visibility: { minutes: 'private', kind: 'private' } }
afterEach(() => vi.unstubAllGlobals())
it('requires safe counts and a boolean like state on every Post', () => {
  expect(validPost({ ...post, comment_count: 0, like_count: 2, is_liked: true }, actor)).toBe(true)
  expect(validPost(post, actor)).toBe(false)
  for (const value of [-1, 1.5, Number.MAX_SAFE_INTEGER + 1]) expect(validPost({ ...post, comment_count: value, like_count: 0, is_liked: false }, actor)).toBe(false)
})

import { getComment, listComments, normalizeBody, writeComment, writeLike } from './api'
const postId = '33333333-3333-4333-8333-333333333333'
const id = '44444444-4444-4444-8444-444444444444'
const comment = { id, post_id: postId, body: 'hello', created_at: '2026-10-30T00:00:00Z', updated_at: '2026-10-30T00:00:00Z', author: { id: actor, username: 'river', display_name: 'River', avatar: null }, is_owner: true }
const result = { viewer_id: actor, post_id: postId, comment_count: 1, comment }
const signal = () => new AbortController().signal
const response = (value: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(value), { status })
it('checks viewer, parent, target, ownership and private fields on social responses', async () => {
  for (const value of [{ ...result, viewer_id: 'other' }, { ...result, post_id: 'other' }, { ...result, comment: { ...comment, id: 'other' } }, { ...result, comment: { ...comment, post_id: 'other' } }, { ...result, comment: { ...comment, is_owner: false } }, { ...result, comment: { ...comment, email: 'private' } }, { ...result, comment_count: -1 }]) {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(response(value))))
    await expect(getComment(id, postId, actor, signal())).rejects.toMatchObject({ code: value.viewer_id === 'other' ? 'SOCIAL_OWNER_CHANGED' : 'INVALID_RESPONSE' })
  }
})
it('sends canonical comment payloads and zero-byte like bodies with actor and csrf headers', async () => {
  const calls: { url: string; init: RequestInit }[] = []
  vi.stubGlobal('fetch', vi.fn((url: string, init: RequestInit) => {
    calls.push({ url, init }); return Promise.resolve(response(url.endsWith('/like') ? { viewer_id: actor, post_id: postId, like_count: init.method === 'POST' ? 1 : 0, is_liked: init.method === 'POST' } : result, init.method === 'POST' && url.endsWith('/comments') ? 201 : 200))
  }))
  await writeComment(postId, id, 'create', 'hello', actor, 'csrf', signal()); await writeComment(postId, id, 'update', 'hello', actor, 'csrf', signal())
  await writeLike(postId, true, actor, 'csrf', signal()); await writeLike(postId, false, actor, 'csrf', signal())
  expect(calls.map(call => [call.url, call.init.method, call.init.body])).toEqual([['/api/posts/' + postId + '/comments', 'POST', JSON.stringify({ id, body: 'hello' })], ['/api/comments/' + id, 'PUT', JSON.stringify({ body: 'hello' })], ['/api/posts/' + postId + '/like', 'POST', undefined], ['/api/posts/' + postId + '/like', 'DELETE', undefined]])
  for (const { init } of calls) { expect(new Headers(init.headers).get('X-Social-Owner')).toBe(actor); expect(new Headers(init.headers).get('X-CSRFToken')).toBe('csrf'); expect(init.credentials).toBe('same-origin'); expect(init.cache).toBe('no-store') }
})
it('requires DELETE204, POST201, safe counts and parent-bound list items', async () => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(response(null, 204))))
  await expect(writeComment(postId, id, 'delete', '', actor, 'csrf', signal())).resolves.toBeNull()
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(response(result))))
  await expect(writeComment(postId, id, 'create', 'hello', actor, 'csrf', signal())).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(response({ viewer_id: actor, post_id: postId, comment_count: 1, items: [{ ...comment, post_id: 'other' }], next_cursor: null }))))
  await expect(listComments(postId, actor, signal())).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
})
it.each([['\u0085 hello \u0085', 'hello'], ['\ufeffhello\ufeff', '\ufeffhello\ufeff'], [' a\r\nb ', 'a\nb'], [' e\u0301🙂 ', 'e\u0301🙂']])('normalizes Python whitespace and preserves code points: %j', (input, expected) => { expect(normalizeBody(input)).toBe(expected) })
it.each(['\rhello', 'hello\r', '\u0000hello', '\u001chello', '\ud800'])('rejects forbidden controls before stripping %j', input => { expect(() => normalizeBody(input)).toThrow() })
it('aborts social writes on timeout and follows the caller abort signal', async () => {
  vi.useFakeTimers()
  try {
    let signal: AbortSignal | undefined | null
    vi.stubGlobal('fetch', vi.fn((_url: string, init: RequestInit) => new Promise<Response>((_resolve, reject) => { signal = init.signal; signal?.addEventListener('abort', () => { reject(new DOMException('abort', 'AbortError')) }, { once: true }) })))
    const controller = new AbortController(); const pending = writeLike(postId, true, actor, 'csrf', controller.signal).catch((cause: unknown) => cause)
    await vi.advanceTimersByTimeAsync(9999); expect(signal?.aborted).toBe(false)
    await vi.advanceTimersByTimeAsync(1); expect(signal?.aborted).toBe(true); await expect(pending).resolves.toMatchObject({ code: 'NETWORK_ERROR' })
    const other = new AbortController(); const stopped = getComment(id, postId, actor, other.signal).catch((cause: unknown) => cause); other.abort(); await expect(stopped).resolves.toMatchObject({ code: 'ABORTED' })
  } finally { vi.useRealTimers() }
})
