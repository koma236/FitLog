// HTTPS and CONNECT terminate only on fixed local fixture listeners.
import http from 'node:http'
import https from 'node:https'
import net from 'node:net'
import { createPublicKey, createHash } from 'node:crypto'
import { readFileSync, writeFileSync } from 'node:fs'
import { chromium, request, expect } from '@playwright/test'
import { installAwsGuard, urlPolicy, SendBudget, apiSend, nativeBodyBytes } from '../support/aws-policy.mjs'
import { newLocalPage } from '../support/safety.mjs'
import { launchOwnedBrowser } from '../support/owned-browser.mjs'
import { saveArtifact } from '../support/private-artifacts.mjs'
import { originContrast } from '../support/aws-oracles.mjs'
import { fileURLToPath } from 'node:url'

const run = process.env.FITLOG_GUARD_FIXTURE_RUN
const owner = JSON.parse(readFileSync('/Users/saki/project/FitLog/.git/fitlog-runtime.lock/owner.json', 'utf8'))
if (!run?.startsWith('aws-fixture-') || owner.run_id !== run) throw Error('FIXTURE_RUNNER_REQUIRED')
process.kill(owner.pid, 0)
const directory = new URL('../.artifacts/' + run + '/', import.meta.url)
const key = readFileSync(new URL('key.pem', directory)); const cert = readFileSync(new URL('cert.pem', directory))
const pin = createHash('sha256').update(createPublicKey(cert).export({ type: 'spki', format: 'der' })).digest('base64')
const origin = 'https://dexample.cloudfront.net'
let forbidden = 0; let allowed = 0; let bytes = 0; let sockets = new Set(); let browser
let passed = false; let stage = 'start'
let fixtureNote = 'before'
const contrastPuts = []
const sessionCanary = 'PRIVATE-SESSION-CANARY'
const csrfCanary = 'PRIVATE-CSRF-CANARY'
const server = https.createServer({ key, cert }, (req, res) => {
  allowed++
  if (req.url === '/forbidden') forbidden++
  if (req.url === '/redirect' || req.url === '/chain' || req.url === '/api/redirect') {
    res.writeHead(302, { Location: req.url === '/chain' ? '/redirect' : 'https://other.cloudfront.net/forbidden' }); res.end(); return
  }
  if (req.url === '/api/drip') {
    res.writeHead(200, { 'Content-Type': 'application/json' }); res.write('{')
    return // Owned listener closes the hanging body after client cancellation.
  }
  let received = 0
  const chunks = []
  req.on('data', chunk => { received += chunk.length; chunks.push(chunk) })
  req.on('end', () => {
    bytes += received
    if (req.url === '/api/auth/csrf' || req.url === '/api/posts/fixture') {
      if (!req.headers.cookie?.includes('sessionid=' + sessionCanary)) { res.writeHead(401); res.end('{}'); return }
      let status = 200; let body
      if (req.url === '/api/auth/csrf') body = { csrf_token: csrfCanary }
      else if (req.method === 'PUT') {
        const raw = Buffer.concat(chunks).toString()
        contrastPuts.push({ headers: req.headers, method: req.method, path: req.url, raw })
        if (req.headers['x-csrftoken'] !== csrfCanary) { status = 403; body = { code: 'INVALID_TOKEN' } }
        else if (req.headers.origin !== origin) { status = 403; body = { code: 'CSRF_FAILED' } }
        else { fixtureNote = JSON.parse(raw).note; body = { ok: true } }
      }
      body ??= { id: 'fixture', note: fixtureNote, exercises: [] }
      res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(body)); return
    }
    res.writeHead(200, { 'Content-Type': req.url?.startsWith('/api/') ? 'application/json' : 'text/html' })
    res.end(req.url?.startsWith('/api/') ? '{"ok":true}' : '<!doctype html><title>synthetic guard</title>fixture')
  })
})
const proxy = http.createServer((_req, res) => { forbidden++; res.writeHead(403); res.end() })
proxy.on('connect', (req, client, head) => {
  if (req.url !== 'dexample.cloudfront.net:443') { forbidden++; client.destroy(); return }
  const upstream = net.connect(18080, '127.0.0.1', () => {
    client.write('HTTP/1.1 200 Connection Established\r\n\r\n')
    if (head.length) upstream.write(head)
    client.pipe(upstream); upstream.pipe(client)
  })
  for (const socket of [client, upstream]) {
    sockets.add(socket); socket.on('close', () => sockets.delete(socket)); socket.on('error', () => { client.destroy(); upstream.destroy() })
  }
})
const listen = (listener, port) => new Promise((resolve, reject) => { listener.once('error', reject); listener.listen(port, '127.0.0.1', resolve) })
const close = listener => listener.listening ? new Promise(resolve => listener.close(resolve)) : Promise.resolve()
const policy = { origin, budget: new SendBudget({ expires: Date.now() + 600000, persist: value => saveArtifact(fileURLToPath(directory), 'budget', value) }) }
try {
  await listen(server, 18080); await listen(proxy, 15173)
  browser = await launchOwnedBrowser(chromium, fileURLToPath(directory), run, 0, { launchOptions: { proxy: { server: 'http://127.0.0.1:15173' }, args: ['--ignore-certificate-errors-spki-list=' + pin] } })
  policy.budget.watch(() => browser.close())
  const context = await browser.newContext({ serviceWorkers: 'block', ignoreHTTPSErrors: false })
  await installAwsGuard(context, { validate: urlPolicy(origin), reserve: event => policy.budget.take(event.request.method, event.request.url, nativeBodyBytes(event.request)) })
  const page = await newLocalPage(context)
  stage = 'same-origin'
  expect((await page.goto(origin + '/')).status()).toBe(200)
  stage = 'body'
  const post = await page.evaluate(async () => {
    const data = new FormData(); data.append('image', new Blob([new Uint8Array([1, 2, 3])], { type: 'image/png' }), 'fixture.png')
    return (await fetch('/api/upload', { method: 'PUT', body: data })).status
  })
  expect(post).toBe(200); expect(bytes).toBeGreaterThan(3)
  stage = 'worker-websocket'
  expect(await page.evaluate(() => { try { new Worker('https://other.cloudfront.net/forbidden'); return false } catch { return true } })).toBe(true)
  await page.evaluate(() => { new WebSocket('wss://other.cloudfront.net/forbidden') })
  stage = 'redirects'
  for (const p of ['/redirect', '/chain']) {
    const candidate = await newLocalPage(context)
    await expect(candidate.goto(origin + p)).rejects.toThrow()
  }
  stage = 'api-context'
  const api = await request.newContext({ proxy: { server: 'http://127.0.0.1:15173' }, ignoreHTTPSErrors: false })
  expect((await apiSend(api, policy, '/api/ok')).status()).toBe(200)
  await expect(apiSend(api, policy, '/api/redirect')).rejects.toThrow('API_SEND_FAILED')
  await api.dispose()
  stage = 'origin-contrast'
  await context.addCookies([{ name: 'sessionid', value: sessionCanary, url: origin, secure: true, httpOnly: true, sameSite: 'Lax' }])
  const contrast = await originContrast((path, options) => apiSend(context.request, policy, path, options),
    { origin, owner: 'fixture-owner', post: 'fixture', payload: { note: 'before', exercises: [] }, marker: 'fixture-positive' })
  expect(contrast).toEqual({ positive: 200, restored: 200, negative: 403, unchanged: true })
  expect(contrastPuts.length).toBe(3)
  const [positive, , negative] = contrastPuts
  expect({ ...positive, headers: { ...positive.headers, origin: 'same' } }).toEqual({ ...negative, headers: { ...negative.headers, origin: 'same' } })
  expect(fixtureNote).toBe('before')
  expect(JSON.stringify(contrast)).not.toMatch(/PRIVATE|CSRF|SESSION/)
  stage = 'body-timeout'
  const hanging = await request.newContext({ proxy: { server: 'http://127.0.0.1:15173' }, ignoreHTTPSErrors: false })
  const began = performance.now()
  await expect(apiSend(hanging, policy, '/api/drip')).rejects.toThrow('API_SEND_FAILED')
  expect(performance.now() - began).toBeLessThan(6500)
  await hanging.dispose()
  stage = 'approval-expiry'
  const expiring = await request.newContext({ proxy: { server: 'http://127.0.0.1:15173' }, ignoreHTTPSErrors: false })
  const expiryBudget = new SendBudget({ expires: Date.now() + 30150, persist: () => {} })
  expiryBudget.cleanup()
  let stoppedAtExpiry = false
  expiryBudget.watch(async () => { await expiring.dispose(); stoppedAtExpiry = true })
  await expect(apiSend(expiring, { origin, budget: expiryBudget }, '/api/drip')).rejects.toThrow('API_SEND_FAILED')
  await expiryBudget.stopAll()
  expect(stoppedAtExpiry).toBe(true)
  stage = 'finished'
  expect(forbidden).toBe(0); expect(allowed).toBeGreaterThan(3)
  expect(policy.budget.state.bytes).toBe(bytes)
  passed = true
} catch { process.exitCode = 1 }
finally {
  await browser?.close()
  for (const socket of sockets) socket.destroy()
  server.closeAllConnections(); proxy.closeAllConnections()
  await close(proxy); await close(server)
  writeFileSync(new URL('fixture.json', directory), JSON.stringify({ passed, stage, forbidden_reads: forbidden, allowed_reads: allowed, body_bytes: bytes, origin_contrast: contrastPuts.length === 3 && fixtureNote === 'before' ? 'pass' : 'not_run', product_requests: 0, aws: 'not_run', tls: 'fixture_certificate_spki_pinned_in_chromium_ca_in_node', listeners_closed: true }), { mode: 0o600 })
}
