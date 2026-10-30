import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import App from '../App'
import type { Account } from '../auth/api'
import type { Profile } from './types'
import { privateFlags } from './types'

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); location.hash = '' })
const owner: Account = { id: '4990c687-5a30-4a83-beb1-30ec8a65d367', username: 'river_user', display_name: 'River', email: 'river@example.test' }
const other: Account = { id: '5990c687-5a30-4a83-beb1-30ec8a65d367', username: 'other_user', display_name: '別利用者', email: 'other@example.test' }
function profile(account = owner): Profile {
  return { viewer_id: account.id, avatar: null, id: account.id, username: account.username, display_name: account.display_name, bio: '自己紹介', is_owner: true,
    health: { height: null, weight: null, age: null, formula: null, activity: null }, energy: { bmr: null, tdee: null, intake: null }, visibility: privateFlags() }
}
function reply(status: number, data: unknown): Response { return new Response(JSON.stringify(data), { status }) }
function path(input: RequestInfo | URL): string { return typeof input === 'string' ? input : input instanceof URL ? input.href : input.url }
function setup(options: { put?: (init?: RequestInit) => Response | Promise<Response>; get?: (target: string) => Response | Promise<Response>; identity?: () => Account } = {}) {
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = path(input)
    if (url.includes('/posts')) return Promise.resolve(reply(200, { viewer_id: (options.identity?.() ?? owner).id, items: [], next_cursor: null }))
    if (url.endsWith('/csrf')) return Promise.resolve(reply(200, { csrf_token: 'csrf-current' }))
    if (url === '/api/auth/me') return Promise.resolve(reply(200, options.identity?.() ?? owner))
    if (init?.method === 'PUT') return Promise.resolve(options.put?.(init) ?? reply(200, profile()))
    return Promise.resolve(options.get?.(url) ?? reply(200, profile(options.identity?.() ?? owner)))
  }))
}
async function edit() {
  fireEvent.click(await screen.findByRole('link', { name: 'プロフィール' }))
  fireEvent.click(await screen.findByRole('link', { name: 'プロフィールを編集' }))
  await screen.findByRole('button', { name: '変更を保存' })
}
it('opens the authenticated owners profile from home', async () => {
  setup(); render(<App />)
  fireEvent.click(await screen.findByRole('link', { name: 'プロフィール' }))
  expect(await screen.findByText('自己紹介')).toBeVisible()
  expect(screen.getByRole('link', { name: 'プロフィールを編集' })).toBeVisible()
  expect(screen.getAllByText('非公開')).toHaveLength(8)
})
it('renders only the public sparse response and has no editing link', async () => {
  location.hash = '#profile/other_user'
  setup({ get: () => reply(200, { viewer_id: owner.id, avatar: null, id: other.id, username: other.username, display_name: other.display_name, bio: '<img src=x onerror=alert(1)>', is_owner: false, health: {}, energy: { bmr: 1500 } }) })
  render(<App />)
  expect(await screen.findByText('1,500 kcal/日')).toBeVisible()
  expect(screen.queryByText('非公開')).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'プロフィールを編集' })).not.toBeInTheDocument()
  expect(document.querySelector('img')).toBeNull()
  expect(screen.queryByText('体重')).not.toBeInTheDocument()
})
it('previews the half-up vector and sends owner/CSRF headers; updates home name', async () => {
  let saved = profile()
  setup({ put: init => {
    expect(new Headers(init?.headers).get('X-Profile-Owner')).toBe(owner.id)
    expect(new Headers(init?.headers).get('X-CSRFToken')).toBe('csrf-current')
    if (typeof init?.body !== 'string') throw new Error('Expected JSON body')
    const data = JSON.parse(init.body) as Record<string, unknown>
    expect(data).not.toHaveProperty('id')
    saved = { ...profile(), display_name: '新表示名' }
    return reply(200, saved)
  }, get: () => reply(200, saved) })
  render(<App />); await edit()
  fireEvent.change(screen.getByLabelText('表示名'), { target: { value: '新表示名' } })
  fireEvent.change(screen.getByLabelText('身長（cm）'), { target: { value: '170' } })
  fireEvent.change(screen.getByLabelText('体重（kg）'), { target: { value: '60' } })
  fireEvent.change(screen.getByLabelText('年齢（歳）'), { target: { value: '30' } })
  fireEvent.change(screen.getByLabelText('計算式の区分'), { target: { value: 'male' } })
  fireEvent.change(screen.getByLabelText('普段の活動量'), { target: { value: 'medium' } })
  expect(screen.getByText('1,518 kcal/日')).toBeVisible()
  expect(screen.getAllByText('2,656 kcal/日')).toHaveLength(2)
  fireEvent.click(screen.getByRole('button', { name: '変更を保存' }))
  await screen.findByRole('link', { name: 'プロフィールを編集' })
  fireEvent.click(screen.getByRole('link', { name: 'ホーム' }))
  expect(await screen.findByRole('heading', { name: '新表示名さん' })).toBeVisible()
})
it.each([400, 403, 503])('keeps the draft after HTTP %s and never resends the PUT', async status => {
  let puts = 0
  setup({ put: () => { puts++; return reply(status, { code: status === 403 ? 'CSRF_FAILED' : 'VALIDATION_ERROR', message: '固定エラー', fieldErrors: { 'health.height': ['入力を確認してください。'] } }) } })
  render(<App />); await edit()
  fireEvent.change(screen.getByLabelText('自己紹介'), { target: { value: '下書き秘密marker' } })
  fireEvent.click(screen.getByRole('button', { name: '変更を保存' }))
  await screen.findByRole('alert')
  await waitFor(() => { expect(screen.getByRole('button', { name: '変更を保存' })).toBeEnabled() })
  expect(screen.getByLabelText('自己紹介')).toHaveValue('下書き秘密marker')
  expect(puts).toBe(1)
})
it('destroys an old draft when a different actor is detected at save time', async () => {
  let account = owner; let puts = 0
  setup({ identity: () => account, put: () => { puts++; return reply(200, profile(account)) } })
  render(<App />); await edit()
  fireEvent.change(screen.getByLabelText('自己紹介'), { target: { value: '下書き秘密marker' } })
  account = other
  fireEvent.click(screen.getByRole('button', { name: '変更を保存' }))
  expect(await screen.findByRole('heading', { name: '別利用者' })).toBeVisible()
  expect(screen.queryByDisplayValue('下書き秘密marker')).not.toBeInTheDocument()
  expect(puts).toBe(0)
})
it('handles the actor race after me by dropping the draft on server 409', async () => {
  let account = owner
  setup({ identity: () => account, put: init => {
    expect(new Headers(init?.headers).get('X-Profile-Owner')).toBe(owner.id)
    account = other
    return reply(409, { code: 'PROFILE_OWNER_CHANGED', message: '本人が変わりました。' })
  } })
  render(<App />); await edit()
  fireEvent.change(screen.getByLabelText('自己紹介'), { target: { value: '旧本人の下書き' } })
  fireEvent.click(screen.getByRole('button', { name: '変更を保存' }))
  expect(await screen.findByRole('heading', { name: '別利用者' })).toBeVisible()
  expect(screen.queryByDisplayValue('旧本人の下書き')).not.toBeInTheDocument()
})
it('does not erase a draft when recovering saved state fails', async () => {
  let failed = false
  setup({ put: () => { failed = true; return reply(503, { code: 'SERVICE_UNAVAILABLE', message: '結果不明' }) }, get: () => failed ? reply(503, { code: 'SERVICE_UNAVAILABLE', message: '再取得失敗' }) : reply(200, profile()) })
  render(<App />); await edit()
  fireEvent.change(screen.getByLabelText('自己紹介'), { target: { value: '保持する下書き' } })
  fireEvent.click(screen.getByRole('button', { name: '変更を保存' }))
  fireEvent.click(await screen.findByRole('button', { name: '保存状態を読み直す（入力を破棄）' }))
  expect(await screen.findByText('再取得失敗')).toBeVisible()
  expect(screen.getByLabelText('自己紹介')).toHaveValue('保持する下書き')
})

it('discards a delayed owners response after changing the target', async () => {
  let finish: ((value: Response) => void) | undefined
  location.hash = '#profile'
  setup({ get: target => target.endsWith('/me') ? new Promise<Response>(resolve => { finish = resolve }) : reply(200, { ...profile(other), viewer_id: owner.id, is_owner: false, visibility: undefined, health: {}, energy: {} }) })
  render(<App />)
  await waitFor(() => { expect(finish).toBeDefined() })
  act(() => { location.hash = '#profile/other_user'; window.dispatchEvent(new HashChangeEvent('hashchange')) })
  expect(await screen.findByRole('heading', { name: '別利用者' })).toBeVisible()
  await act(async () => { finish?.(reply(200, { ...profile(), display_name: '遅延した秘密名' })); await Promise.resolve() })
  expect(screen.queryByText('遅延した秘密名')).not.toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '別利用者' })).toBeVisible()
})
it('holds the editor during a pending write and navigates after success', async () => {
  let finish: ((value: Response) => void) | undefined
  setup({ put: () => new Promise<Response>(resolve => { finish = resolve }) })
  render(<App />); await edit()
  fireEvent.click(screen.getByRole('button', { name: '変更を保存' }))
  await waitFor(() => { expect(finish).toBeDefined() })
  act(() => { location.hash = '#'; window.dispatchEvent(new HashChangeEvent('hashchange')) })
  await waitFor(() => { expect(location.hash).toBe('#profile-edit') })
  expect(screen.getByRole('button', { name: '保存中…' })).toBeDisabled()
  await act(async () => { finish?.(reply(200, profile())); await Promise.resolve() })
  expect(await screen.findByRole('link', { name: 'プロフィールを編集' })).toBeVisible()
})
it('clears sensitive drafts on expired identity and never stores them in web storage', async () => {
  const stored = vi.spyOn(Storage.prototype, 'setItem')
  setup(); render(<App />); await edit()
  fireEvent.change(screen.getByLabelText('自己紹介'), { target: { value: '消去する秘密下書き' } })
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(reply(401, { code: 'AUTH_REQUIRED', message: 'ログインが必要です。' }))))
  fireEvent.click(screen.getByRole('button', { name: '変更を保存' }))
  expect(await screen.findByRole('button', { name: 'ログイン' })).toBeVisible()
  expect(screen.queryByDisplayValue('消去する秘密下書き')).not.toBeInTheDocument()
  expect(stored).not.toHaveBeenCalled()
})
it('replaces the draft only after an explicit successful saved-state read', async () => {
  let saved = profile()
  setup({ put: () => {
    saved = { ...profile(), bio: 'サーバー保存済み' }
    return reply(503, { code: 'SERVICE_UNAVAILABLE', message: '結果不明' })
  }, get: () => reply(200, saved) })
  render(<App />); await edit()
  fireEvent.change(screen.getByLabelText('自己紹介'), { target: { value: '手元の下書き' } })
  fireEvent.click(screen.getByRole('button', { name: '変更を保存' }))
  const reload = await screen.findByRole('button', { name: '保存状態を読み直す（入力を破棄）' })
  await waitFor(() => { expect(reload).toBeEnabled() })
  expect(screen.getByLabelText('自己紹介')).toHaveValue('手元の下書き')
  fireEvent.click(reload)
  await waitFor(() => { expect(screen.getByLabelText('自己紹介')).toHaveValue('サーバー保存済み') })
})
