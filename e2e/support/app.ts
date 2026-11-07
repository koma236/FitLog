import { expect, type Browser, type BrowserContext, type Locator, type Page, type Response } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { randomBytes } from 'node:crypto'
import { readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { assertLocalUrl, sanitizeAxe, Budget, installLocalRequestGuard, newLocalPage } from './safety.mjs'
import { ORIGIN, isAws, artifact, runId, validateUrl, reserveNative, savePrivate } from './environment.js'
import { installAwsGuard } from './aws-policy.mjs'
export { ORIGIN, artifact, runId } from './environment.js'
import { responseAfter, RecoveryLog } from './recovery.mjs'

export type Actor = { context: BrowserContext; page: Page; username: string; email: string; password: string; name: string; id: string }
export const recoveryLog = new RecoveryLog(rows => writeFileSync(path.join(artifact, 'recovery-observations.json'), JSON.stringify(rows, null, 2)))
export const budget = new Budget({ users: 2, posts: 6, comments: 4, images: 4 }, isAws ? used => savePrivate('resource-budget', used) : undefined)
const authAttempts: number[] = []
const httpObservations: { method: string; operation: string; expected: number; received: number }[] = []
const guardObservations: { code: string; method?: string; observed_at: string }[] = []
export const audit: { screen: string; width: number; overflow_px: number; violations: unknown[]; incomplete: unknown[] }[] = []

/** Rate-limit every UI signup/login, including negative cases, across both actors. */
export async function authSlot() {
  while (authAttempts.filter(time => Date.now() - time < 60_000).length >= 8) {
    const oldest = authAttempts.filter(time => Date.now() - time < 60_000)[0]
    await new Promise(resolve => setTimeout(resolve, Math.max(1, 60_001 - (Date.now() - oldest))))
  }
  authAttempts.push(Date.now())
}

export async function guardedContext(browser: Browser, options: Parameters<Browser['newContext']>[0] = {}) {
  const context = await browser.newContext({ locale: 'ja-JP', timezoneId: 'Asia/Tokyo', viewport: { width: 1280, height: 800 }, serviceWorkers: 'block', ...options })
  context.setDefaultTimeout(10_000)
  context.setDefaultNavigationTimeout(10_000)
  try {
    if (isAws) {
      await installAwsGuard(context, { validate: validateUrl!, reserve: reserveNative })
    } else await installLocalRequestGuard(context)
    return context
  }
  catch { await context.close(); throw new Error('CONTEXT_GUARD_UNAVAILABLE') }
}

export async function makeActor(browser: Browser, suffix: string): Promise<Actor> {
  budget.take('users')
  const context = await guardedContext(browser)
  try {
    return { context, page: await guardedPage(context), username: `fl10a_${runId}_${suffix}`,
      email: `fl10a_${runId}_${suffix}@example.invalid`, password: randomBytes(24).toString('base64url'), name: `検証${suffix.toUpperCase()} ${runId}`, id: '' }
  } catch { await context.close(); throw new Error('ACTOR_PAGE_UNAVAILABLE') }
}

export async function guardedPage(context: BrowserContext): Promise<Page> {
  return newLocalPage(context, event => {
    guardObservations.push({ ...event, observed_at: new Date().toISOString() })
    writeFileSync(path.join(artifact, 'guard-status.json'), JSON.stringify(guardObservations, null, 2))
  })
}

export async function responseFor(page: Page, pathname: string, method: string, action: () => Promise<unknown>, status: number): Promise<Response> {
  const response = await responseAfter(page, pathname, method, action, status, received => {
    httpObservations.push({ method, operation: pathname.startsWith('/api/auth/') ? pathname : '/api/resource', expected: status, received })
    writeFileSync(path.join(artifact, 'http-status.json'), JSON.stringify(httpObservations, null, 2))
  })
  expect(response.status()).toBe(status)
  return response
}

export async function signup(actor: Actor) {
  await actor.page.goto(ORIGIN)
  await actor.page.getByRole('button', { name: '新規登録', exact: true }).click()
  await actor.page.getByLabel('ユーザー名', { exact: true }).fill(actor.username)
  await actor.page.getByLabel('表示名', { exact: true }).fill(actor.name)
  await actor.page.getByLabel('メールアドレス', { exact: true }).fill(actor.email)
  await actor.page.getByLabel('パスワード', { exact: true }).fill(actor.password)
  await authSlot()
  const response = await responseFor(actor.page, '/api/auth/signup', 'POST', () => actor.page.getByRole('button', { name: '登録する', exact: true }).click(), 201)
  actor.id = (await response.json()).id
  await expect(actor.page.getByRole('button', { name: 'ログアウト', exact: true })).toBeVisible()
}

export async function login(actor: Actor, wrong = false) {
  const page = actor.page
  if (await page.getByRole('button', { name: 'ログイン画面へ', exact: true }).isVisible()) await page.getByRole('button', { name: 'ログイン画面へ', exact: true }).click()
  await page.getByLabel('メールアドレス', { exact: true }).fill(actor.email)
  await page.getByLabel('パスワード', { exact: true }).fill(wrong ? 'Different-Invalid-Password-1234' : actor.password)
  await authSlot()
  const response = await responseFor(page, '/api/auth/login', 'POST', () => page.getByRole('button', { name: 'ログイン', exact: true }).click(), wrong ? 401 : 200)
  if (wrong) expect((await response.json()).code).toBe('INVALID_CREDENTIALS')
  else await expect(page.getByRole('button', { name: 'ログアウト', exact: true })).toBeVisible()
}

export async function logout(actor: Actor) {
  await responseFor(actor.page, '/api/auth/logout', 'POST', () => actor.page.getByRole('button', { name: 'ログアウト', exact: true }).click(), 204)
  await expect(actor.page.getByRole('button', { name: 'ログイン', exact: true })).toBeVisible()
}

export async function go(page: Page, hash: string) {
  await page.goto(ORIGIN + '/' + hash)
  await expect(page.getByRole('button', { name: 'ログアウト', exact: true })).toBeVisible()
}

/** Supplemental real API observations stay in the page's own origin/session. */
export async function api(actor: Actor, pathname: string, method = 'GET', data?: unknown, csrf = true) {
  if (isAws) validateUrl!(ORIGIN + pathname)
  else assertLocalUrl(ORIGIN + pathname)
  return actor.page.evaluate(async ({ pathname, method, data, csrf, id }) => {
    const headers: Record<string, string> = { Accept: 'application/json' }
    if (method !== 'GET') {
      headers['X-Record-Owner'] = id; headers['X-Social-Owner'] = id; headers['X-Profile-Owner'] = id
      if (csrf) headers['X-CSRFToken'] = (await (await fetch('/api/auth/csrf')).json()).csrf_token
      if (data !== undefined) headers['Content-Type'] = 'application/json'
    }
    const response = await fetch(pathname, { method, headers, ...(data !== undefined ? { body: JSON.stringify(data) } : {}) })
    const body = response.status === 204 ? null : await response.json()
    return { status: response.status, body }
  }, { pathname, method, data, csrf, id: actor.id })
}

export async function scan(page: Page, screen: string) {
  await page.locator('h1, article.workout-card').first().waitFor()
  await expect(page.getByRole('status').filter({ hasText: /確認中|読み込んでいます|検索中/ })).toHaveCount(0)
  const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const clean = sanitizeAxe(screen, result)
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  audit.push({ ...clean, width: page.viewportSize()!.width, overflow_px: overflow })
  writeFileSync(path.join(artifact, 'accessibility.json'), JSON.stringify(audit, null, 2))
  // E10 enforces accumulated violations, allowing other functional cases to finish.
}

export function imageFixture() {
  return { name: 'fixture.png', mimeType: 'image/png', buffer: readFileSync(path.resolve(import.meta.dirname, '../fixtures/pixels.png')) }
}

export async function fillRecord(page: Page, note: string, sets = 3) {
  await page.getByLabel('トレーニング日', { exact: true }).fill('2026-01-15')
  await page.getByLabel('種目名', { exact: true }).fill('ベンチプレス')
  for (let i = 1; i <= sets; i++) {
    if (i > 1) await page.getByRole('button', { name: /＋ セットを追加/ }).click()
    await page.getByLabel(`種目1 セット${i} 重量（kg）`, { exact: true }).fill('60')
    await page.getByLabel(`種目1 セット${i} 回数`, { exact: true }).fill('10')
  }
  await page.getByLabel('メモ', { exact: true }).fill(note)
}

export async function keyboardTarget(page: Page, target: Locator, activate = false) {
  for (let i = 0; i < 90; i++) {
    if (await target.evaluate(element => document.activeElement === element)) {
      await expect(target).toBeFocused()
      await target.scrollIntoViewIfNeeded()
      const visibleFocus = await target.evaluate(element => {
        const css = getComputedStyle(element)
        return css.outlineStyle !== 'none' && css.outlineWidth !== '0px' || css.boxShadow !== 'none'
      })
      expect(visibleFocus).toBe(true)
      if (activate) await page.keyboard.press('Enter')
      return
    }
    await page.keyboard.press('Tab')
  }
  throw new Error('KEYBOARD_TARGET_UNREACHABLE')
}
