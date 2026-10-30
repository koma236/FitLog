import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import CommentsPanel from './CommentsPanel'
import LikeButton from './LikeButton'
import type { Workout } from '../workouts/types'
const actor = { id: '11111111-1111-4111-8111-111111111111', username: 'river', display_name: 'River', email: 'river@example.test' }
const postId = '33333333-3333-4333-8333-333333333333'
const commentId = '44444444-4444-4444-8444-444444444444'
const comment = { id: commentId, post_id: postId, body: 'hello', created_at: '2026-10-30T00:00:00Z', updated_at: '2026-10-30T00:00:00Z', author: { id: actor.id, username: 'river', display_name: 'River', avatar: null }, is_owner: true }
const page = (items: typeof comment[] = [], cursor: string | null = null) => ({ viewer_id: actor.id, post_id: postId, comment_count: items.length, items, next_cursor: cursor })
const result = (body = 'hello', id = commentId) => ({ viewer_id: actor.id, post_id: postId, comment_count: 1, comment: { ...comment, body, id } })
const reply = (status: number, value: unknown = null) => new Response(status === 204 ? null : JSON.stringify(value), { status })
beforeEach(() => { Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function (this: HTMLDialogElement) { this.open = true } }); Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function (this: HTMLDialogElement) { this.open = false } }) })
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks() })
function setup(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/api/auth/me') return reply(200, actor)
    if (url === '/api/auth/csrf') return reply(200, { csrf_token: 'token' })
    return handler(url, init)
  }))
  const callbacks = { onIdentity: vi.fn(), onBusy: vi.fn(), onUncertain: vi.fn(), onCount: vi.fn(), onMissing: vi.fn() }
  render(<CommentsPanel account={actor} postId={postId} {...callbacks} />)
  return callbacks
}
async function submit(body = 'hello') {
  await screen.findByRole('button', { name: 'コメントする' })
  fireEvent.change(screen.getByLabelText('コメント本文'), { target: { value: body } })
  fireEvent.click(screen.getByRole('button', { name: 'コメントする' }))
}
it('renders escaped comments and hides write controls for a different author', async () => {
  setup(() => reply(200, page([{ ...comment, body: '<script>alert(1)</script>', is_owner: false, author: { ...comment.author, id: 'other' } }])))
  expect(await screen.findByText('<script>alert(1)</script>')).toBeVisible()
  expect(document.querySelector('script')).toBeNull()
  expect(screen.queryByRole('button', { name: '編集' })).toBeNull()
  expect(screen.queryByRole('button', { name: '削除' })).toBeNull()
})
it('fixes the UUID and immutable body through one manual retry then forbids further POSTs', async () => {
  const writes: { id: string; body: string }[] = []
  const callbacks = setup((url, init) => {
    if (init?.method === 'POST') { writes.push(JSON.parse(typeof init.body === 'string' ? init.body : '{}') as { id: string; body: string }); return Promise.reject(new TypeError('lost ack')) }
    return reply(url.startsWith('/api/comments/') ? 404 : 200, page())
  })
  await submit(' hello ')
  expect(await screen.findByRole('button', { name: '状態を確認' })).toBeVisible()
  expect(screen.getByLabelText('送信した本文')).toHaveValue('hello')
  expect(screen.getByLabelText('送信した本文')).toHaveAttribute('readonly')
  fireEvent.click(screen.getByRole('button', { name: '状態を確認' }))
  fireEvent.click(await screen.findByRole('button', { name: '同じ内容で1回再送' }))
  await waitFor(() => { expect(writes).toHaveLength(2) })
  fireEvent.click(screen.getByRole('button', { name: '状態を確認' }))
  expect(await screen.findByText(/再送しません/)).toBeVisible()
  expect(screen.queryByRole('button', { name: '同じ内容で1回再送' })).toBeNull()
  expect(writes[1]).toEqual(writes[0]); expect(writes[0]?.body).toBe('hello')
  expect(callbacks.onUncertain).toHaveBeenCalledWith(expect.any(Symbol), true)
  const event = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(event); expect(event.defaultPrevented).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: '確認を中断' }))
  expect(await screen.findByRole('alertdialog', { name: '確認の中断' })).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: '中断して一覧へ戻る' }))
  expect(screen.getByLabelText('コメント本文')).toHaveValue('')
  expect(callbacks.onUncertain).toHaveBeenLastCalledWith(expect.any(Symbol), false)
})
it('preserves the prior unknown and snapshot when retry preflight fails', async () => {
  let checks = 0; const writes: unknown[] = []
  setup((url, init) => {
    if (init?.method === 'POST') { writes.push(init.body); return Promise.reject(new TypeError('offline')) }
    return reply(url.startsWith('/api/comments/') ? 404 : 200, page())
  })
  await submit(); fireEvent.click(await screen.findByRole('button', { name: '状態を確認' }))
  await screen.findByRole('button', { name: '同じ内容で1回再送' })
  const previous = globalThis.fetch
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => { if (url === '/api/auth/me' && ++checks === 1) return Promise.resolve(reply(503, { code: 'SERVICE_UNAVAILABLE' })); return previous(url, init) }))
  fireEvent.click(screen.getByRole('button', { name: '同じ内容で1回再送' }))
  expect(await screen.findByText(/今回未送信、前回結果不明/)).toBeVisible()
  expect(screen.getByLabelText('送信した本文')).toHaveValue('hello'); expect(writes).toHaveLength(1)
  expect(screen.getByRole('button', { name: '状態を確認' })).toBeEnabled()
})
it('marks conflict then GET404 terminal without recreating the comment', async () => {
  let writes = 0
  setup((url, init) => { if (init?.method === 'POST') { writes++; return writes === 1 ? Promise.reject(new TypeError('ack')) : reply(409, { code: 'COMMENT_ID_CONFLICT' }) } return reply(url.startsWith('/api/comments/') ? 404 : 200, page()) })
  await submit(); fireEvent.click(await screen.findByRole('button', { name: '状態を確認' })); fireEvent.click(await screen.findByRole('button', { name: '同じ内容で1回再送' }))
  await waitFor(() => { expect(writes).toBe(2) }); fireEvent.click(screen.getByRole('button', { name: '状態を確認' }))
  expect(await screen.findByText(/再送しません/)).toBeVisible(); expect(screen.queryByRole('button', { name: '同じ内容で1回再送' })).toBeNull()
})
it('discards all old pages after creation and removes the separate confirmation only when server pages include its id', async () => {
  let created = false; const reads: string[] = []; let sentId = ''
  setup((url, init) => {
    if (init?.method === 'POST') { created = true; sentId = (JSON.parse(typeof init.body === 'string' ? init.body : '{}') as { id: string }).id; return reply(201, result('hello', sentId)) }
    reads.push(url)
    if (created) return reply(200, url.includes('?cursor=') ? page([{ ...comment, id: sentId }]) : page([{ ...comment, id: 'older', body: 'older' }], 'next'))
    return reply(200, page([], null))
  })
  await submit(); expect(await screen.findByRole('region', { name: '送信したコメント' })).toBeVisible()
  expect(reads).toEqual(['/api/posts/' + postId + '/comments', '/api/posts/' + postId + '/comments'])
  fireEvent.click(screen.getByRole('button', { name: 'もっとコメントを見る' }))
  await waitFor(() => { expect(screen.queryByRole('region', { name: '送信したコメント' })).toBeNull() })
  expect(screen.getAllByText('hello')).toHaveLength(1)
})
it('keeps an acknowledged success when the following page read fails', async () => {
  let created = false
  setup((_url, init) => { if (init?.method === 'POST') { created = true; return reply(201, result('hello', (JSON.parse(typeof init.body === 'string' ? init.body : '{}') as { id: string }).id)) } return created ? reply(503, {}) : reply(200, page()) })
  await submit(); expect(await screen.findByText(/送信済み。一覧を再読み込み/)).toBeVisible()
  expect(screen.getByRole('region', { name: '送信したコメント' })).toBeVisible(); expect(screen.getByLabelText('コメント本文')).toHaveValue('')
  expect(screen.queryByRole('button', { name: '状態を確認' })).toBeNull()
})
it('keeps a PUT snapshot when detail differs and resumes only on an explicit choice', async () => {
  let written = false
  setup((url, init) => {
    if (init?.method === 'PUT') { written = true; return Promise.reject(new TypeError('ack')) }
    return reply(200, url.startsWith('/api/comments/') ? result('other tab') : page([comment]))
  })
  fireEvent.click(await screen.findByRole('button', { name: '編集' }))
  fireEvent.change(screen.getByLabelText('コメント本文'), { target: { value: 'new body' } }); fireEvent.click(screen.getByRole('button', { name: '変更を保存' }))
  fireEvent.click(await screen.findByRole('button', { name: '状態を確認' }))
  expect(await screen.findByText('現在の保存内容')).toBeVisible(); expect(screen.getByLabelText('送信した本文')).toHaveValue('new body'); expect(written).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: '現在の内容で編集を開き直す' }))
  expect(screen.getByLabelText('コメント本文')).toHaveValue('other tab')
})
it('treats DELETE detail404 neutrally, resets pages and focuses the heading even if reload fails', async () => {
  let deleted = false
  const callbacks = setup((url, init) => { if (init?.method === 'DELETE') { deleted = true; return Promise.reject(new TypeError('ack')) } return url.startsWith('/api/comments/') ? reply(404, {}) : deleted ? reply(503, {}) : reply(200, page([comment])) })
  fireEvent.click(await screen.findByRole('button', { name: '削除' })); fireEvent.click(await screen.findByRole('button', { name: 'コメントを削除する' }))
  fireEvent.click(await screen.findByRole('button', { name: '状態を確認' }))
  expect(await screen.findByText('現在は表示されていません。')).toBeVisible()
  await waitFor(() => { expect(screen.getByRole('heading', { name: 'コメント' })).toHaveFocus() })
  expect(screen.queryByRole('button', { name: '状態を確認' })).toBeNull(); expect(callbacks.onUncertain).toHaveBeenLastCalledWith(expect.any(Symbol), false)
})
it('revalidates identity on invalid cursor and waits for explicit first-page reload', async () => {
  let reads = 0
  setup(() => { reads++; return reads === 1 ? reply(200, page([comment], 'old')) : reply(400, { code: 'INVALID_CURSOR' }) })
  fireEvent.click(await screen.findByRole('button', { name: 'もっとコメントを見る' }))
  expect(await screen.findByRole('button', { name: 'コメントを先頭から再読み込み' })).toBeVisible()
  expect(screen.queryByText('hello')).toBeNull(); expect(reads).toBe(2)
})
it('does not optimistically toggle a like and confirms an unknown outcome without reversing it', async () => {
  let resolve!: (v: Response) => void; let writes = 0
  const callbacks = { onIdentity: vi.fn(), onBusy: vi.fn(), onUncertain: vi.fn(), onLike: vi.fn() }
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    if (url === '/api/auth/me') return Promise.resolve(reply(200, actor))
    if (url === '/api/auth/csrf') return Promise.resolve(reply(200, { csrf_token: 'token' }))
    if (init?.method === 'POST') { writes++; return new Promise<Response>(r => { resolve = r }) }
    return reply(503, {})
  }))
  render(<LikeButton account={actor} post={{ id: postId, viewer_id: actor.id, like_count: 0, is_liked: false } as Workout} {...callbacks} />)
  fireEvent.click(screen.getByRole('button', { name: 'いいね', pressed: false }))
  await waitFor(() => { expect(writes).toBe(1) }); expect(screen.getByRole('button', { name: 'いいね', pressed: false })).toHaveAttribute('aria-pressed', 'false'); expect(screen.getByRole('button', { name: 'いいね', pressed: false })).toHaveAccessibleDescription('0件')
  act(() => { resolve(reply(503, {})) })
  expect(await screen.findByRole('button', { name: 'いいねの状態を確認' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'いいね', pressed: false })).toBeDisabled(); expect(callbacks.onLike).not.toHaveBeenCalled()
})
it('keeps invalid controls editable without sending and counts emoji as one code point', async () => {
  let writes = 0
  setup((_url, init) => { if (init?.method === 'POST') { writes++; return reply(201, result((JSON.parse(typeof init.body === 'string' ? init.body : '{}') as { body: string }).body, (JSON.parse(typeof init.body === 'string' ? init.body : '{}') as { id: string }).id)) } return reply(200, page()) })
  await submit('\u0000hello'); expect(await screen.findByText('使用できない文字が含まれています。')).toBeVisible(); expect(writes).toBe(0)
  await submit('🙂'.repeat(501)); expect(await screen.findByText(/1〜500文字/)).toBeVisible(); expect(writes).toBe(0)
  await submit('🙂'.repeat(500)); await waitFor(() => { expect(writes).toBe(1) }); await waitFor(() => { expect(screen.getByLabelText('コメント本文')).toHaveValue('') })
})
it('uses the normal success path for same UUID retry201 after detail404', async () => {
  const writes: string[] = []; let success = false
  const callbacks = setup((url, init) => {
    if (init?.method === 'POST') { const payload = JSON.parse(typeof init.body === 'string' ? init.body : '{}') as { id: string }; writes.push(payload.id); if (writes.length === 1) return Promise.reject(new TypeError('lost')); success = true; return reply(201, result('hello', payload.id)) }
    return url.startsWith('/api/comments/') ? reply(404, {}) : reply(200, page(success ? [{ ...comment, id: writes[0] ?? '' }] : []))
  })
  await submit(); fireEvent.click(await screen.findByRole('button', { name: '状態を確認' })); fireEvent.click(await screen.findByRole('button', { name: '同じ内容で1回再送' }))
  expect(await screen.findByText('コメントを送信しました。')).toBeVisible(); expect(writes).toHaveLength(2); expect(writes[0]).toBe(writes[1]); expect(screen.getByLabelText('コメント本文')).toHaveValue(''); expect(callbacks.onUncertain).toHaveBeenLastCalledWith(expect.any(Symbol), false)
})
it.each([{ status: 200, body: 'new body', message: 'コメントを保存しました。', frozen: false }, { status: 404, body: '', message: '現在は表示されていません。確認を中断して一覧へ戻れます。', frozen: true }, { status: 503, body: '', message: '前回の結果は不明です。状態を確認するか確認を中断してください。', frozen: true }])('reconciles PUT status=$status without falsely treating other states as success', async ({ status, body, message, frozen }) => {
  setup((url, init) => { if (init?.method === 'PUT') return Promise.reject(new TypeError('lost')); return url.startsWith('/api/comments/') ? reply(status, result(body)) : reply(200, page([comment])) })
  fireEvent.click(await screen.findByRole('button', { name: '編集' })); fireEvent.change(screen.getByLabelText('コメント本文'), { target: { value: 'new body' } }); fireEvent.click(screen.getByRole('button', { name: '変更を保存' }))
  fireEvent.click(await screen.findByRole('button', { name: '状態を確認' })); expect(await screen.findByText(message)).toBeVisible()
  if (frozen) { expect(screen.getByLabelText('送信した本文')).toHaveValue('new body'); expect(screen.getByRole('button', { name: '確認を中断' })).toBeEnabled() } else expect(screen.getByLabelText('コメント本文')).toHaveValue('')
})
it.each([200, 503])('keeps DELETE snapshot on detail$status and allows only explicit actions', async status => {
  let writes = 0
  setup((url, init) => { if (init?.method === 'DELETE') { writes++; return Promise.reject(new TypeError('lost')) } return url.startsWith('/api/comments/') ? reply(status, result()) : reply(200, page([comment])) })
  fireEvent.click(await screen.findByRole('button', { name: '削除' })); expect(await screen.findByRole('button', { name: 'キャンセル' })).toHaveFocus(); fireEvent.click(screen.getByRole('button', { name: 'コメントを削除する' })); fireEvent.click(await screen.findByRole('button', { name: '状態を確認' }))
  expect(await screen.findByText(status === 200 ? '現在はコメントが残っています。削除する場合は明示的に操作してください。' : '前回の結果は不明です。状態を確認するか確認を中断してください。')).toBeVisible()
  expect(screen.getByLabelText('送信した本文')).toHaveValue('hello'); expect(writes).toBe(1); expect(screen.getByRole('button', { name: '確認を中断' })).toBeEnabled()
})
it('keeps a separate unsent draft after DELETE204 even when refreshing counts fails', async () => {
  let deleted = false
  setup((_url, init) => { if (init?.method === 'DELETE') { deleted = true; return reply(204) } return deleted ? reply(503, {}) : reply(200, page([comment])) })
  await screen.findByRole('button', { name: 'コメントする' }); fireEvent.change(screen.getByLabelText('コメント本文'), { target: { value: 'separate draft' } }); fireEvent.click(screen.getByRole('button', { name: '削除' })); fireEvent.click(await screen.findByRole('button', { name: 'コメントを削除する' }))
  expect(await screen.findByText(/削除済み、件数を更新できません/)).toBeVisible(); expect(screen.getByLabelText('コメント本文')).toHaveValue('separate draft'); expect(screen.queryByRole('button', { name: '状態を確認' })).toBeNull()
})
it('discards a stale initial page after a successful create invalidates its generation', async () => {
  let finish!: (value: Response) => void; let reads = 0
  setup((_url, init) => { if (init?.method === 'POST') return reply(201, result('hello', (JSON.parse(typeof init.body === 'string' ? init.body : '{}') as { id: string }).id)); reads++; return reads === 1 ? new Promise<Response>(resolve => { finish = resolve }) : reply(200, page([{ ...comment, body: 'fresh page' }])) })
  await submit(); expect(await screen.findByText('fresh page')).toBeVisible()
  act(() => { finish(reply(200, page([{ ...comment, body: 'stale page' }]))) })
  await waitFor(() => { expect(screen.queryByText('stale page')).toBeNull() }); expect(screen.getByText('fresh page')).toBeVisible()
})
it('clears every draft and snapshot on a changed viewer response and never resends', async () => {
  let writes = 0
  const callbacks = setup((_url, init) => { if (init?.method === 'POST') { writes++; return reply(201, { ...result(), viewer_id: 'other' }) } return reply(200, page()) })
  await submit(); await waitFor(() => { expect(callbacks.onIdentity).toHaveBeenCalled() }); expect(writes).toBe(1); expect(screen.queryByLabelText('送信した本文')).toBeNull(); expect(screen.getByLabelText('コメント本文')).toHaveValue('')
})
it('disables new writes after a missing parent while keeping an unknown snapshot available for explicit abandonment', async () => {
  let sent = false
  const callbacks = setup((url, init) => { if (init?.method === 'POST') { sent = true; return Promise.reject(new TypeError('lost')) } return url.startsWith('/api/comments/') || url === '/api/posts/' + postId ? reply(404, {}) : reply(200, page()) })
  await submit(); fireEvent.click(await screen.findByRole('button', { name: '状態を確認' })); await waitFor(() => { expect(callbacks.onMissing).toHaveBeenCalled() }); expect(sent).toBe(true); expect(screen.getByLabelText('送信した本文')).toHaveValue('hello'); expect(screen.queryByRole('button', { name: '同じ内容で1回再送' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '確認を中断' })); fireEvent.click(await screen.findByRole('button', { name: '中断して一覧へ戻る' })); expect(screen.getByRole('button', { name: 'コメントする' })).toBeDisabled()
})

import App from '../App'
import WorkoutFeed from '../workouts/WorkoutFeed'
const postDto: Workout = { id: postId, viewer_id: actor.id, image: null, author: comment.author, is_owner: true, performed_on: '2026-10-30', note: '', created_at: comment.created_at, updated_at: comment.updated_at, exercises: [{ name: 'Squat', sets: [{ weight_kg: '60.00', reps: 10 }] }], energy: null, energy_input: { minutes: null, kind: null }, visibility: { minutes: 'private', kind: 'private' }, like_count: 0, comment_count: 0, is_liked: false }
it('prevents feed reload from destroying a like unknown confirmation', async () => {
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    if (url === '/api/auth/me') return Promise.resolve(reply(200, actor)); if (url === '/api/auth/csrf') return Promise.resolve(reply(200, { csrf_token: 'token' }))
    if (init?.method === 'POST') return Promise.reject(new TypeError('lost'))
    return Promise.resolve(reply(200, { viewer_id: actor.id, items: [postDto], next_cursor: 'more' }))
  }))
  render(<WorkoutFeed account={actor} username="river" onIdentity={vi.fn()} />)
  fireEvent.click(await screen.findByRole('button', { name: 'いいね', pressed: false })); await screen.findByRole('button', { name: 'いいねの状態を確認' })
  expect(screen.getByRole('button', { name: '画像と一覧を再読み込み' })).toBeDisabled(); expect(screen.getByRole('button', { name: 'もっと見る' })).toBeDisabled()
})
it('keeps all simultaneous busy tokens until every pending like has completed', async () => {
  location.hash = ''; const pending = new Map<string, (value: Response) => void>()
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    if (url === '/api/auth/me') return Promise.resolve(reply(200, actor)); if (url === '/api/auth/csrf') return Promise.resolve(reply(200, { csrf_token: 'token' }))
    if (init?.method === 'POST') return new Promise<Response>(resolve => { pending.set(url, resolve) })
    return Promise.resolve(reply(200, { viewer_id: actor.id, items: [postDto, { ...postDto, id: '55555555-5555-4555-8555-555555555555' }], next_cursor: null }))
  }))
  render(<App />); const buttons = await screen.findAllByRole('button', { name: 'いいね', pressed: false }); const first = buttons[0]; const second = buttons[1]; if (!first || !second) throw Error('two cards required')
  fireEvent.click(first); fireEvent.click(second); await waitFor(() => { expect(pending.size).toBe(2) })
  act(() => { pending.get('/api/posts/55555555-5555-4555-8555-555555555555/like')?.(reply(200, { viewer_id: actor.id, post_id: '55555555-5555-4555-8555-555555555555', like_count: 1, is_liked: true })) })
  await screen.findByRole('button', { name: 'いいね', pressed: true }); expect(screen.getByRole('button', { name: 'ログアウト' })).toBeDisabled()
  act(() => { location.hash = '#profile'; window.dispatchEvent(new HashChangeEvent('hashchange')) }); expect(location.hash).toBe('')
  act(() => { pending.get('/api/posts/' + postId + '/like')?.(reply(200, { viewer_id: actor.id, post_id: postId, like_count: 1, is_liked: true })) })
  await waitFor(() => { expect(screen.getByRole('button', { name: 'ログアウト' })).toBeEnabled() }); expect(screen.getAllByRole('button', { name: 'いいね', pressed: true })).toHaveLength(2); for (const button of screen.getAllByRole('button', { name: 'いいね', pressed: true })) expect(button).toHaveAccessibleDescription('1件')
})
it('does not let a late confirmation GET404 erase a newer sent comment', async () => {
  let finish!: (value: Response) => void; let serial = 0
  setup((url, init) => {
    if (init?.method === 'POST') { const body = JSON.parse(typeof init.body === 'string' ? init.body : '{}') as { id: string; body: string }; serial++; return reply(201, result(body.body, body.id)) }
    if (url.startsWith('/api/comments/')) return new Promise<Response>(resolve => { finish = resolve })
    return reply(200, page())
  })
  await submit(); await screen.findByRole('region', { name: '送信したコメント' }); await waitFor(() => { expect(screen.getByRole('button', { name: 'コメントを先頭から再読み込み' })).toBeEnabled() })
  fireEvent.click(screen.getByRole('button', { name: 'コメントを先頭から再読み込み' })); await submit('second body'); await waitFor(() => { expect(serial).toBe(2) }); expect(await screen.findByText('second body')).toBeVisible()
  act(() => { finish(reply(404, {})) }); await waitFor(() => { expect(screen.getByRole('region', { name: '送信したコメント' })).toBeVisible() }); expect(screen.getByText('second body')).toBeVisible()
})
it('retains prior unknown when CSRF recovery fails then clears it only on an actual identity change', async () => {
  let writes = 0
  const callbacks = setup((url, init) => {
    if (init?.method === 'POST') { writes++; return writes === 1 ? Promise.reject(new TypeError('lost')) : reply(403, { code: 'CSRF_FAILED' }) }
    return reply(url.startsWith('/api/comments/') ? 404 : 200, page())
  })
  await submit(); fireEvent.click(await screen.findByRole('button', { name: '状態を確認' })); fireEvent.click(await screen.findByRole('button', { name: '同じ内容で1回再送' })); expect(await screen.findByText(/安全性の確認を更新しました。前回結果不明/)).toBeVisible(); expect(screen.getByLabelText('送信した本文')).toHaveValue('hello')
  const prior = globalThis.fetch; vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => url === '/api/auth/me' ? Promise.resolve(reply(200, { ...actor, id: 'other' })) : prior(url, init)))
  fireEvent.click(screen.getByRole('button', { name: '状態を確認' })); await waitFor(() => { expect(callbacks.onIdentity).toHaveBeenCalledWith(expect.objectContaining({ id: 'other' }), expect.any(String)) }); expect(screen.queryByLabelText('送信した本文')).toBeNull(); expect(screen.getByLabelText('コメント本文')).toHaveValue(''); expect(writes).toBe(2)
})
it('keeps the initial draft after failed preflight and makes zero comment writes', async () => {
  let writes = 0
  setup((_url, init) => { if (init?.method === 'POST') writes++; return reply(200, page()) })
  const prior = globalThis.fetch; vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => url === '/api/auth/me' ? Promise.resolve(reply(503, { code: 'SERVICE_UNAVAILABLE' })) : prior(url, init)))
  await submit(); expect(await screen.findByText(/未送信です。入力を保持/)).toBeVisible(); expect(screen.getByLabelText('コメント本文')).toHaveValue('hello'); expect(screen.getByRole('button', { name: 'コメントする' })).toBeEnabled(); expect(writes).toBe(0)
})
it('clears the immutable snapshot on401 and returns an explicit check-existing-comments notice', async () => {
  const callbacks = setup((url, init) => { if (init?.method === 'POST') return Promise.reject(new TypeError('lost')); return url.startsWith('/api/comments/') ? reply(401, { code: 'AUTH_REQUIRED' }) : reply(200, page()) })
  await submit(); fireEvent.click(await screen.findByRole('button', { name: '状態を確認' })); await waitFor(() => { expect(callbacks.onIdentity).toHaveBeenCalledWith(null, expect.stringContaining('既存のコメントを確認')) }); expect(screen.queryByLabelText('送信した本文')).toBeNull(); expect(screen.getByLabelText('コメント本文')).toHaveValue('')
})
it('keeps an existing parent visible after normal DELETE404 and reloads the first comment page neutrally', async () => {
  let deleted = false; const reads: string[] = []
  const callbacks = setup((url, init) => { if (init?.method === 'DELETE') { deleted = true; return reply(404, {}) } reads.push(url); if (url === '/api/posts/' + postId) return reply(200, postDto); return reply(200, page(deleted ? [] : [comment], deleted ? null : 'old')) })
  fireEvent.click(await screen.findByRole('button', { name: '削除' })); fireEvent.click(await screen.findByRole('button', { name: 'コメントを削除する' }))
  expect(await screen.findByText('現在は表示されていません。')).toBeVisible(); expect(callbacks.onMissing).not.toHaveBeenCalled(); expect(await screen.findByText('まだコメントがありません。')).toBeVisible(); expect(reads.filter(url => url.endsWith('/comments'))).toHaveLength(2)
})
it('retains a PUT404 draft and focuses the editing textarea until explicit cancellation returns to the list', async () => {
  const callbacks = setup((url, init) => init?.method === 'PUT' ? reply(404, {}) : reply(200, url === '/api/posts/' + postId ? postDto : page([comment])))
  fireEvent.click(await screen.findByRole('button', { name: '編集' })); expect(screen.getByLabelText('コメント本文')).toHaveFocus(); expect(screen.getByLabelText('コメント本文')).toHaveAccessibleDescription(/編集対象/)
  fireEvent.change(screen.getByLabelText('コメント本文'), { target: { value: 'unsaved edit' } }); fireEvent.click(screen.getByRole('button', { name: '変更を保存' }))
  expect(await screen.findByText(/現在は表示されていません/)).toBeVisible(); expect(callbacks.onMissing).not.toHaveBeenCalled(); expect(screen.getByLabelText('コメント本文')).toHaveValue('unsaved edit'); expect(screen.getByRole('button', { name: '変更を保存' })).toBeDisabled(); expect(screen.queryByRole('button', { name: '削除' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '編集をキャンセル' })); expect(await screen.findByRole('button', { name: 'コメントする' })).toBeEnabled()
})
it.each([503, 404, 401])('checks the actual parent after PUT404 without guessing from parent GET status %i', async status => {
  const callbacks = setup((url, init) => init?.method === 'PUT' ? reply(404, {}) : url === '/api/posts/' + postId ? reply(status, {}) : reply(200, page([comment])))
  fireEvent.click(await screen.findByRole('button', { name: '編集' })); fireEvent.change(screen.getByLabelText('コメント本文'), { target: { value: 'draft' } }); fireEvent.click(screen.getByRole('button', { name: '変更を保存' }))
  await waitFor(() => { if (status === 404) expect(callbacks.onMissing).toHaveBeenCalledTimes(1); else if (status === 401) expect(callbacks.onIdentity).toHaveBeenCalledWith(null, expect.any(String)); else expect(screen.getByText(/記録の表示状態を確認できません/)).toBeVisible() })
  if (status !== 404) expect(callbacks.onMissing).not.toHaveBeenCalled()
  if (status === 503) expect(screen.getByLabelText('コメント本文')).toHaveValue('draft')
})
it('abandons only the like guard after an explicit warning and keeps its unconfirmed toggle disabled', async () => {
  let writes = 0; const callbacks = { onIdentity: vi.fn(), onBusy: vi.fn(), onUncertain: vi.fn(), onLike: vi.fn() }
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => { if (url === '/api/auth/me') return Promise.resolve(reply(200, actor)); if (url === '/api/auth/csrf') return Promise.resolve(reply(200, { csrf_token: 'token' })); if (init?.method === 'POST') { writes++; return Promise.reject(new TypeError('lost')) } return Promise.resolve(reply(200, { ...postDto, like_count: 1, is_liked: true })) }))
  render(<LikeButton account={actor} post={postDto} {...callbacks} />)
  fireEvent.click(screen.getByRole('button', { name: 'いいね' })); await screen.findByRole('button', { name: 'いいねの状態を確認' }); fireEvent.click(screen.getByRole('button', { name: '確認を中断' }))
  expect(await screen.findByRole('alertdialog', { name: 'いいねの確認の中断' })).toBeVisible(); expect(screen.getByRole('button', { name: 'キャンセル' })).toHaveFocus(); expect(screen.getByText(/状態は未確認/)).toBeVisible()
  fireEvent(screen.getByRole('alertdialog', { name: 'いいねの確認の中断' }), new Event('cancel', { cancelable: true })); expect(screen.queryByRole('alertdialog')).toBeNull(); expect(screen.getByRole('button', { name: '確認を中断' })).toHaveFocus(); expect(callbacks.onUncertain).toHaveBeenLastCalledWith(expect.any(Symbol), true)
  fireEvent.click(screen.getByRole('button', { name: '確認を中断' })); fireEvent.click(screen.getByRole('button', { name: '中断して画面を離れる' })); expect(callbacks.onBusy).toHaveBeenLastCalledWith(expect.any(Symbol), false); expect(callbacks.onUncertain).toHaveBeenLastCalledWith(expect.any(Symbol), false); expect(callbacks.onLike).not.toHaveBeenCalled(); expect(writes).toBe(1)
  expect(screen.getByRole('button', { name: 'いいね' })).toBeDisabled(); const event = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(event); expect(event.defaultPrevented).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: 'いいねの状態を確認' })); await waitFor(() => { expect(callbacks.onLike).toHaveBeenCalledWith({ like_count: 1, is_liked: true }) }); expect(screen.getByRole('button', { name: 'いいね' })).toBeEnabled(); expect(writes).toBe(1)
})
it('preserves an unknown DELETE snapshot after a further DELETE404 while the parent still exists', async () => {
  let writes = 0; const callbacks = setup((url, init) => {
    if (init?.method === 'DELETE') { writes++; return writes === 1 ? Promise.reject(new TypeError('lost')) : reply(404, {}) }
    if (url === '/api/posts/' + postId) return reply(200, postDto)
    return reply(200, url.startsWith('/api/comments/') ? result() : page([comment]))
  })
  fireEvent.click(await screen.findByRole('button', { name: '削除' })); fireEvent.click(await screen.findByRole('button', { name: 'コメントを削除する' })); fireEvent.click(await screen.findByRole('button', { name: '状態を確認' })); fireEvent.click(await screen.findByRole('button', { name: '同じコメントを削除する' }))
  expect(await screen.findByText('現在は表示されていません。前回の結果は不明です。状態を確認するか確認を中断してください。')).toBeVisible(); expect(callbacks.onMissing).not.toHaveBeenCalled(); expect(screen.getByLabelText('送信した本文')).toHaveValue('hello'); expect(callbacks.onUncertain).toHaveBeenLastCalledWith(expect.any(Symbol), true); expect(writes).toBe(2)
})
it('discards the PUT404 draft if confirming the parent returns a changed viewer', async () => {
  const callbacks = setup((url, init) => init?.method === 'PUT' ? reply(404, {}) : reply(200, url === '/api/posts/' + postId ? { ...postDto, viewer_id: 'other' } : page([comment])))
  fireEvent.click(await screen.findByRole('button', { name: '編集' })); fireEvent.change(screen.getByLabelText('コメント本文'), { target: { value: 'private draft' } }); fireEvent.click(screen.getByRole('button', { name: '変更を保存' }))
  await waitFor(() => { expect(callbacks.onIdentity).toHaveBeenCalled() }); expect(callbacks.onMissing).not.toHaveBeenCalled(); expect(screen.getByLabelText('コメント本文')).toHaveValue(''); expect(screen.queryByLabelText('送信した本文')).toBeNull()
})
it('disables every row action after PUT404 until explicit cancellation and updates only the parent comment count', async () => {
  let missing = false
  const second = { ...comment, id: '66666666-6666-4666-8666-666666666666', body: 'second comment' }
  const callbacks = setup((url, init) => {
    if (init?.method === 'PUT') { missing = true; return reply(404, {}) }
    if (url === '/api/posts/' + postId) return reply(200, { ...postDto, comment_count: 1, like_count: 7, is_liked: true })
    return reply(200, page(missing ? [second] : [comment, second]))
  })
  const firstEdit = (await screen.findAllByRole('button', { name: '編集' }))[0]
  if (!firstEdit) throw Error('first comment required')
  fireEvent.click(firstEdit); fireEvent.change(screen.getByLabelText('コメント本文'), { target: { value: 'unsaved missing edit' } }); fireEvent.click(screen.getByRole('button', { name: '変更を保存' }))
  await screen.findByText(/現在は表示されていません。編集内容を保持/)
  await waitFor(() => { expect(callbacks.onCount).toHaveBeenLastCalledWith(1) })
  for (const button of screen.getAllByRole('button', { name: /^(編集|削除)$/ })) expect(button).toBeDisabled()
  expect(screen.getByLabelText('コメント本文')).toHaveValue('unsaved missing edit')
  fireEvent.click(screen.getByRole('button', { name: '編集をキャンセル' }))
  await waitFor(() => { expect(screen.getAllByRole('button', { name: '編集' })).toHaveLength(1) })
  expect(screen.getByRole('button', { name: '編集' })).toBeEnabled(); expect(screen.getByRole('button', { name: '削除' })).toBeEnabled(); expect(screen.queryByText('hello')).toBeNull()
})
it('keeps the visible like label equal to the accessible name in the liked state', () => {
  render(<LikeButton account={actor} post={{ ...postDto, is_liked: true, like_count: 3 }} onIdentity={vi.fn()} onBusy={vi.fn()} onUncertain={vi.fn()} onLike={vi.fn()} />)
  const button = screen.getByRole('button', { name: 'いいね', pressed: true })
  expect(button).toHaveTextContent('いいね'); expect(button).not.toHaveTextContent('いいね済み'); expect(button).toHaveAccessibleDescription('3件')
  expect(button.querySelector('[aria-hidden="true"]')).toHaveTextContent('♥')
})
