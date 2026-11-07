/** HTTPS destination and pre-send limits, shared by CDP and APIRequestContext. */
import { installLocalRequestGuard } from './safety.mjs'

export async function installAwsGuard(context, policy) {
  await context.routeWebSocket('**/*', socket => socket.close())
  await context.addInitScript(() => {
    const denied = function () { throw Error('WORKER_BLOCKED') }
    Object.defineProperty(globalThis, 'Worker', { value: denied, configurable: false, writable: false })
    Object.defineProperty(globalThis, 'SharedWorker', { value: denied, configurable: false, writable: false })
  })
  await installLocalRequestGuard(context, policy)
}

export function nativeBodyBytes(request) {
  if (!request.hasPostData) return 0
  if (!request.postDataEntries?.length || request.postDataEntries.some(entry => typeof entry.bytes !== 'string')) throw Error('BODY_SIZE_UNKNOWN')
  return request.postDataEntries.reduce((sum, entry) => sum + Buffer.from(entry.bytes, 'base64').length, 0)
}

export function urlPolicy(origin) {
  if (!/^https:\/\/[a-z0-9]{1,63}\.cloudfront\.net$/.test(origin)) throw Error('ORIGIN_BLOCKED')
  return value => {
    if (typeof value !== 'string') throw Error('ORIGIN_BLOCKED')
    if (value.startsWith('data:image/')) return
    if (value.startsWith('blob:')) { value = value.slice(5) }
    // Test raw authority too: URL normalizes default ports, userinfo and dots.
    const match = /^(https:\/\/[^/?#]+)(?:[/?#]|$)/.exec(value)
    if (!match || match[1] !== origin || /[\\\r\n]/.test(value)) throw Error('ORIGIN_BLOCKED')
    const url = new URL(value)
    if (url.origin !== origin || url.username || url.password) throw Error('ORIGIN_BLOCKED')
  }
}

export class SendBudget {
  constructor({ expires, now = Date.now, persist }) {
    this.expires = expires; this.now = now; this.persist = persist
    this.started = performance.now(); this.limitMs = expires - now()
    this.state = { requests: 0, bytes: 0, auth: 0, auth_times: [], cleanup: false, failed: false }
  }
  check() {
    const reserved = this.state.cleanup ? 0 : 300000
    if (this.now() >= this.expires - reserved || performance.now() - this.started >= this.limitMs - reserved) throw Error('DEADLINE')
    if (this.state.failed) throw Error('BUDGET_WRITE_FAILED')
  }
  cleanup() { this.state.cleanup = true }
  take(method, url, bytes = 0) {
    this.check()
    const s = this.state; const now = this.now()
    if (s.requests >= (s.cleanup ? 3000 : 2800)) throw Error('REQUEST_LIMIT')
    if (!Number.isSafeInteger(bytes) || bytes < 0 || s.bytes + bytes > 20 * 1024 * 1024) throw Error('BODY_LIMIT')
    const auth = method === 'POST' && /\/api\/auth\/(login|signup)(?:[?#]|$)/.test(url)
    s.auth_times = s.auth_times.filter(t => now - t < 60000)
    if (auth && (s.auth >= 24 || s.auth_times.length >= 8)) throw Error('AUTH_LIMIT')
    s.requests++; s.bytes += bytes
    if (auth) { s.auth++; s.auth_times.push(now) }
    try { this.persist(structuredClone(s)) }
    catch { s.failed = true; throw Error('BUDGET_WRITE_FAILED') }
  }
}

export async function apiSend(request, policy, pathname, options = {}) {
  if (!/^\/api\/[A-Za-z0-9_/?=&%.-]+$/.test(pathname) || pathname.includes('..') || /%2[ef]/i.test(pathname)) throw Error('API_PATH_BLOCKED')
  const url = policy.origin + pathname
  urlPolicy(policy.origin)(url)
  const { method = 'GET', headers = {}, data } = options
  const raw = data === undefined ? undefined : typeof data === 'string' || Buffer.isBuffer(data) ? data : JSON.stringify(data)
  policy.budget.take(method, url, raw === undefined ? 0 : Buffer.byteLength(raw))
  try {
    const response = await request.fetch(url, { method, headers: { Origin: policy.origin, ...headers }, ...(raw === undefined ? {} : { data: raw }),
      maxRedirects: 0, maxRetries: 0, ignoreHTTPSErrors: false, timeout: 5000 })
    if (response.status() >= 300 && response.status() < 400) throw Error('REDIRECT_BLOCKED')
    return response
  } catch {
    await request.dispose().catch(() => {})
    throw Error('API_SEND_FAILED')
  }
}
