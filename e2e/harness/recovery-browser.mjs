import { createServer } from 'node:http'
import { readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { build } from '../.artifacts/frontend-deps/node_modules/esbuild/lib/main.js'
import { chromium, expect } from '@playwright/test'
import { installLocalRequestGuard, newLocalPage, ORIGIN } from '../support/safety.mjs'
import { networkRecovery, followingReady, deletionSettled, responseAfter, RecoveryLog, failureCategory } from '../support/recovery.mjs'

const run = process.env.FITLOG_RECOVERY_FIXTURE_RUN
const owner = JSON.parse(readFileSync('/Users/saki/project/FitLog/.git/fitlog-runtime.lock/owner.json', 'utf8'))
if (!run || owner.run_id !== run || !run.startsWith('recovery-fixture-')) throw new Error('FIXTURE_RUNNER_REQUIRED')
process.kill(owner.pid, 0)
const output = new URL('../.artifacts/' + run + '/', import.meta.url)
// Hand-written OpenAPI Account/PostPage/Profile fixtures; no product data or writes.
const account = { id: '11111111-1111-4111-8111-111111111111', username: 'fixture', display_name: 'Fixture', email: 'fixture@example.invalid' }
const post = { id: '22222222-2222-4222-8222-222222222222', viewer_id: account.id, author: { id: account.id, username: 'fixture', display_name: 'Fixture', avatar: null }, is_owner: true, performed_on: '2026-01-15', note: 'controlled record', created_at: '2026-01-15T00:00:00Z', updated_at: '2026-01-15T00:00:00Z', exercises: [{ name: 'Bench', sets: [{ weight_kg: '60.00', reps: 10 }] }], energy: null, energy_input: { minutes: null, kind: null }, visibility: { minutes: 'private', kind: 'private' }, image: null, like_count: 0, comment_count: 0, is_liked: false }
const profile = { id: account.id, username: account.username, display_name: account.display_name, viewer_id: account.id, avatar: null, bio: '', is_owner: true, is_following: false, follower_count: 0, following_count: 0, health: { height: null, weight: null, age: null, formula: null, activity: null }, energy: { bmr: null, tdee: null, intake: null }, visibility: { height: 'private', weight: 'private', age: 'private', formula: 'private', activity: 'private', bmr: 'private', tdee: 'private', intake: 'private' } }
const bundle = await build({ entryPoints: [new URL('recovery-app.tsx', import.meta.url).pathname], bundle: true, write: false, format: 'iife', jsx: 'automatic', alias: { react: path.resolve('e2e/.artifacts/frontend-deps/node_modules/react'), 'react-dom': path.resolve('e2e/.artifacts/frontend-deps/node_modules/react-dom') }, define: { 'process.env.NODE_ENV': '"test"' } })
let mode = 'normal'; let releases = []; let waiters = new Map(); let imageFailed = false
let browser; let passed = false; let stage = 'start'
const rows = []; const observations = {}; const diagnostics = []
const notify = name => { waiters.get(name)?.(); waiters.delete(name) }
const signal = name => new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error('REQUEST_TIMEOUT')), 10_000)
  waiters.set(name, () => { clearTimeout(timer); resolve() })
})
const json = (response, value, status = 200) => { response.writeHead(status, { 'Content-Type': 'application/json' }); response.end(JSON.stringify(value)) }
const pageValue = () => ({ viewer_id: account.id, items: [post], next_cursor: null })
const server = createServer((request, response) => {
  if (request.url === '/fixture.css') { response.writeHead(200, { 'Content-Type': 'text/css' }); response.end(readFileSync(new URL('../../frontend/src/style.css', import.meta.url))); return }
  if (request.url === '/fixture.js') { response.writeHead(200, { 'Content-Type': 'text/javascript' }); response.end(bundle.outputFiles[0].text); return }
  if (request.url === '/api/auth/me') return json(response, account)
  if (request.url === '/api/auth/csrf') return json(response, { csrf_token: 'synthetic' })
  if (request.url === '/api/users/me') return json(response, profile)
  if (request.url === '/api/users/fixture/posts') return json(response, pageValue())
  if (request.url === '/api/posts/' + post.id + '/comments') return json(response, { viewer_id: account.id, post_id: post.id, comment_count: 0, items: [], next_cursor: null })
  if (request.url === '/api/posts/' + post.id) {
    if (request.method === 'DELETE') { response.writeHead(204); response.end(); return }
    return json(response, post)
  }
  if (request.url === '/api/timeline/following') {
    const value = pageValue()
    if (mode === 'image-error') {
      if (imageFailed) return json(response, { viewer_id: account.id, items: [], next_cursor: null })
      value.items = [{ ...post, image: { id: post.id, url: '/broken-image', expires_at: '2030-01-01T00:00:00Z', width: 2, height: 2, content_type: 'image/png' } }]
    }
    if (mode === 'bad-status') return json(response, { code: 'SERVICE_UNAVAILABLE', message: 'SECRET' }, 503)
    if (mode === 'unauthorized') return json(response, { code: 'AUTH_REQUIRED', message: 'SECRET' }, 401)
    if (mode === 'bad-body') return json(response, { SECRET: true })
    if (['held', 'body-held', 'stale'].includes(mode)) {
      const bodyOnly = mode === 'body-held'
      if (bodyOnly) { response.writeHead(200, { 'Content-Type': 'application/json' }); response.flushHeaders() }
      let ended = false
      releases.push(() => { if (ended || response.destroyed) return; ended = true; bodyOnly ? response.end(JSON.stringify(value)) : json(response, value) })
      notify('timeline')
      return
    }
    return json(response, value)
  }
  if (request.url === '/broken-image') { imageFailed = true; response.writeHead(404); response.end(); return }
  if (request.url?.startsWith('/api/')) { response.writeHead(404); response.end(); return }
  response.writeHead(200, { 'Content-Type': 'text/html' }); response.end('<!doctype html><link rel="stylesheet" href="/fixture.css"><div id="root"></div><script src="/fixture.js"></script>')
})
const listen = () => new Promise((resolve, reject) => { server.once('error', reject); server.listen(15173, '127.0.0.1', resolve) })
const close = () => server.listening ? new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve())) : Promise.resolve()
const settleFrames = page => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
async function scenario(id, action) {
  stage = id; mode = 'normal'; imageFailed = false; releases = []; waiters = new Map()
  const context = await browser.newContext({ serviceWorkers: 'block' })
  context.setDefaultTimeout(10_000); context.setDefaultNavigationTimeout(10_000)
  await installLocalRequestGuard(context)
  const page = await newLocalPage(context)
  const actor = { context, page, ...account }
  const log = new RecoveryLog(values => {
    diagnostics.push({ case_id: id, observation: values.at(-1) })
    writeFileSync(new URL('observations.json', output), JSON.stringify(diagnostics))
  })
  let offline = false; let offlineCalls = 0
  const nativeOffline = context.setOffline.bind(context)
  context.setOffline = async value => { if (value) offlineCalls++; await nativeOffline(value); offline = value }
  try {
    await action({ actor, page, context, log, offline: () => offline, offlineCalls: () => offlineCalls })
    rows.push({ id, status: 'pass' })
  } finally {
    for (const release of releases) release()
    await context.close()
  }
}
try {
  await listen(); browser = await chromium.launch()
  for (const heldMode of ['held', 'body-held']) await scenario(heldMode, async ({ actor, page, log, offlineCalls }) => {
    mode = heldMode
    const seen = signal('timeline')
    const task = networkRecovery(actor, post.note, log).then(() => null, error => error)
    await seen
    await expect(page.getByRole('button', { name: 'ログアウト', exact: true })).toBeVisible()
    await settleFrames(page)
    observations[heldMode + '_offline_before_release'] = offlineCalls()
    observations[heldMode + '_button_before_release'] = await page.getByRole('button', { name: '画像と一覧を再読み込み', exact: true }).count()
    expect(offlineCalls()).toBe(0); expect(observations[heldMode + '_button_before_release']).toBe(0)
    if (heldMode === 'body-held') await expect.poll(() => log.rows.some(row => row.stage === 'network-ready' && row.phase === 'start')).toBe(true)
    mode = 'normal'
    for (const release of releases) release()
    expect(await task).toBeNull(); expect(offlineCalls()).toBe(1)
  })
  for (const invalid of ['bad-status', 'bad-body', 'unauthorized']) await scenario(invalid, async ({ actor, log, offlineCalls, offline }) => {
    mode = invalid
    let error
    try { await networkRecovery(actor, post.note, log) } catch (cause) { error = cause }
    expect(Boolean(error)).toBe(true); expect(offlineCalls()).toBe(0); expect(offline()).toBe(false)
    expect(log.rows.some(row => row.stage === 'network-offline')).toBe(false)
  })
  await scenario('wrong-session', async ({ actor, log, offlineCalls, offline }) => {
    let error
    try { await networkRecovery({ ...actor, id: post.id }, post.note, log) } catch (cause) { error = cause }
    expect(Boolean(error)).toBe(true); expect(offlineCalls()).toBe(0); expect(offline()).toBe(false)
    expect(log.rows.some(row => row.stage === 'session-check' && row.matches === false)).toBe(true)
  })
  await scenario('wrong-route-same-button', async ({ page, log }) => {
    await page.goto(ORIGIN + '/#profile')
    await expect(page.getByRole('button', { name: '画像と一覧を再読み込み', exact: true })).toBeVisible()
    let error
    try { await followingReady(page, post.note, log) } catch (cause) { error = cause }
    expect(Boolean(error)).toBe(true)
  })
  await scenario('stale-same-path-response', async ({ page }) => {
    await page.goto(ORIGIN + '/#'); await followingReady(page, post.note)
    mode = 'stale'
    let seen = signal('timeline')
    await page.evaluate(() => { window.oldRead = fetch('/api/timeline/following').then(response => response.json()) })
    await seen; seen = signal('timeline')
    let completed = false
    const response = responseAfter(page, '/api/timeline/following', 'GET', () => page.evaluate(() => { window.freshRead = fetch('/api/timeline/following').then(response => response.json()) }), 200).then(value => { completed = true; return value })
    await seen
    releases[0](); await page.evaluate(() => window.oldRead)
    expect(completed).toBe(false)
    releases[1](); expect((await response).status()).toBe(200)
    await page.evaluate(() => window.freshRead)
  })
  await scenario('image-error-is-distinct', async ({ page, log }) => {
    mode = 'image-error'
    await page.goto(ORIGIN + '/#')
    // The visible lazy image may already have failed and been replaced by Photo.
    await expect(page.getByRole('button', { name: '一覧を最初から読み込み直す', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'もう一度読み込む', exact: true })).toHaveCount(0)
    let error
    try { await followingReady(page, post.note, log) } catch (cause) { error = cause }
    expect(Boolean(error)).toBe(true)
  })
  await scenario('delete-response-before-dom-transition', async ({ page, log }) => {
    // Delay resolution of the fixture DELETE fetch after observing actual HTTP204.
    await page.addInitScript(() => {
      const original = window.fetch.bind(window)
      window.fetch = async (...args) => {
        const response = await original(...args)
        if (args[1]?.method === 'DELETE') await new Promise(resolve => { window.releaseDelete = resolve })
        return response
      }
    })
    await page.goto(ORIGIN + '/#record/' + post.id)
    await page.getByRole('button', { name: '記録を削除', exact: true }).click()
    await responseAfter(page, '/api/posts/' + post.id, 'DELETE', () => page.getByRole('alertdialog').getByRole('button', { name: '削除する', exact: true }).click(), 204)
    let completed = false
    const task = deletionSettled(page, log).then(() => { completed = true })
    await settleFrames(page); expect(completed).toBe(false)
    await expect(page.getByRole('alertdialog')).toBeVisible()
    await page.evaluate(() => window.releaseDelete())
    await task; expect(await page.evaluate(() => location.hash)).toBe('#profile')
  })
  for (const failAt of ['network-ready', 'network-offline', 'network-error', 'network-retry']) await scenario('failure-' + failAt, async ({ actor, log, offline }) => {
    const persist = log.persist
    log.persist = values => { persist(values); if (values.at(-1).stage === failAt && values.at(-1).phase === 'start') throw new Error('SECRET') }
    let error
    try { await networkRecovery(actor, post.note, log) } catch (cause) { error = cause }
    observations[failAt + '_rejected'] = Boolean(error)
    observations[failAt + '_offline'] = offline()
    expect(Boolean(error)).toBe(true); expect(offline()).toBe(false)
    const status = await actor.page.evaluate(async () => (await fetch('/api/auth/me')).status)
    observations[failAt + '_status'] = status
    expect(status).toBe(200)
    expect(log.rows.some(row => row.stage === 'network-restored' && row.phase === 'pass')).toBe(false)
  })
  await scenario('closed-context-is-failure', async ({ actor, log, context }) => {
    const original = log.stage.bind(log)
    log.stage = async (name, ...args) => { if (name === 'network-ready') await context.close(); return original(name, ...args) }
    let error
    try { await networkRecovery(actor, post.note, log) } catch (cause) { error = cause }
    expect(Boolean(error)).toBe(true); expect(actor.page.isClosed()).toBe(true)
  })
  expect(JSON.stringify(diagnostics)).not.toContain('SECRET')
  passed = true
} catch (error) { rows.push({ id: stage, status: 'fail', failure: failureCategory(error) }); process.exitCode = 1 }
finally {
  for (const release of releases) release()
  await browser?.close(); await close()
  writeFileSync(new URL('fixture.json', output), JSON.stringify({ passed, cases: rows, observations, product_requests: 0, users_created: 0, listeners_closed: true }, null, 2))
}
