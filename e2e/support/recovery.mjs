import { expect } from '@playwright/test'
import { ORIGIN } from './safety.mjs'

const stages = new Set(['response', 'network-open', 'network-ready', 'network-offline', 'network-error', 'network-online', 'network-retry', 'network-restored', 'delete-settled', 'session-check', 'case-network', 'case-csrf', 'case-old-session', 'case-cookie-loss', 'postcondition', 'capture-open', 'capture-ready', 'capture-like', 'capture-liked'])
const phases = new Set(['start', 'pass', 'fail', 'observation'])
const kinds = new Set(['auth', 'timeline', 'resource'])
const categories = new Set(['REQUEST_TIMEOUT', 'REQUEST_FAILED', 'PAGE_CLOSED', 'HTTP_STATUS', 'PRECONDITION_FAILED', 'CASE_FAILED', 'LOCATOR_NOT_UNIQUE'])

export function failureCategory(error) {
  if (categories.has(error?.message)) return error.message
  if (typeof error?.message === 'string' && error.message.includes('strict mode violation')) return 'LOCATOR_NOT_UNIQUE'
  if (error?.name === 'TimeoutError') return 'OPERATION_TIMEOUT'
  return 'ASSERTION_OR_OPERATION_FAILED'
}

/** Only fixed enums, generated ordinals, booleans and bounded numbers cross this boundary. */
export class RecoveryLog {
  /** @param {(rows: object[]) => void} persist */
  constructor(persist = () => {}) { this.persist = persist; this.rows = []; this.pages = new WeakMap(); this.pageCount = 0; this.started = performance.now() }
  event(stage, page, actor, phase, details = {}) {
    if (!stages.has(stage) || !phases.has(phase) || !['A', 'B'].includes(actor)) throw new Error('OBSERVATION_INVALID')
    if (!this.pages.has(page)) this.pages.set(page, ++this.pageCount)
    const row = { stage, actor, page: this.pages.get(page), operation: this.rows.length + 1, phase, observed_at: new Date().toISOString(), elapsed_ms: Math.round(performance.now() - this.started) }
    for (const key of ['visible', 'enabled', 'matches', 'online']) if (typeof details[key] === 'boolean') row[key] = details[key]
    for (const key of ['count', 'status']) if (Number.isSafeInteger(details[key]) && details[key] >= 0 && details[key] <= 999) row[key] = details[key]
    if (kinds.has(details.request_kind)) row.request_kind = details.request_kind
    if (['OPERATION_TIMEOUT', 'ASSERTION_OR_OPERATION_FAILED', ...categories].includes(details.failure)) row.failure = details.failure
    this.rows.push(row)
    this.persist(this.rows)
  }
  async stage(stage, page, actor, action) {
    this.event(stage, page, actor, 'start')
    try { const value = await action(); this.event(stage, page, actor, 'pass'); return value }
    catch (error) { this.event(stage, page, actor, 'fail', { failure: failureCategory(error), status: error?.status }); throw error }
  }
}

/** Observe only requests that START after this operation is armed, not stale responses. */
async function requestAfter(page, pathname, method, action, outcome) {
  const requests = new Set()
  let resolve; let reject; let timer
  const pending = new Promise((yes, no) => { resolve = yes; reject = no })
  const started = request => {
    if (request.method() === method && new URL(request.url()).pathname === pathname && request.frame() === page.mainFrame()) requests.add(request)
  }
  const responded = response => { if (requests.has(response.request()) && outcome === 'response') resolve(response) }
  // StrictMode/navigation may abort one mount read and start its replacement.
  // A response wait still requires a new successful response within the same cap.
  const failed = request => { if (requests.has(request) && outcome === 'failure') resolve(request) }
  const closed = () => reject(new Error('PAGE_CLOSED'))
  page.on('request', started); page.on('response', responded); page.on('requestfailed', failed); page.on('close', closed)
  timer = setTimeout(() => reject(new Error('REQUEST_TIMEOUT')), 10_000)
  try {
    const [value] = await Promise.all([pending, Promise.resolve().then(action)])
    return value
  } finally {
    clearTimeout(timer)
    page.off('request', started); page.off('response', responded); page.off('requestfailed', failed); page.off('close', closed)
  }
}

/** @returns {Promise<import('@playwright/test').Response>} */
export async function responseAfter(page, pathname, method, action, status, observed = (_status) => {}) {
  const response = await requestAfter(page, pathname, method, action, 'response')
  observed(response.status())
  if (response.status() !== status) throw Object.assign(new Error('HTTP_STATUS'), { status: response.status() })
  return response
}

/** Capture handoff, shared verbatim with the controlled real-App fixture. */
export async function captureLikeFromFollowing(page, postId, note, log = new RecoveryLog()) {
  const route = '#record/' + postId
  await log.stage('capture-open', page, 'B', async () => {
    const entry = page.getByRole('region', { name: '記録一覧', exact: true }).locator('article.workout-card').filter({ has: page.getByText(note, { exact: true }) })
    const link = entry.getByRole('link', { name: '記録の詳細', exact: true })
    await expect(entry).toHaveCount(1); await expect(link).toHaveAttribute('href', route)
    await responseAfter(page, '/api/posts/' + postId, 'GET', () => link.click(), 200,
      status => log.event('capture-open', page, 'B', 'observation', { request_kind: 'resource', status }))
  })
  const detail = page.locator('.workout-content')
  const card = detail.locator('article.workout-card')
  const like = card.getByRole('button', { name: 'いいね', exact: true })
  await log.stage('capture-ready', page, 'B', async () => {
    await expect.poll(() => page.evaluate(() => location.hash)).toBe(route)
    await expect(page.getByRole('region', { name: '記録一覧', exact: true })).toHaveCount(0)
    await expect(detail).toHaveCount(1); await expect(card).toHaveCount(1)
    await expect(card.getByText(note, { exact: true })).toBeVisible()
    await expect(card.getByRole('link', { name: '記録の詳細', exact: true })).toHaveAttribute('href', route)
    await expect(detail.getByRole('region', { name: 'コメント一覧', exact: true })).toBeVisible()
    await expect(detail.getByRole('textbox', { name: 'コメント本文', exact: true })).toBeEnabled()
    await expect(page.getByRole('status')).toHaveCount(0)
    await expect(page.getByRole('alert')).toHaveCount(0)
    await expect(page.locator('dialog[open]')).toHaveCount(0)
    await expect(like).toHaveCount(1); await expect(like).toBeVisible(); await expect(like).toBeEnabled()
    await expect(like).toHaveAttribute('aria-pressed', 'false')
    await expect(like).toHaveAccessibleDescription('0件')
    log.event('capture-ready', page, 'B', 'observation', { count: await like.count(), visible: true, enabled: true, matches: true })
  })
  await log.stage('capture-like', page, 'B', () => responseAfter(page, '/api/posts/' + postId + '/like', 'POST', () => like.click(), 200,
    status => log.event('capture-like', page, 'B', 'observation', { request_kind: 'resource', status })))
  await log.stage('capture-liked', page, 'B', async () => {
    await expect(like).toHaveCount(1); await expect(like).toBeEnabled()
    await expect(like).toHaveAttribute('aria-pressed', 'true')
    await expect(like).toHaveAccessibleDescription('1件')
    log.event('capture-liked', page, 'B', 'observation', { count: 1, enabled: true, matches: true })
  })
}

export async function sessionMatches(actor, log = new RecoveryLog(), label = 'A') {
  if (actor.page.isClosed()) return false
  try {
    const result = await actor.page.evaluate(async id => {
      const controller = new AbortController()
      const timer = setTimeout(() => controller.abort(), 10_000)
      try {
        const response = await fetch('/api/auth/me', { credentials: 'same-origin', cache: 'no-store', signal: controller.signal })
        return { status: response.status, matches: response.status === 200 && (await response.json()).id === id }
      } finally { clearTimeout(timer) }
    }, actor.id)
    log.event('session-check', actor.page, label, 'observation', { ...result, request_kind: 'auth' })
    return result.matches
  } catch { return false }
}

export async function followingReady(page, note, log = new RecoveryLog()) {
  const feed = page.getByRole('region', { name: '記録一覧', exact: true })
  const button = feed.getByRole('button', { name: '画像と一覧を再読み込み', exact: true })
  await expect.poll(() => page.evaluate(() => ['', '#'].includes(location.hash))).toBe(true)
  await expect(page.getByRole('tab', { name: 'フォロー中', selected: true, exact: true })).toBeVisible()
  await expect(feed).toHaveCount(1)
  await expect(feed.getByText(note, { exact: true })).toBeVisible()
  await expect(page.getByRole('status')).toHaveCount(0)
  await expect(page.getByRole('alert')).toHaveCount(0)
  await expect(page.locator('dialog[open]')).toHaveCount(0)
  await expect(button).toHaveCount(1); await expect(button).toBeVisible(); await expect(button).toBeEnabled()
  log.event('network-ready', page, 'B', 'observation', { count: await button.count(), visible: await button.isVisible(), enabled: await button.isEnabled(), matches: true })
  return button
}

/** Shared by the real journey and the HTTP fixture; never mocks a product response. */
export async function networkRecovery(actor, note, log = new RecoveryLog()) {
  const { page, context } = actor
  try {
    await context.setOffline(false)
    await log.stage('network-open', page, 'B', async () => {
      const response = await responseAfter(page, '/api/timeline/following', 'GET', () => page.goto(ORIGIN + '/#'), 200)
      log.event('network-open', page, 'B', 'observation', { request_kind: 'timeline', status: response.status(), online: true })
    })
    const button = await log.stage('network-ready', page, 'B', async () => {
      if (!await sessionMatches(actor, log, 'B')) throw new Error('PRECONDITION_FAILED')
      try { return await followingReady(page, note, log) }
      catch { throw new Error('PRECONDITION_FAILED') }
    })
    await log.stage('network-offline', page, 'B', async () => {
      await context.setOffline(true)
      await requestAfter(page, '/api/timeline/following', 'GET', () => button.click(), 'failure')
    })
    await log.stage('network-error', page, 'B', async () => {
      await expect(page.getByRole('alert').getByText('記録を読み込めませんでした。', { exact: true })).toBeVisible()
      await expect(page.getByRole('button', { name: 'もう一度読み込む', exact: true })).toBeEnabled()
    })
  } finally {
    // Even a failed precondition, click, observation write or assertion restores networking.
    await context.setOffline(false)
    log.event('network-online', page, 'B', 'observation', { online: true })
  }
  await log.stage('network-retry', page, 'B', async () => {
    const response = await responseAfter(page, '/api/timeline/following', 'GET', () => page.getByRole('button', { name: 'もう一度読み込む', exact: true }).click(), 200)
    log.event('network-retry', page, 'B', 'observation', { request_kind: 'timeline', status: response.status() })
  })
  await log.stage('network-restored', page, 'B', async () => {
    await followingReady(page, note, log)
    await expect(page.getByRole('button', { name: 'もう一度読み込む', exact: true })).toHaveCount(0)
    if (!await sessionMatches(actor, log, 'B')) throw new Error('PRECONDITION_FAILED')
  })
}

export async function deletionSettled(page, log = new RecoveryLog()) {
  await log.stage('delete-settled', page, 'A', async () => {
    await expect(page.locator('dialog[open]')).toHaveCount(0)
    await expect.poll(() => page.evaluate(() => location.hash === '#profile')).toBe(true)
    await expect(page.getByRole('button', { name: 'ログアウト', exact: true })).toBeEnabled()
  })
}

export const RECOVERY_IDS = ['network', 'csrf', 'old-session', 'cookie-loss']
export function recoveryRows() { return RECOVERY_IDS.map(id => ({ id, status: 'not_run', reason: 'PRECONDITION_NOT_REACHED' })) }

/** Independent cases proceed only after their own current precondition is verified. */
export async function recoveryCases(cases, rows, save) {
  for (const row of rows) {
    const candidate = cases[row.id]
    let ready = false
    try { ready = await candidate.ready() } catch { /* Unknown state is not readiness. */ }
    if (!ready) { save(); continue }
    row.status = 'fail'; row.reason = 'INTERRUPTED'; row.started = new Date().toISOString(); save()
    try { await candidate.action(); row.status = 'pass'; row.reason = null }
    catch { row.reason = 'ASSERTION_OR_OPERATION_FAILED' }
    finally { row.finished = new Date().toISOString(); save() }
  }
  return rows.every(row => row.status === 'pass')
}
