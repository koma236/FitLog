import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

function requestPath(input: RequestInfo | URL): string {
  return typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
}

afterEach(() => { cleanup(); vi.unstubAllGlobals() })
beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
    const path = requestPath(input)
    if (path.endsWith('/me')) return Promise.resolve(new Response(JSON.stringify({ code: 'AUTH_REQUIRED', message: 'ログインが必要です。' }), { status: 401 }))
    if (path.endsWith('/csrf')) return Promise.resolve(new Response(JSON.stringify({ csrf_token: 'test-csrf-token' }), { status: 200 }))
    return Promise.resolve(new Response(JSON.stringify({ code: 'INVALID_CREDENTIALS', message: '認証情報を確認してください。' }), { status: 401 }))
  }))
})

describe('approved minimal authentication', () => {
  it('shows email/password login after an anonymous me response', async () => {
    render(<App />)
    expect(await screen.findByLabelText('メールアドレス')).toBeVisible()
    expect(screen.getByLabelText('パスワード')).toBeVisible()
    expect(screen.getByRole('button', { name: 'ログイン' })).toBeEnabled()
    expect(screen.queryByText('モック利用者')).not.toBeInTheDocument()
  })

  it('keeps the login screen when the server rejects credentials', async () => {
    render(<App />)
    fireEvent.change(await screen.findByLabelText('メールアドレス'), { target: { value: 'river@example.test' } })
    fireEvent.change(screen.getByLabelText('パスワード'), { target: { value: 'incorrect-password-42' } })
    fireEvent.click(screen.getByRole('button', { name: 'ログイン' }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('認証情報を確認してください。'))
    expect(screen.getByRole('button', { name: 'ログイン' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'ログアウト' })).not.toBeInTheDocument()
  })
})

const account = { id: '4990c687-5a30-4a83-beb1-30ec8a65d367', username: 'river_user', display_name: '川', email: 'river@example.test' }
function reply(status: number, data: unknown): Response {
  return new Response(status === 204 ? null : JSON.stringify(data), { status })
}
async function fillLogin() {
  fireEvent.change(await screen.findByLabelText('メールアドレス'), { target: { value: account.email } })
  fireEvent.change(screen.getByLabelText('パスワード'), { target: { value: 'River-lantern-42!pine' } })
}

it('restores account from me and logs out using the fetched CSRF token', async () => {
  let logoutCalls = 0
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = requestPath(input)
    if (path.endsWith('/csrf')) return Promise.resolve(reply(200, { csrf_token: 'masked-csrf' }))
    if (path.endsWith('/logout')) {
      logoutCalls++
      expect(new Headers(init?.headers).get('X-CSRFToken')).toBe('masked-csrf')
      return Promise.resolve(reply(204, null))
    }
    return Promise.resolve(reply(200, account))
  }))
  render(<App />)
  expect(await screen.findByRole('heading', { name: '川さん' })).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'ログアウト' }))
  expect(await screen.findByRole('button', { name: 'ログイン' })).toBeVisible()
  expect(logoutCalls).toBe(1)
})

it('registers using only the four approved fields and shows the returned account', async () => {
  let sent: unknown
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = requestPath(input)
    if (path.endsWith('/me')) return Promise.resolve(reply(401, { code: 'AUTH_REQUIRED' }))
    if (path.endsWith('/csrf')) return Promise.resolve(reply(200, { csrf_token: 'csrf' }))
    sent = typeof init?.body === 'string' ? JSON.parse(init.body) as unknown : null
    return Promise.resolve(reply(201, account))
  }))
  render(<App />)
  fireEvent.click(await screen.findByRole('button', { name: '新規登録' }))
  fireEvent.change(screen.getByLabelText('ユーザー名'), { target: { value: 'river_user' } })
  fireEvent.change(screen.getByLabelText('表示名'), { target: { value: '川' } })
  await fillLogin()
  fireEvent.click(screen.getByRole('button', { name: '登録する' }))
  expect(await screen.findByRole('heading', { name: '川さん' })).toBeVisible()
  expect(sent).toEqual({ username: 'river_user', display_name: '川', email: account.email, password: 'River-lantern-42!pine' })
})

it.each([400, 401, 429, 503])('keeps input and never shows home after HTTP %s', async status => {
  let posts = 0
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
    const path = requestPath(input)
    if (path.endsWith('/me')) return Promise.resolve(reply(401, { code: 'AUTH_REQUIRED' }))
    if (path.endsWith('/csrf')) return Promise.resolve(reply(200, { csrf_token: 'csrf' }))
    posts++
    return Promise.resolve(reply(status, { code: 'FAILURE', message: '操作を確認してください。', fieldErrors: { email: ['メールを確認してください。'] } }))
  }))
  render(<App />); await fillLogin()
  fireEvent.click(screen.getByRole('button', { name: 'ログイン' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('操作を確認してください。')
  expect(screen.getByLabelText('メールアドレス')).toHaveValue(account.email)
  expect(screen.getByLabelText('メールアドレス')).toHaveAttribute('aria-invalid', 'true')
  expect(screen.queryByRole('button', { name: 'ログアウト' })).not.toBeInTheDocument()
  expect(posts).toBe(1)
})

it('refreshes CSRF once on 403, retains input and waits for a new click', async () => {
  let csrfCalls = 0; let posts = 0
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
    const path = requestPath(input)
    if (path.endsWith('/me')) return Promise.resolve(reply(401, { code: 'AUTH_REQUIRED' }))
    if (path.endsWith('/csrf')) { csrfCalls++; return Promise.resolve(reply(200, { csrf_token: `csrf-${String(csrfCalls)}` })) }
    posts++
    return Promise.resolve(reply(403, { code: 'CSRF_FAILED', message: '再送してください。' }))
  }))
  render(<App />); await fillLogin()
  fireEvent.click(screen.getByRole('button', { name: 'ログイン' }))
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('安全性の確認を更新しました。'))
  expect(csrfCalls).toBe(2); expect(posts).toBe(1)
  expect(screen.getByLabelText('パスワード')).toHaveValue('River-lantern-42!pine')
})

it.each([200, 401])('checks me after ALREADY_AUTHENTICATED and follows HTTP %s', async status => {
  let meCalls = 0
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
    const path = requestPath(input)
    if (path.endsWith('/me')) {
      meCalls++
      return Promise.resolve(meCalls === 1 || status === 401 ? reply(401, { code: 'AUTH_REQUIRED' }) : reply(200, account))
    }
    if (path.endsWith('/csrf')) return Promise.resolve(reply(200, { csrf_token: 'csrf' }))
    return Promise.resolve(reply(409, { code: 'ALREADY_AUTHENTICATED', message: 'すでにログインしています。' }))
  }))
  render(<App />); await fillLogin()
  fireEvent.click(screen.getByRole('button', { name: 'ログイン' }))
  await waitFor(() => { expect(meCalls).toBe(2) })
  if (status === 200) expect(await screen.findByRole('button', { name: 'ログアウト' })).toBeVisible()
  else expect(await screen.findByRole('button', { name: 'ログイン' })).toBeVisible()
})

it('blocks duplicate submissions until the original request settles', async () => {
  let finish: ((response: Response) => void) | undefined
  let posts = 0
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
    const path = requestPath(input)
    if (path.endsWith('/me')) return Promise.resolve(reply(401, { code: 'AUTH_REQUIRED' }))
    if (path.endsWith('/csrf')) return Promise.resolve(reply(200, { csrf_token: 'csrf' }))
    posts++
    return new Promise<Response>(resolve => { finish = resolve })
  }))
  render(<App />); await fillLogin()
  const button = screen.getByRole('button', { name: 'ログイン' })
  fireEvent.click(button); fireEvent.click(button)
  await waitFor(() => { expect(posts).toBe(1) })
  expect(screen.getByRole('button', { name: '送信中…' })).toBeDisabled()
  finish?.(reply(401, { code: 'INVALID_CREDENTIALS', message: '認証情報を確認してください。' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('認証情報を確認してください。')
})

it.each(['network', 'non-json'])('shows %s failure without retrying the POST', async failure => {
  let posts = 0
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
    const path = requestPath(input)
    if (path.endsWith('/me')) return Promise.resolve(reply(401, { code: 'AUTH_REQUIRED' }))
    if (path.endsWith('/csrf')) return Promise.resolve(reply(200, { csrf_token: 'csrf' }))
    posts++
    return failure === 'network' ? Promise.reject(new TypeError('network')) : Promise.resolve(new Response('invalid', { status: 503 }))
  }))
  render(<App />); await fillLogin()
  fireEvent.click(screen.getByRole('button', { name: 'ログイン' }))
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(posts).toBe(1)
  expect(screen.queryByRole('button', { name: 'ログアウト' })).not.toBeInTheDocument()
})

it('returns to login when focus detects expiry and safely renders a display name', async () => {
  let meCalls = 0
  const display = '<img src=x onerror=alert(1)>'
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
    if (requestPath(input).endsWith('/csrf')) return Promise.resolve(reply(200, { csrf_token: 'csrf' }))
    meCalls++
    return Promise.resolve(meCalls === 1 ? reply(200, { ...account, display_name: display }) : reply(401, { code: 'AUTH_REQUIRED' }))
  }))
  const { container } = render(<App />)
  expect(await screen.findByRole('heading', { name: `${display}さん` })).toBeVisible()
  expect(container.querySelector('img')).toBeNull()
  fireEvent.focus(window)
  expect(await screen.findByRole('button', { name: 'ログイン' })).toBeVisible()
  expect(screen.getByRole('alert')).toHaveTextContent('セッションの有効期限が切れました。')
})

it('does not authenticate from an unexpected success status or account shape', async () => {
  let posts = 0
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
    const path = requestPath(input)
    if (path.endsWith('/me')) return Promise.resolve(reply(401, { code: 'AUTH_REQUIRED' }))
    if (path.endsWith('/csrf')) return Promise.resolve(reply(200, { csrf_token: 'csrf' }))
    posts++
    return Promise.resolve(posts === 1 ? reply(201, account) : reply(200, { ...account, is_staff: true }))
  }))
  render(<App />); await fillLogin()
  fireEvent.click(screen.getByRole('button', { name: 'ログイン' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('応答を確認できません。')
  await waitFor(() => { expect(screen.getByRole('button', { name: 'ログイン' })).toBeEnabled() })
  fireEvent.click(screen.getByRole('button', { name: 'ログイン' }))
  await waitFor(() => { expect(posts).toBe(2) })
  expect(screen.queryByRole('button', { name: 'ログアウト' })).not.toBeInTheDocument()
})
