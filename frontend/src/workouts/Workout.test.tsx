import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import App from '../App'
import type { Account } from '../auth/api'
import { privateFlags } from '../profile/types'
import WorkoutScreen from './WorkoutScreen'
import WorkoutCard from './WorkoutCard'
import WorkoutFeed from './WorkoutFeed'
import type { Workout } from './types'

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); location.hash = '' })
const owner: Account = { id: '11111111-1111-4111-8111-111111111111', username: 'river_user', display_name: 'River', email: 'river@example.test' }
const other: Account = { ...owner, id: '22222222-2222-4222-8222-222222222222', username: 'other_user' }
const base: Workout = { image: null, viewer_id: owner.id, id: '33333333-3333-4333-8333-333333333333', author: { id: owner.id, username: owner.username, display_name: owner.display_name, avatar: null }, is_owner: true, performed_on: '2024-02-29', note: '記録メモ', created_at: '2024-02-29T00:00:00.123456Z', updated_at: '2024-02-29T00:00:00.123456Z', exercises: [{ name: 'ベンチプレス', sets: [{ weight_kg: '60.00', reps: 10 }] }], energy: { kcal: 105, method: 'met-gross-v1' }, energy_input: { minutes: 30, kind: 'general' }, visibility: { minutes: 'private', kind: 'private' } }
function reply(status: number, value: unknown): Response { return new Response(status === 204 ? null : JSON.stringify(value), { status }) }
function mock(options: { write?: (init: RequestInit) => Response | Promise<Response>; read?: (url: string) => Response | Promise<Response>; me?: () => Account | Response | Promise<Account | Response> } = {}) {
  const count = { writes: 0, csrf: 0 }
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    if (url === '/api/auth/me') { const me = await (options.me?.() ?? owner); return me instanceof Response ? me : reply(200, me) }
    if (url === '/api/auth/csrf') { count.csrf++; return reply(200, { csrf_token: 'csrf' }) }
    if (url === '/api/users/me') return reply(200, { viewer_id: owner.id, avatar: null, id: owner.id, username: owner.username, display_name: owner.display_name, bio: '', is_owner: true, health: { height: null, weight: '60.0', age: 30, formula: null, activity: null }, energy: { bmr: null, tdee: null, intake: null }, visibility: privateFlags() })
    if (init?.method && init.method !== 'GET') { count.writes++; return await (options.write?.(init) ?? reply(200, base)) }
    return await (options.read?.(url) ?? reply(200, base))
  }))
  return count
}
function form(initial: Workout | null = null) {
  const callbacks = { identity: vi.fn(), busy: vi.fn(), saved: vi.fn(), cleared: vi.fn(), uncertain: vi.fn() }
  render(<WorkoutScreen account={owner} id={initial?.id ?? null} editing={true} initial={initial} onIdentity={callbacks.identity} onBusy={callbacks.busy} onSaved={callbacks.saved} onClearSaved={callbacks.cleared} onUncertain={callbacks.uncertain} />)
  return callbacks
}
async function fill() {
  await screen.findByRole('button', { name: '記録する' })
  fireEvent.change(screen.getByLabelText('種目名'), { target: { value: 'ベンチプレス' } })
  fireEvent.change(screen.getByLabelText('種目1 セット1 重量（kg）'), { target: { value: '60' } })
  fireEvent.change(screen.getByLabelText('種目1 セット1 回数'), { target: { value: '10' } })
  fireEvent.change(screen.getByLabelText('運動した時間（分）'), { target: { value: '30' } })
  fireEvent.change(screen.getByLabelText('トレーニングの種類'), { target: { value: 'general' } })
}
it('previews independent calories and sends stable id, owner, CSRF and private defaults', async () => {
  const saved = vi.fn()
  const count = mock({ write: init => {
    const headers = new Headers(init.headers)
    expect(headers.get('X-Record-Owner')).toBe(owner.id); expect(headers.get('X-CSRFToken')).toBe('csrf')
    const data = JSON.parse(typeof init.body === 'string' ? init.body : '{}') as { id: string; visibility: unknown }
    expect(data.visibility).toEqual({ minutes: 'private', kind: 'private' }); expect(data.id).toMatch(/^[0-9a-f-]{36}$/)
    saved(data.id); return reply(201, { ...base, id: data.id })
  } })
  const callbacks = form(); await fill()
  expect(screen.getByText('105 kcal')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: '記録する' }))
  await waitFor(() => { expect(callbacks.saved).toHaveBeenCalled() })
  expect(count.writes).toBe(1); expect(saved).toHaveBeenCalledTimes(1)
})
it('keeps validation input and links the field error without resending', async () => {
  const count = mock({ write: () => reply(400, { code: 'VALIDATION_ERROR', fieldErrors: { 'exercises.0.sets.0.reps': ['回数を確認してください。'] } }) })
  form(); await fill(); fireEvent.change(screen.getByLabelText('メモ'), { target: { value: 'private draft' } })
  fireEvent.click(screen.getByRole('button', { name: '記録する' }))
  expect(await screen.findByText('回数を確認してください。')).toBeVisible()
  expect(screen.getByLabelText('種目1 セット1 回数')).toHaveAttribute('aria-describedby', 'workout-exercises.0.sets.0.reps')
  expect(screen.getByLabelText('メモ')).toHaveValue('private draft'); expect(count.writes).toBe(1)
})
it('refreshes CSRF exactly once on 403 and never automatically repeats POST', async () => {
  const count = mock({ write: () => reply(403, { code: 'CSRF_FAILED' }) })
  form(); await fill(); fireEvent.click(screen.getByRole('button', { name: '記録する' }))
  expect(await screen.findByText('安全性の確認を更新しました。入力を確認してもう一度保存してください。')).toBeVisible()
  expect(count.csrf).toBe(2); expect(count.writes).toBe(1)
})
it('destroys the draft if identity changes after a CSRF rejection', async () => {
  let account = owner
  const count = mock({ me: () => account, write: () => { account = other; return reply(403, { code: 'CSRF_FAILED' }) } })
  const callbacks = form(); await fill(); fireEvent.change(screen.getByLabelText('メモ'), { target: { value: 'old draft' } })
  fireEvent.click(screen.getByRole('button', { name: '記録する' }))
  await waitFor(() => { expect(callbacks.identity).toHaveBeenCalledWith(other, expect.any(String)) })
  expect(screen.queryByLabelText('メモ')).not.toBeInTheDocument(); expect(count.csrf).toBe(1); expect(count.writes).toBe(1)
})
it('freezes an ambiguous POST then recovers using its original id without another POST', async () => {
  let sentId = ''
  const count = mock({ write: init => { sentId = (JSON.parse(typeof init.body === 'string' ? init.body : '{}') as { id: string }).id; throw new TypeError('network') }, read: url => { expect(url).toBe('/api/posts/' + sentId); return reply(200, { ...base, id: sentId }) } })
  const callbacks = form(); await fill(); fireEvent.click(screen.getByRole('button', { name: '記録する' }))
  const recover = await screen.findByRole('button', { name: /保存状態を確認（入力を破棄/ })
  expect(screen.getByLabelText('メモ')).toBeDisabled()
  fireEvent.click(recover)
  await waitFor(() => { expect(callbacks.saved).toHaveBeenCalledWith(expect.objectContaining({ id: sentId })) })
  expect(count.writes).toBe(1)
})
it('discards an edit when a concurrent deletion returns 404', async () => {
  mock({ write: () => reply(404, { code: 'NOT_FOUND' }) }); form(base)
  await screen.findByRole('button', { name: '変更を保存' })
  expect(screen.getByRole('textbox', { name: 'メモ' })).toHaveValue('記録メモ')
  fireEvent.click(screen.getByRole('button', { name: '変更を保存' }))
  expect(await screen.findByText('記録が見つかりません。')).toBeVisible()
  expect(screen.queryByLabelText('メモ')).not.toBeInTheDocument()
})
it('renders public calories without leaking private labels or reasons', () => {
  const publicValue = { ...base }; delete publicValue.visibility
  render(<WorkoutCard post={{ ...publicValue, viewer_id: other.id, is_owner: false, energy_input: {} }} />)
  expect(screen.getByText('消費カロリー 105 kcal')).toBeVisible()
  expect(screen.queryByText(/非公開|運動時間|安静時/)).not.toBeInTheDocument()
})
it('keeps read cards and restarts pagination explicitly after INVALID_CURSOR', async () => {
  let reads = 0
  mock({ read: url => {
    reads++
    if (reads === 1) return reply(200, { viewer_id: owner.id, items: [base], next_cursor: 'old' })
    if (reads === 2) { expect(url).toContain('cursor=old'); return reply(400, { code: 'INVALID_CURSOR' }) }
    expect(url).not.toContain('cursor='); return reply(200, { viewer_id: owner.id, items: [], next_cursor: null })
  } })
  render(<WorkoutFeed account={owner} username={owner.username} onIdentity={vi.fn()} />)
  fireEvent.click(await screen.findByRole('button', { name: 'もっと見る' }))
  const restart = await screen.findByRole('button', { name: '一覧を最初から読み込み直す' })
  expect(screen.getByText('ベンチプレス')).toBeVisible(); fireEvent.click(restart)
  expect(await screen.findByText('まだ記録がありません。')).toBeVisible()
})

it('returns to login with an explicit list-check notice if ambiguous save recovery gets 401', async () => {
  const count = mock({ write: () => reply(503, { code: 'SERVICE_UNAVAILABLE' }), read: () => reply(401, { code: 'AUTH_REQUIRED' }) })
  const callbacks = form(); await fill(); fireEvent.click(screen.getByRole('button', { name: '記録する' }))
  fireEvent.click(await screen.findByRole('button', { name: /保存状態を確認（入力を破棄/ }))
  await waitFor(() => { expect(callbacks.identity).toHaveBeenCalledWith(null, expect.stringContaining('ログイン後に記録一覧で保存されたか確認')) })
  expect(screen.queryByLabelText('メモ')).not.toBeInTheDocument(); expect(count.writes).toBe(1)
})

async function createInApp() {
  const server = { record: { ...base }, deleted: false, detailReads: 0 }
  mock({ write: init => {
    if (init.method === 'DELETE') { server.deleted = true; return reply(204, null) }
    const data = JSON.parse(typeof init.body === 'string' ? init.body : '{}') as { id: string }
    server.record = { ...base, id: data.id }
    return reply(201, server.record)
  }, read: url => {
    if (url.startsWith('/api/users/')) return reply(200, { viewer_id: owner.id, items: server.deleted ? [] : [server.record], next_cursor: null })
    server.detailReads++
    return server.deleted ? reply(404, { code: 'NOT_FOUND' }) : reply(200, server.record)
  } })
  location.hash = '#record-new'; render(<App />); await fill()
  fireEvent.click(screen.getByRole('button', { name: '記録する' }))
  await screen.findByRole('button', { name: '記録を削除' })
  return server
}
it('revisits a saved record through GET instead of reusing the one-shot handoff', async () => {
  const server = await createInApp()
  expect(server.detailReads).toBe(0)
  fireEvent.click(screen.getByRole('link', { name: 'ホーム' }))
  await screen.findByRole('heading', { name: 'Riverさん' })
  server.record = { ...server.record, note: '別タブで更新された内容' }
  fireEvent.click(await screen.findByRole('link', { name: '記録の詳細' }))
  expect(await screen.findByText('別タブで更新された内容')).toBeVisible()
  expect(server.detailReads).toBe(1)
  expect(screen.queryByText('記録を保存しました。')).not.toBeInTheDocument()
})
it('does not resurrect a deleted saved record on a back navigation', async () => {
  const server = await createInApp()
  // Native dialog mechanics are a browser boundary; this test exercises the actual delete flow.
  const originalShow = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'showModal')
  const originalClose = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'close')
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function (this: HTMLDialogElement) { this.setAttribute('open', '') } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function (this: HTMLDialogElement) { this.removeAttribute('open') } })
  try {
    fireEvent.click(screen.getByRole('button', { name: '記録を削除' }))
    expect(await screen.findByRole('alertdialog')).toBeVisible()
    expect(screen.getByRole('button', { name: 'キャンセル' })).toHaveFocus()
    fireEvent.click(screen.getByRole('button', { name: '削除する' }))
    await screen.findByText('まだ記録がありません。')
    act(() => { location.hash = '#record/' + server.record.id })
    expect(await screen.findByText('記録が見つかりません。')).toBeVisible()
    expect(screen.queryByText('記録を保存しました。')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '記録を削除' })).not.toBeInTheDocument()
  } finally {
    cleanup()
    if (originalShow) Object.defineProperty(HTMLDialogElement.prototype, 'showModal', originalShow)
    else Reflect.deleteProperty(HTMLDialogElement.prototype, 'showModal')
    if (originalClose) Object.defineProperty(HTMLDialogElement.prototype, 'close', originalClose)
    else Reflect.deleteProperty(HTMLDialogElement.prototype, 'close')
  }
})
it('does not assert PUT success when recovery returns old persisted data', async () => {
  const count = mock({ write: () => { throw new TypeError('network') }, read: () => reply(200, base) })
  const callbacks = form(base)
  await screen.findByRole('button', { name: '変更を保存' })
  fireEvent.change(screen.getByRole('textbox', { name: 'メモ' }), { target: { value: '送信できなかった変更' } })
  fireEvent.click(screen.getByRole('button', { name: '変更を保存' }))
  fireEvent.click(await screen.findByRole('button', { name: /保存状態を確認（入力を破棄/ }))
  expect(await screen.findByText('保存済みの記録を表示しました。変更が反映されているか確認してください。')).toBeVisible()
  expect(screen.queryByText('記録を保存しました。')).not.toBeInTheDocument()
  expect(screen.getByRole('textbox', { name: 'メモ' })).toHaveValue('記録メモ')
  expect(callbacks.saved).not.toHaveBeenCalled(); expect(count.writes).toBe(1)
})
it('resends the original frozen create payload only once after a confirmed 404', async () => {
  const bodies: unknown[] = []
  const count = mock({ write: init => { bodies.push(JSON.parse(typeof init.body === 'string' ? init.body : '{}') as unknown); throw new TypeError('network') }, read: () => reply(404, { code: 'NOT_FOUND' }) })
  form(); await fill(); fireEvent.change(screen.getByLabelText('メモ'), { target: { value: '最初に送信した内容' } })
  fireEvent.click(screen.getByRole('button', { name: '記録する' }))
  fireEvent.click(await screen.findByRole('button', { name: /保存状態を確認（入力を破棄/ }))
  fireEvent.click(await screen.findByRole('button', { name: '同じ内容で1回再送' }))
  await waitFor(() => { expect(count.writes).toBe(2) })
  const recover = screen.getByRole('button', { name: /保存状態を確認（入力を破棄/ })
  await waitFor(() => { expect(recover).toBeEnabled() }); fireEvent.click(recover)
  await screen.findByText('保存状態を確認できません。記録一覧で確認してください。')
  expect(screen.getByLabelText('メモ')).toBeDisabled()
  expect(screen.queryByRole('button', { name: '同じ内容で1回再送' })).not.toBeInTheDocument()
  expect(bodies[1]).toEqual(bodies[0]); expect(count.writes).toBe(2)
})
it('focus expiry after an ambiguous save preserves the check-your-list notice in App', async () => {
  let expired = false
  const count = mock({ me: () => expired ? reply(401, { code: 'AUTH_REQUIRED' }) : owner, write: () => reply(503, { code: 'SERVICE_UNAVAILABLE' }) })
  location.hash = '#record-new'; render(<App />); await fill()
  fireEvent.click(screen.getByRole('button', { name: '記録する' }))
  await screen.findByRole('button', { name: /保存状態を確認（入力を破棄/ })
  expired = true; fireEvent.focus(window)
  expect(await screen.findByRole('button', { name: 'ログイン' })).toBeVisible()
  expect(screen.getByRole('alert')).toHaveTextContent('ログイン後に記録一覧で保存されたか確認してください。')
  expect(count.writes).toBe(1)
})
it('a direct rejected write uses the normal session-expired notice', async () => {
  mock({ write: () => reply(401, { code: 'AUTH_REQUIRED' }) }); const callbacks = form(); await fill()
  fireEvent.click(screen.getByRole('button', { name: '記録する' }))
  await waitFor(() => { expect(callbacks.identity).toHaveBeenCalledWith(null, 'セッションの有効期限が切れました。ログインしてください。') })
})

it.each(['network', '503'])('keeps an unsent draft editable when focus identity read fails with %s', async mode => {
  let offline = false
  const count = mock({ me: () => {
    if (!offline) return owner
    if (mode === 'network') throw new TypeError('offline')
    return reply(503, { code: 'SERVICE_UNAVAILABLE' })
  } })
  form(); await fill(); fireEvent.change(screen.getByLabelText('メモ'), { target: { value: 'まだ送っていない下書き' } })
  offline = true; fireEvent.focus(window)
  expect(await screen.findByText('ログイン状態を確認できません。時間をおいてもう一度操作してください。')).toBeVisible()
  expect(screen.getByLabelText('メモ')).toBeEnabled()
  expect(screen.getByLabelText('メモ')).toHaveValue('まだ送っていない下書き')
  expect(screen.getByRole('button', { name: '記録する' })).toBeEnabled()
  expect(screen.queryByRole('button', { name: /保存状態を確認（入力を破棄/ })).not.toBeInTheDocument()
  expect(count.writes).toBe(0)
})

it('does not let a late App focus 401 overwrite the screen recovery notice', async () => {
  let expire = false; let meReads = 0
  const pending: ((value: Response) => void)[] = []
  mock({ me: () => {
    meReads++
    return expire ? new Promise<Response>(resolve => { pending.push(resolve) }) : owner
  }, write: () => reply(503, { code: 'SERVICE_UNAVAILABLE' }) })
  location.hash = '#record-new'; render(<App />); await fill()
  const before = meReads; fireEvent.focus(window)
  await waitFor(() => { expect(meReads).toBeGreaterThanOrEqual(before + 2) })
  fireEvent.click(screen.getByRole('button', { name: '記録する' }))
  await screen.findByRole('button', { name: /保存状態を確認（入力を破棄/ })
  expire = true; fireEvent.focus(window)
  await waitFor(() => { expect(pending).toHaveLength(2) })
  const first = pending[0]; const second = pending[1]
  if (!first || !second) throw new Error('Two identity reads are required')
  await act(async () => { first(reply(401, { code: 'AUTH_REQUIRED' })); await Promise.resolve() })
  await screen.findByRole('button', { name: 'ログイン' })
  await act(async () => { second(reply(401, { code: 'AUTH_REQUIRED' })); await Promise.resolve() })
  expect(screen.getByRole('alert')).toHaveTextContent('ログイン後に記録一覧で保存されたか確認してください。')
})
it('keeps the draft when identity preflight fails before any write', async () => {
  let offline = false
  const count = mock({ me: () => offline ? reply(503, { code: 'SERVICE_UNAVAILABLE' }) : owner })
  form(); await fill(); fireEvent.change(screen.getByLabelText('メモ'), { target: { value: '送信前の下書き' } })
  offline = true; fireEvent.click(screen.getByRole('button', { name: '記録する' }))
  await screen.findByText('ログイン状態を確認できません。時間をおいてもう一度操作してください。')
  expect(screen.getByLabelText('メモ')).toBeEnabled(); expect(screen.getByLabelText('メモ')).toHaveValue('送信前の下書き')
  expect(count.writes).toBe(0)
})
