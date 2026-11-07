export const ORIGIN = 'http://127.0.0.1:15173'
export const STEP_IDS = ['E01', 'E02', 'E03', 'E04', 'E05', 'E06', 'E07', 'E08', 'E09', 'E10']

/** Validate every destination, including redirects, without reflecting the URL. */
export function assertLocalUrl(value) {
  try {
    const url = new URL(value)
    if (url.protocol === 'data:') return
    if (url.protocol === 'blob:') return assertLocalUrl(url.pathname)
    if (url.origin === ORIGIN && url.protocol === 'http:' && !url.username && !url.password) return
  } catch { /* Invalid destinations share the fixed failure below. */ }
  throw new Error('ORIGIN_BLOCKED')
}
export function assertQuietEnvironment(env) {
  if (['DEBUG', 'PWDEBUG', 'NODE_DEBUG'].some(key => env[key])) throw new Error('VERBOSE_BLOCKED')
}

/** Chromium enforces this policy on redirect hops that Playwright does not route. */
const localPageGuards = new WeakMap()
export async function installLocalRequestGuard(context) {
  const pages = new WeakMap()
  localPageGuards.set(context, pages)
  await context.route('**/*', async route => {
    try {
      assertLocalUrl(route.request().url())
      const page = route.request().frame().page()
      if (pages.get(page)?.healthy !== true) throw new Error('PAGE_GUARD_REQUIRED')
    } catch {
      // Never fall back to route.continue when the native policy is unavailable.
      await route.abort('blockedbyclient')
      return
    }
    await route.continue()
  })
}
/**
 * @param {import('@playwright/test').BrowserContext} context
 * @param {(event: {code: string, method?: string}) => void} [observe]
 */
export async function newLocalPage(context, observe = () => {}) {
  const pages = localPageGuards.get(context)
  if (!pages) throw new Error('CONTEXT_GUARD_REQUIRED')
  const page = await context.newPage()
  let stopPage
  try {
    // Install on the blank page before navigation; routing skips redirect hops.
    const session = await context.newCDPSession(page)
    const state = { healthy: true, stopping: null }
    stopPage = () => {
      // Invalidate synchronously: no later initial request may use this page.
      state.healthy = false
      // Register the promise before close can emit another close notification.
      state.stopping ??= Promise.resolve().then(() => page.close()).catch(() => context.close()).then(() => true, () => false)
      return state.stopping
    }
    const notify = event => {
      try { observe(event) }
      catch { void stopPage() }
    }
    session.on('close', () => {
      const stopped = stopPage()
      notify({ code: 'SESSION_CLOSED' })
      return stopped
    })
    session.on('Fetch.requestPaused', async event => {
      let method; let parameters
      try {
        if (!state.healthy) throw new Error('NATIVE_GUARD_LOST')
        assertLocalUrl(event.request.url)
        // Reject forbidden Location values before Chromium follows/normalizes them.
        if (event.responseStatusCode >= 300 && event.responseStatusCode < 400) {
          for (const header of event.responseHeaders ?? []) {
            if (header.name.toLowerCase() === 'location') assertLocalUrl(new URL(header.value, event.request.url).href)
          }
        }
        if (event.responseErrorReason) {
          method = 'Fetch.failRequest'; parameters = { requestId: event.requestId, errorReason: 'Failed' }
        } else {
          method = event.responseStatusCode === undefined ? 'Fetch.continueRequest' : 'Fetch.continueResponse'
          parameters = { requestId: event.requestId }
        }
      } catch {
        method = 'Fetch.failRequest'; parameters = { requestId: event.requestId, errorReason: 'BlockedByClient' }
      }
      try { await session.send(method, parameters) }
      catch (error) {
        // Aborting a fetch/navigation removes its interception before this send
        // can complete. It has no request left to release and loses no guard.
        if (/Invalid [Ii]nterception[Ii]d\.?$/.test(typeof error?.message === 'string' ? error.message : '')) {
          notify({ code: 'REQUEST_ALREADY_FINISHED', method })
        } else {
          notify({ code: 'PROTOCOL_FAILURE', method })
          await stopPage()
        }
      }
    })
    await session.send('Fetch.enable', { patterns: [{ urlPattern: '*', requestStage: 'Request' }, { urlPattern: '*', requestStage: 'Response' }] })
    if (!state.healthy) throw new Error('NATIVE_GUARD_LOST')
    pages.set(page, state)
    return page
  } catch {
    if (stopPage) await stopPage()
    else await page.close()
    throw new Error('NATIVE_GUARD_UNAVAILABLE')
  }
}

/** Export counts only: axe nodes can contain DOM values, capabilities and email. */
export function sanitizeAxe(screen, result) {
  return {
    screen,
    violations: result.violations.map(item => ({ rule: item.id, impact: item.impact, count: item.nodes.length })),
    incomplete: result.incomplete.map(item => ({ rule: item.id, count: item.nodes.length })),
  }
}
export function sanitizeFailure(error) {
  const stack = typeof error?.stack === 'string' ? error.stack : ''
  const match = stack.match(/\/(journey\.spec\.ts):(\d+):(\d+)/) ?? stack.match(/\/(app\.ts):(\d+):(\d+)/)
  return match ? { source: match[1], line: Number(match[2]), column: Number(match[3]) } : { source: 'unknown', line: null, column: null }
}
export function captureSearchAllowed(expected, query, items) {
  return query === expected.username && Array.isArray(items) && items.length === 1 && items[0]?.id === expected.id
}
/** W3C H102 permits browser chrome, but never a background page control. */
export function modalFocusContained(dialog) {
  const doc = dialog.ownerDocument
  return dialog.matches(':modal') && (dialog.contains(doc.activeElement) || (!doc.hasFocus() && doc.activeElement === doc.body))
}
export async function withinDeadline(action, timeout, cancel) {
  let timer
  let timedOut = false
  try {
    return await Promise.race([
      Promise.resolve().then(action),
      new Promise((_, reject) => { timer = setTimeout(() => { timedOut = true; reject(new Error('CASE_TIMEOUT')) }, timeout) }),
    ])
  } catch (error) {
    if (timedOut) await cancel()
    throw error
  } finally { clearTimeout(timer) }
}
/** Own late-created resources as well as already-created ones during cancellation. */
export class CancellationScope {
  constructor() { this.controller = new AbortController(); this.resources = new Map() }
  check() { if (this.controller.signal.aborted) throw new Error('CAPTURE_CANCELLED') }
  async step(action) { this.check(); const value = await action(); this.check(); return value }
  close(resource) {
    const state = this.resources.get(resource)
    state.closing ??= Promise.resolve().then(() => resource.close())
    return state.closing
  }
  async using(factory, action) {
    this.check()
    let resource
    try {
      resource = await factory()
      this.resources.set(resource, { closing: null })
      this.check()
      const value = await action(resource)
      this.check()
      return value
    } finally {
      if (resource) { try { await this.close(resource) } finally { this.resources.delete(resource) } }
    }
  }
  async cancel() {
    this.controller.abort()
    await Promise.allSettled([...this.resources.keys()].map(resource => this.close(resource)))
  }
}
export async function withinCancellableDeadline(action, timeout) {
  const scope = new CancellationScope()
  const work = Promise.resolve().then(() => action(scope))
  return withinDeadline(() => work, timeout, async () => {
    await scope.cancel()
    // Cancellation is not complete until late factories and their finally blocks settle.
    // The original error is secondary to CASE_TIMEOUT, which remains the result.
    await work.catch(() => {})
  })
}
export class ResultLedger {
  constructor(ids) { this.entries = new Map(ids.map(id => [id, { id, status: 'not_run', reason: 'PRECONDITION_NOT_REACHED' }])) }
  start(id) {
    if (!this.entries.has(id)) throw new Error('UNKNOWN_STEP')
    this.entries.set(id, { id, status: 'fail', reason: 'INTERRUPTED', started: new Date().toISOString() })
  }
  finish(id, passed, _error = undefined) {
    if (!this.entries.has(id)) throw new Error('UNKNOWN_STEP')
    if (!this.entries.get(id).started || this.entries.get(id).finished) throw new Error('STEP_NOT_RUNNING')
    this.entries.set(id, { ...this.entries.get(id), status: passed ? 'pass' : 'fail', reason: passed ? null : 'ASSERTION_OR_OPERATION_FAILED', finished: new Date().toISOString() })
  }
  get success() { return this.rows().every(row => row.status === 'pass') }
  rows() { return [...this.entries.values()] }
}
export class Budget {
  constructor(limits) { this.limits = limits; this.used = {} }
  take(kind) {
    if (!Object.hasOwn(this.limits, kind) || (this.used[kind] ?? 0) >= this.limits[kind]) throw new Error('RESOURCE_LIMIT')
    this.used[kind] = (this.used[kind] ?? 0) + 1
  }
}
