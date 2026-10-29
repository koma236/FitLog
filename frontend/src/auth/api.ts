export type Account = { id: string; username: string; display_name: string; email: string }
export type FieldErrors = Record<string, string[]>

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function account(value: unknown): value is Account {
  return record(value) && Object.keys(value).length === 4
    && ['id', 'username', 'display_name', 'email'].every(key => typeof value[key] === 'string')
}

function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item: unknown) => typeof item === 'string')
}

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public fields: FieldErrors = {}) {
    super(message)
  }
}

async function request(path: string, init?: RequestInit): Promise<unknown> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => { controller.abort() }, 10000)
  try {
    const headers = new Headers(init?.headers)
    headers.set('Accept', 'application/json')
    const response = await fetch(`/api/auth/${path}`, {
      ...init, signal: controller.signal, credentials: 'same-origin', cache: 'no-store',
      headers,
    })
    if (response.status === 204 && path === 'logout') return null
    let body: unknown
    try { body = await response.json() } catch {
      throw new ApiError(response.status, 'INVALID_RESPONSE', '応答を確認できません。時間をおいてログイン状態を確認してください。')
    }
    if (!response.ok) {
      const fields: FieldErrors = {}
      if (record(body) && record(body.fieldErrors)) {
        for (const [key, value] of Object.entries(body.fieldErrors)) {
          if (strings(value)) fields[key] = value
        }
      }
      throw new ApiError(response.status, record(body) && typeof body.code === 'string' ? body.code : '',
        record(body) && typeof body.message === 'string' ? body.message : '処理結果を確認できません。', fields)
    }
    const expected = path === 'logout' ? 204 : path === 'signup' ? 201 : 200
    if (response.status !== expected) throw new ApiError(response.status, 'INVALID_RESPONSE', '応答を確認できません。')
    return body
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError(0, 'NETWORK_ERROR', '接続できません。処理結果が不明な場合はログイン状態を確認してください。')
  } finally { window.clearTimeout(timeout) }
}

export async function getMe(): Promise<Account> {
  const body = await request('me')
  if (!account(body)) throw new ApiError(200, 'INVALID_RESPONSE', '応答を確認できません。')
  return body
}

export async function getCsrf(): Promise<string> {
  const body = await request('csrf')
  if (!record(body) || typeof body.csrf_token !== 'string' || !body.csrf_token) {
    throw new ApiError(200, 'INVALID_RESPONSE', '応答を確認できません。')
  }
  return body.csrf_token
}

export async function submitAuth(
  action: 'login' | 'signup', data: Record<string, string>, csrf: string,
): Promise<Account> {
  const body = await request(action, {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: JSON.stringify(data),
  })
  if (!account(body)) throw new ApiError(200, 'INVALID_RESPONSE', '応答を確認できません。ログイン状態を確認してください。')
  return body
}

export async function signOut(csrf: string): Promise<void> {
  const body = await request('logout', {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: '{}',
  })
  if (body !== null) throw new ApiError(200, 'INVALID_RESPONSE', 'ログアウトの結果を確認できません。')
}
