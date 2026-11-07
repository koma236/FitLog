import assert from 'node:assert/strict'
import { test } from 'node:test'
import { assertLocalUrl, assertQuietEnvironment, sanitizeAxe, sanitizeFailure, captureSearchAllowed, withinDeadline, ResultLedger, Budget } from '../support/safety.mjs'

test('origin guard blocks credentials, external requests, alternate ports and redirected URLs', () => {
  assert.doesNotThrow(() => assertLocalUrl('http://127.0.0.1:15173/api/posts'))
  assert.doesNotThrow(() => assertLocalUrl('blob:http://127.0.0.1:15173/id'))
  for (const url of ['https://example.com/', 'http://127.0.0.1:18080/', 'http://localhost:15173/', 'http://name:secret@127.0.0.1:15173/', 'file:///etc/passwd', 'blob:https://example.com/id']) {
    assert.throws(() => assertLocalUrl(url), /ORIGIN_BLOCKED/)
  }
})

test('verbose environment is rejected before a browser can log credentials', () => {
  assert.doesNotThrow(() => assertQuietEnvironment({}))
  for (const key of ['DEBUG', 'PWDEBUG', 'NODE_DEBUG']) assert.throws(() => assertQuietEnvironment({ [key]: 'secret' }), /VERBOSE_BLOCKED/)
})

test('report ledger fails closed for failed and unvisited steps and never serializes raw errors', () => {
  const ledger = new ResultLedger(['E01', 'E02', 'E03'])
  ledger.start('E01'); ledger.finish('E01', true)
  ledger.start('E02'); ledger.finish('E02', false, new Error('password=SECRET; email=private@example.com'))
  assert.equal(ledger.success, false)
  const rows = ledger.rows()
  assert.deepEqual(rows.map(row => row.status), ['pass', 'fail', 'not_run'])
  assert.equal(rows[1].reason, 'ASSERTION_OR_OPERATION_FAILED')
  assert.doesNotMatch(JSON.stringify(rows), /SECRET|private@|password|stack/)
  assert.throws(() => ledger.start('secret-dynamic-id'), /UNKNOWN_STEP/)
})

test('an unstarted step cannot be marked passed and all visited steps are needed for success', () => {
  const ledger = new ResultLedger(['E01', 'E02'])
  assert.throws(() => ledger.finish('E01', true), /STEP_NOT_RUNNING/)
  ledger.start('E01'); ledger.finish('E01', true)
  assert.equal(ledger.success, false)
  ledger.start('E02'); ledger.finish('E02', true)
  assert.equal(ledger.success, true)
})

test('axe export omits DOM, form values, URLs and selectors containing personal information', () => {
  const result = sanitizeAxe('profile', { violations: [{ id: 'label', impact: 'serious', nodes: [{ html: '<input value="SECRET">', target: ['private@example.com'] }] }], incomplete: [{ id: 'color-contrast', nodes: [{ html: 'SECRET' }] }] })
  assert.deepEqual(result, { screen: 'profile', violations: [{ rule: 'label', impact: 'serious', count: 1 }], incomplete: [{ rule: 'color-contrast', count: 1 }] })
  assert.doesNotMatch(JSON.stringify(result), /SECRET|private@|html|target/)
})

test('resource budget rejects one more allocation before it reaches the application', () => {
  const budget = new Budget({ users: 2, posts: 6 })
  budget.take('users'); budget.take('users')
  assert.throws(() => budget.take('users'), /RESOURCE_LIMIT/)
  for (let i = 0; i < 6; i++) budget.take('posts')
  assert.throws(() => budget.take('posts'), /RESOURCE_LIMIT/)
  assert.throws(() => budget.take('unknown'), /RESOURCE_LIMIT/)
})

test('failure location keeps only source coordinates, never assertion values or error text', () => {
  const error = new Error('SECRET private@example.com')
  error.stack = 'Error SECRET\n at action (/private/SECRET/e2e/specs/journey.spec.ts:87:12)\n fill("PASSWORD")'
  assert.deepEqual(sanitizeFailure(error), { source: 'journey.spec.ts', line: 87, column: 12 })
  assert.deepEqual(sanitizeFailure(new Error('SECRET')), { source: 'unknown', line: null, column: null })
})

test('failure coordinates prefer the calling scenario over a generic helper frame', () => {
  const error = new Error('SECRET')
  error.stack = 'Error SECRET\n at responseFor (/private/e2e/support/app.ts:45:24)\n at action (/private/e2e/specs/journey.spec.ts:244:13)'
  assert.deepEqual(sanitizeFailure(error), { source: 'journey.spec.ts', line: 244, column: 13 })
})

test('capture cannot reveal empty, broad or unrelated search results', () => {
  const expected = { id: 'member-A', username: 'fl10a_run_a' }
  assert.equal(captureSearchAllowed(expected, '', [{ id: 'member-A' }, { id: 'private-user' }]), false)
  assert.equal(captureSearchAllowed(expected, 'fl10a_run_a', [{ id: 'member-A' }, { id: 'private-user' }]), false)
  assert.equal(captureSearchAllowed(expected, 'fl10a_run_a', []), false)
  assert.equal(captureSearchAllowed(expected, 'fl10a_run_a', [{ id: 'private-user' }]), false)
  assert.equal(captureSearchAllowed(expected, 'fl10a_run_a', [{ id: 'member-A' }]), true)
})

test('deadline cancels the active operation before reporting timeout', async () => {
  const events = []
  await assert.rejects(withinDeadline(() => new Promise(() => {}), 5, async () => { events.push('cancelled') }), /CASE_TIMEOUT/)
  assert.deepEqual(events, ['cancelled'])
})

test('completed operation keeps its result and is not cancelled', async () => {
  let cancelled = false
  assert.equal(await withinDeadline(async () => 42, 5, async () => { cancelled = true }), 42)
  assert.equal(cancelled, false)
})

test('an ordinary operation failure propagates without cancelling cleanup-capable contexts', async () => {
  let cancelled = false
  await assert.rejects(withinDeadline(async () => { throw new Error('fixture failure') }, 5, async () => { cancelled = true }), /fixture failure/)
  assert.equal(cancelled, false)
})
