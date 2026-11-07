import test from 'node:test'
import assert from 'node:assert/strict'
import { installLocalRequestGuard, newLocalPage, ORIGIN } from '../support/safety.mjs'

function fixture(fail = false, { closeDuringEnable = false, closeFails = false, finishedInterception = false } = {}) {
  let handler
  const commands = []; const events = []
  const handlers = new Map()
  const page = { close: async () => { events.push('close'); if (closeFails) throw new Error('close failed') } }
  const context = {
    route: async (_pattern, callback) => { handler = callback },
    newPage: async () => page,
    close: async () => events.push('context-close'),
    newCDPSession: async () => ({ on: (name, action) => handlers.set(name, action), send: async (method, params) => {
      commands.push({ method, params })
      if (finishedInterception && params?.requestId === 'canceled') throw new Error('Protocol error (Fetch.continueResponse): Invalid InterceptionId.')
      if (closeDuringEnable && method === 'Fetch.enable') await handlers.get('close')?.()
      if (fail) throw new Error('unsupported')
    } }),
  }
  return {
    context, commands, events, paused: event => handlers.get('Fetch.requestPaused')(event),
    disconnected: () => handlers.get('close')?.(),
    request: url => handler({ request: () => ({ url: () => url, frame: () => ({ page: () => page }) }), abort: async () => events.push('abort'), continue: async () => events.push('continue') }),
  }
}

test('external requests abort before native guard or continue', async () => {
  const f = fixture(); await installLocalRequestGuard(f.context)
  await f.request('https://outside.invalid/')
  assert.deepEqual(f.events, ['abort']); assert.equal(f.commands.length, 0)
})

test('a page receives native redirect blocking before its first allowed request', async () => {
  const f = fixture(); await installLocalRequestGuard(f.context)
  await newLocalPage(f.context)
  await f.request(ORIGIN + '/first'); await f.request(ORIGIN + '/second')
  assert.deepEqual(f.events, ['continue', 'continue'])
  assert.deepEqual(f.commands, [{ method: 'Fetch.enable', params: { patterns: [{ urlPattern: '*', requestStage: 'Request' }, { urlPattern: '*', requestStage: 'Response' }] } }])
})

test('unsupported native blocking fails closed on every request without fallback', async () => {
  const f = fixture(true); await installLocalRequestGuard(f.context)
  await assert.rejects(newLocalPage(f.context), /NATIVE_GUARD_UNAVAILABLE/)
  await f.request(ORIGIN + '/first'); await f.request(ORIGIN + '/second')
  assert.deepEqual(f.events, ['close', 'abort', 'abort'])
})

test('an unguarded page cannot make even an otherwise allowed request', async () => {
  const f = fixture(); await installLocalRequestGuard(f.context)
  await f.request(ORIGIN + '/first')
  assert.deepEqual(f.events, ['abort'])
})

test('native response interception rejects forbidden redirect targets before following', async () => {
  const f = fixture(); await installLocalRequestGuard(f.context); await newLocalPage(f.context)
  for (const target of ['https://outside.invalid/', 'http://127.0.0.1:18080/', 'http://u:p@127.0.0.1:15173/']) {
    await f.paused({ requestId: 'fixture', request: { url: ORIGIN + '/redirect' }, responseStatusCode: 302, responseHeaders: [{ name: 'LOCATION', value: target }] })
    assert.deepEqual(f.commands.at(-1), { method: 'Fetch.failRequest', params: { requestId: 'fixture', errorReason: 'BlockedByClient' } })
  }
  await f.paused({ requestId: 'fixture', request: { url: ORIGIN + '/redirect' }, responseStatusCode: 302, responseHeaders: [{ name: 'Location', value: '/ok' }] })
  assert.equal(f.commands.at(-1).method, 'Fetch.continueResponse')
})

test('native request interception also rejects a redirect hop without a response event', async () => {
  const f = fixture(); await installLocalRequestGuard(f.context); await newLocalPage(f.context)
  await f.paused({ requestId: 'hop', request: { url: 'https://outside.invalid/' } })
  assert.equal(f.commands.at(-1).method, 'Fetch.failRequest')
})

test('a detached CDP session closes its page and permanently blocks later requests', async () => {
  const f = fixture(); await installLocalRequestGuard(f.context); await newLocalPage(f.context)
  await f.disconnected()
  await f.request(ORIGIN + '/redirect')
  assert.deepEqual(f.events, ['close', 'abort'])
  await f.paused({ requestId: 'late', request: { url: ORIGIN + '/ok' } })
  assert.equal(f.commands.at(-1).method, 'Fetch.failRequest')
})

test('disconnect during guard initialization cannot return a usable page', async () => {
  const f = fixture(false, { closeDuringEnable: true }); await installLocalRequestGuard(f.context)
  await assert.rejects(newLocalPage(f.context), /NATIVE_GUARD_UNAVAILABLE/)
  await f.request(ORIGIN + '/ok')
  assert.deepEqual(f.events, ['close', 'abort'])
})

test('duplicate close notifications share one stop operation', async () => {
  const f = fixture(); await installLocalRequestGuard(f.context); await newLocalPage(f.context)
  await Promise.all([f.disconnected(), f.disconnected()])
  assert.deepEqual(f.events, ['close'])
})

test('a failed page stop falls back to stopping its owned context', async () => {
  const f = fixture(false, { closeFails: true }); await installLocalRequestGuard(f.context); await newLocalPage(f.context)
  await f.disconnected()
  await f.request(ORIGIN + '/ok')
  assert.deepEqual(f.events, ['close', 'context-close', 'abort'])
})

test('an already-canceled request does not invalidate a still-connected guard', async () => {
  const f = fixture(false, { finishedInterception: true }); await installLocalRequestGuard(f.context); await newLocalPage(f.context)
  await f.paused({ requestId: 'canceled', request: { url: ORIGIN + '/slow' }, responseStatusCode: 200 })
  await f.request(ORIGIN + '/ok')
  assert.deepEqual(f.events, ['continue'])
  await f.disconnected()
  await f.request(ORIGIN + '/ok')
  assert.deepEqual(f.events, ['continue', 'close', 'abort'])
})

test('failure to persist a guard observation stops the page instead of continuing', async () => {
  const f = fixture(false, { finishedInterception: true }); await installLocalRequestGuard(f.context)
  await newLocalPage(f.context, () => { throw new Error('storage unavailable') })
  await f.paused({ requestId: 'canceled', request: { url: ORIGIN + '/slow' }, responseStatusCode: 200 })
  await f.request(ORIGIN + '/ok')
  assert.deepEqual(f.events, ['close', 'abort'])
})

test('injected policy checks and charges each native request once, never response events', async () => {
  const f = fixture(); const charged = []
  const validate = url => { if (!url.startsWith('https://dexample.cloudfront.net/')) throw Error('ORIGIN_BLOCKED') }
  await installLocalRequestGuard(f.context, { validate, reserve: event => charged.push(event.request.method) })
  await newLocalPage(f.context)
  await f.paused({ requestId: 'first', request: { url: 'https://dexample.cloudfront.net/ok', method: 'GET' } })
  await f.paused({ requestId: 'first', request: { url: 'https://dexample.cloudfront.net/ok', method: 'GET' }, responseStatusCode: 200 })
  assert.deepEqual(charged, ['GET'])
  await f.request(ORIGIN + '/wrong')
  assert.equal(f.events.at(-1), 'abort')
})
