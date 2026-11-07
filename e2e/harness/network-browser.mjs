// Controlled HTTP fixtures only. Never contacts the product, DB, or internet.
import { createServer } from 'node:http'
import { readFileSync, writeFileSync } from 'node:fs'
import { chromium, expect } from '@playwright/test'
import { installLocalRequestGuard, newLocalPage, ORIGIN } from '../support/safety.mjs'

const run = process.env.FITLOG_GUARD_FIXTURE_RUN
const owner = JSON.parse(readFileSync('/Users/saki/project/FitLog/.git/fitlog-runtime.lock/owner.json', 'utf8'))
if (!run || owner.run_id !== run || !run.startsWith('network-fixture-')) throw new Error('FIXTURE_RUNNER_REQUIRED')
process.kill(owner.pid, 0)
let forbiddenReads = 0; let credentialReads = 0
let browser; let phase = 'start'; let guardPhase = 'not_started'; let failure = null; let passed = false
const nativeSessions = []
const guardEvents = []
let detachedPageClosed = false; let initializationDisconnectRejected = false; let normalPageClosePassed = false
let heldResponseId
let notifyHeld
let releaseHeld
const held = new Promise(resolve => { notifyHeld = resolve })
const release = new Promise(resolve => { releaseHeld = resolve })
const allowed = createServer((request, response) => {
  if (request.url === '/fixture-auth') {
    response.writeHead(201, { 'Content-Type': 'application/json', 'Set-Cookie': 'guard_fixture=synthetic; HttpOnly; Path=/; SameSite=Lax' }); response.end('{"id":"fixture"}'); return
  }
  if (request.url === '/fixture-me') {
    response.writeHead(request.headers.cookie?.includes('guard_fixture=synthetic') ? 200 : 401, { 'Content-Type': 'application/json' }); response.end('{}'); return
  }
  if (request.url === '/fixture-slow') {
    response.writeHead(200, { 'Content-Type': 'application/json' }); response.end('{"fixture":true}'); return
  }
  if (request.url === '/redirect' || request.url === '/chain' || request.url === '/credential-redirect' || request.url === '/local-redirect') {
    const location = request.url === '/local-redirect' ? '/ok' : request.url === '/chain' ? '/redirect' : request.url === '/credential-redirect' ? 'http://u:p@127.0.0.1:15173/credential-target' : 'http://127.0.0.1:18080/forbidden'
    response.writeHead(302, { Location: location }); response.end(); return
  }
  if (request.url === '/credential-target') credentialReads++
  response.writeHead(200, { 'Content-Type': 'text/html', 'Cache-Control': 'no-store' }); response.end('<!doctype html><title>Guard fixture</title>ok')
})
const forbidden = createServer((_request, response) => { forbiddenReads++; response.writeHead(200, { 'Access-Control-Allow-Origin': '*' }); response.end('forbidden') })
const listen = (server, port) => new Promise((resolve, reject) => { server.once('error', reject); server.listen(port, '127.0.0.1', resolve) })
const close = server => server.listening ? new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve())) : Promise.resolve()
try {
  await listen(allowed, 15173); await listen(forbidden, 18080)
  browser = await chromium.launch()
  const context = await browser.newContext({ serviceWorkers: 'block' })
  const guarded = {
    route: context.route.bind(context),
    newPage: context.newPage.bind(context),
    close: context.close.bind(context),
    newCDPSession: async page => {
      guardPhase = 'attaching'
      const session = await context.newCDPSession(page)
      nativeSessions.push(session)
      return {
        on: (name, action) => session.on(name, (...args) => {
          if (name === 'close') guardEvents.push({ phase, event: 'session-close' })
          if (name === 'Fetch.requestPaused' && phase === 'canceled-response' && args[0].responseStatusCode === 200 && args[0].request.url.endsWith('/fixture-slow')) heldResponseId = args[0].requestId
          return action(...args)
        }),
        send: async (method, parameters) => {
          guardPhase = method
          if (method === 'Fetch.continueResponse' && parameters.requestId === heldResponseId) { notifyHeld(); await release }
          try { const result = await session.send(method, parameters); guardPhase = method + ':done'; return result }
          catch (error) {
            const category = /[Ii]nvalid.*[Ii]nterception|Invalid InterceptionId/.test(error.message) ? 'interception_gone' : /closed|detached/.test(error.message) ? 'closed' : 'other'
            guardEvents.push({ phase, method, error_category: category }); throw error
          }
        },
      }
    },
  }
  await installLocalRequestGuard(guarded)
  const page = await newLocalPage(guarded)
  phase = 'allowed'
  expect((await page.goto(ORIGIN + '/ok')).status()).toBe(200)
  expect((await page.goto(ORIGIN + '/local-redirect')).status()).toBe(200)
  phase = 'redirect'
  for (const pathname of ['/redirect', '/chain', '/credential-redirect']) {
    // Keep a denied navigation's asynchronous error document out of later cases.
    const candidate = await newLocalPage(guarded)
    let rejected = false
    try { await candidate.goto(ORIGIN + pathname, { timeout: 10_000 }) } catch { rejected = true }
    expect(rejected).toBe(true)
    expect(forbiddenReads).toBe(0); expect(credentialReads).toBe(0)
    await candidate.close()
  }
  phase = 'fetch-redirect'
  await page.goto(ORIGIN + '/ok')
  expect(await page.evaluate(async () => { try { await fetch('/redirect'); return false } catch { return true } })).toBe(true)
  expect(forbiddenReads).toBe(0)
  phase = 'auth-cookie'
  const auth = await page.evaluate(async () => {
    const response = await fetch('/fixture-auth', { method: 'POST', credentials: 'same-origin' })
    const body = await response.json()
    const me = await fetch('/fixture-me', { credentials: 'same-origin' })
    return { status: response.status, id: body.id, me: me.status }
  })
  expect(auth).toEqual({ status: 201, id: 'fixture', me: 200 })
  phase = 'canceled-response'
  await page.evaluate(() => {
    window.fixtureAbort = new AbortController()
    window.fixtureTask = fetch('/fixture-slow', { signal: window.fixtureAbort.signal }).then(() => false, () => true)
  })
  await held
  await page.evaluate(() => { window.fixtureAbort.abort() })
  releaseHeld()
  expect(await page.evaluate(() => window.fixtureTask)).toBe(true)
  expect((await page.goto(ORIGIN + '/ok')).status()).toBe(200)
  phase = 'preview'
  const fixture = readFileSync(new URL('../fixtures/pixels.png', import.meta.url)).toString('base64')
  const images = await page.evaluate(async data => {
    const bytes = Uint8Array.from(atob(data), value => value.charCodeAt(0))
    const blob = URL.createObjectURL(new Blob([bytes], { type: 'image/png' }))
    try {
      return await Promise.all(['data:image/png;base64,' + data, blob].map(src => new Promise(resolve => {
        const image = document.createElement('img'); image.onload = () => resolve(image.naturalWidth); image.onerror = () => resolve(0); image.src = src; document.body.append(image)
      })))
    } finally { URL.revokeObjectURL(blob) }
  }, fixture)
  expect(images).toEqual([2, 2])
  phase = 'offline'
  await context.setOffline(true)
  expect(await page.evaluate(async () => { try { await fetch('/ok'); return false } catch { return true } })).toBe(true)
  await context.setOffline(false)
  expect((await page.goto(ORIGIN + '/ok')).status()).toBe(200)
  phase = 'detached-session'
  await nativeSessions[0].detach()
  await expect.poll(() => page.isClosed()).toBe(true)
  detachedPageClosed = true
  let rejected = false
  try { await page.goto(ORIGIN + '/redirect', { timeout: 1_000 }) } catch { rejected = true }
  expect(rejected).toBe(true); expect(forbiddenReads).toBe(0)
  phase = 'normal-close'
  const freshPage = await newLocalPage(guarded)
  expect((await freshPage.goto(ORIGIN + '/ok')).status()).toBe(200)
  await freshPage.close()
  expect(freshPage.isClosed()).toBe(true)
  const survivor = await newLocalPage(guarded)
  expect((await survivor.goto(ORIGIN + '/ok')).status()).toBe(200)
  await survivor.close()
  normalPageClosePassed = true
  await context.close()
  phase = 'initialization-disconnect'
  const initializing = await browser.newContext({ serviceWorkers: 'block' })
  const disconnecting = {
    route: initializing.route.bind(initializing), newPage: initializing.newPage.bind(initializing), close: initializing.close.bind(initializing),
    newCDPSession: async page => {
      const session = await initializing.newCDPSession(page)
      return { on: session.on.bind(session), send: async (method, parameters) => {
        const result = await session.send(method, parameters)
        if (method === 'Fetch.enable') await session.detach()
        return result
      } }
    },
  }
  await installLocalRequestGuard(disconnecting)
  await expect(newLocalPage(disconnecting)).rejects.toThrow('NATIVE_GUARD_UNAVAILABLE')
  initializationDisconnectRejected = true
  await initializing.close()
  passed = true
} catch (error) {
  failure = error.message.includes('Timeout') ? 'timeout' : error.message.includes('ERR_BLOCKED_BY_CLIENT') ? 'blocked' : /closed|detached/.test(error.message) ? 'closed' : 'other'
  process.exitCode = 1
} finally {
  releaseHeld()
  await browser?.close()
  await close(allowed); await close(forbidden)
  writeFileSync(new URL('../.artifacts/' + run + '/fixture.json', import.meta.url), JSON.stringify({ passed, phase, guard_phase: guardPhase, guard_events: guardEvents, failure, detached_page_closed: detachedPageClosed, initialization_disconnect_rejected: initializationDisconnectRejected, normal_page_close_passed: normalPageClosePassed, forbidden_reads: forbiddenReads, credential_reads: credentialReads, product_requests: 0, users_created: 0, listeners_closed: true }, null, 2))
}
