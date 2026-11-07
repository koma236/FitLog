import test from 'node:test'
import assert from 'node:assert/strict'
import { urlPolicy, SendBudget, apiSend } from '../support/aws-policy.mjs'

const origin = 'https://dexample.cloudfront.net'
test('exact HTTPS origin rejects normalization tricks and every other destination', () => {
  const allow = urlPolicy(origin)
  for (const value of [origin + '/', origin + '/api/auth/me', 'data:image/png;base64,AA', 'blob:' + origin + '/id']) allow(value)
  for (const value of ['http://dexample.cloudfront.net/', origin + ':443/', 'https://u:p@dexample.cloudfront.net/', 'https://other.cloudfront.net/', 'https://dexample.cloudfront.net./', 'blob:https://other.cloudfront.net/id', 'file:///tmp/a', 'ws://dexample.cloudfront.net/']) {
    assert.throws(() => allow(value), /ORIGIN_BLOCKED/)
  }
})

test('budget is shared, durable before sending, and reserves 200 requests for cleanup', () => {
  const rows = []; let now = 0
  const budget = new SendBudget({ expires: 1000000, now: () => now, persist: row => rows.push(structuredClone(row)) })
  for (let n = 0; n < 2800; n++) budget.take('GET', origin)
  assert.throws(() => budget.take('GET', origin), /REQUEST_LIMIT/)
  budget.cleanup()
  for (let n = 0; n < 200; n++) budget.take('GET', origin)
  assert.throws(() => budget.take('GET', origin), /REQUEST_LIMIT/)
  assert.equal(rows.at(-1).requests, 3000)
  now = 1000000
  assert.throws(() => budget.take('GET', origin), /DEADLINE/)
})

test('body/auth caps and failed persistence deny before invoking the API client', async () => {
  let calls = 0
  const request = { fetch: async () => { calls++; return { status: () => 200 } }, dispose: async () => {} }
  const budget = new SendBudget({ expires: Date.now() + 600000, persist: () => { throw Error('secret-canary') } })
  await assert.rejects(apiSend(request, { origin, budget }, '/api/auth/me'), /BUDGET_WRITE_FAILED/)
  assert.equal(calls, 0)
  const cap = new SendBudget({ expires: 1000000, now: () => 0, persist: () => {} })
  cap.take('POST', origin, 20 * 1024 * 1024)
  assert.throws(() => cap.take('POST', origin, 1), /BODY_LIMIT/)
  for (let i = 0; i < 8; i++) cap.take('POST', origin + '/api/auth/login')
  assert.throws(() => cap.take('POST', origin + '/api/auth/login'), /AUTH_LIMIT/)
})

test('the total authentication cap survives multiple rolling windows', () => {
  let now = 0
  const budget = new SendBudget({ expires: 1000000, now: () => now, persist: () => {} })
  for (let group = 0; group < 3; group++) {
    for (let n = 0; n < 8; n++) budget.take('POST', origin + '/api/auth/signup')
    now += 60001
  }
  assert.throws(() => budget.take('POST', origin + '/api/auth/login'), /AUTH_LIMIT/)
})

test('API wrapper refuses forbidden paths, disables redirects/retries and hides raw exceptions', async () => {
  const calls = []
  const request = { fetch: async (url, options) => { calls.push({ url, options }); throw Error('secret-canary') }, dispose: async () => {} }
  const policy = { origin, budget: new SendBudget({ expires: Date.now() + 600000, persist: () => {} }) }
  for (const value of ['https://other.invalid/', '//other.invalid/x', '/api/../admin', '/api/a\\b']) await assert.rejects(apiSend(request, policy, value))
  assert.equal(calls.length, 0)
  await assert.rejects(apiSend(request, policy, '/api/auth/me'), /^Error: API_SEND_FAILED$/)
  assert.equal(calls[0].url, origin + '/api/auth/me')
  assert.equal(calls[0].options.maxRedirects, 0)
  assert.equal(calls[0].options.maxRetries, 0)
  assert.equal(calls[0].options.ignoreHTTPSErrors, false)
  assert.equal(calls[0].options.headers.Origin, origin)
})

test('last five minutes are reserved for cleanup without extending the hard deadline', () => {
  let now = 0
  const budget = new SendBudget({ expires: 600000, now: () => now, persist: () => {} })
  budget.take('GET', origin)
  now = 300000
  assert.throws(() => budget.take('GET', origin), /DEADLINE/)
  budget.cleanup(); budget.take('GET', origin)
  now = 600000
  assert.throws(() => budget.take('GET', origin), /DEADLINE/)
})
