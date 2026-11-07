import { test } from 'node:test'
import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { RecoveryLog, failureCategory, responseAfter, recoveryCases, recoveryRows, networkRecovery } from '../support/recovery.mjs'

test('observation exports only approved scalars even when URL, DOM, body and errors contain secrets', () => {
  let output
  const log = new RecoveryLog(rows => { output = JSON.stringify(rows) })
  log.event('network-ready', {}, 'B', 'observation', { count: 1, visible: true, enabled: true, matches: true, status: 200, request_kind: 'timeline', url: 'SECRET', body: 'SECRET', dom: 'SECRET', error: new Error('SECRET'), failure: 'SECRET' })
  assert.doesNotMatch(output, /SECRET|url|body|dom|error/)
  assert.equal(log.rows[0].operation, 1)
  assert.equal(log.rows[0].page, 1)
  assert.equal(log.rows[0].matches, true)
  assert.throws(() => log.event('SECRET', {}, 'B', 'pass'), /OBSERVATION_INVALID/)
  assert.equal(failureCategory(new Error('SECRET')), 'ASSERTION_OR_OPERATION_FAILED')
})

test('observation persistence failure cannot be reported as a completed stage', async () => {
  let acted = false
  const log = new RecoveryLog(() => { throw new Error('SECRET') })
  await assert.rejects(log.stage('network-ready', {}, 'B', () => { acted = true }))
  assert.equal(acted, false)
})

test('capture locator failures retain a fixed classification without the locator or DOM error', async () => {
  let output
  const log = new RecoveryLog(rows => { output = JSON.stringify(rows) })
  await assert.rejects(log.stage('capture-ready', {}, 'B', () => { throw new Error('strict mode violation: SECRET URL DOM') }))
  assert.equal(log.rows.at(-1).phase, 'fail')
  assert.equal(log.rows.at(-1).failure, 'LOCATOR_NOT_UNIQUE')
  assert.doesNotMatch(output, /SECRET|URL|DOM|strict mode violation/)
})

test('a response from an older same-path request cannot satisfy the current action', async () => {
  const page = new EventEmitter(); const frame = {}; page.mainFrame = () => frame
  const request = () => ({ method: () => 'GET', url: () => 'http://127.0.0.1:15173/api/timeline/following?SECRET', frame: () => frame })
  const old = request(); const fresh = request()
  const response = item => ({ request: () => item, status: () => 200 })
  let completed = false
  const task = responseAfter(page, '/api/timeline/following', 'GET', () => {
    page.emit('response', response(old))
    page.emit('request', fresh)
  }, 200).then(value => { completed = true; return value })
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(completed, false)
  page.emit('response', response(fresh))
  assert.equal((await task).request(), fresh)
  assert.equal(page.listenerCount('request'), 0)
})

test('closed pages and failed actions remove request observers and reject without a success', async () => {
  for (const close of [true, false]) {
    const page = new EventEmitter(); page.mainFrame = () => ({})
    await assert.rejects(responseAfter(page, '/fixture', 'GET', () => { if (close) page.emit('close'); else throw new Error('SECRET') }, 200))
    for (const event of ['request', 'response', 'requestfailed', 'close']) assert.equal(page.listenerCount(event), 0)
  }
})

test('an aborted mount read cannot reject the next read started by the same navigation', async () => {
  const page = new EventEmitter(); const frame = {}; page.mainFrame = () => frame
  const request = () => ({ method: () => 'GET', url: () => 'http://127.0.0.1:15173/api/timeline/following', frame: () => frame })
  const aborted = request(); const actual = request()
  const response = { request: () => actual, status: () => 200 }
  const value = await responseAfter(page, '/api/timeline/following', 'GET', () => {
    page.emit('request', aborted); page.emit('requestfailed', aborted)
    page.emit('request', actual); page.emit('response', response)
  }, 200)
  assert.equal(value, response)
})

test('a failed subcase stays failed while independently ready cases proceed and lost prerequisites remain not_run', async () => {
  const rows = recoveryRows(); const actions = []; let saves = 0
  const cases = {
    network: { ready: async () => true, action: async () => { actions.push('network'); throw new Error('SECRET') } },
    csrf: { ready: async () => true, action: async () => { actions.push('csrf') } },
    'old-session': { ready: async () => false, action: async () => { actions.push('old-session') } },
    'cookie-loss': { ready: async () => { throw new Error('SECRET') }, action: async () => { actions.push('cookie-loss') } },
  }
  assert.equal(await recoveryCases(cases, rows, () => { saves++ }), false)
  assert.deepEqual(actions, ['network', 'csrf'])
  assert.deepEqual(rows.map(row => row.status), ['fail', 'pass', 'not_run', 'not_run'])
  assert.ok(saves > 0)
  assert.doesNotMatch(JSON.stringify(rows), /SECRET/)
})

test('recovery navigation uses the validated origin passed by its caller', async () => {
  const page = new EventEmitter(); page.mainFrame = () => ({})
  let destination
  page.goto = async value => { destination = value; throw Error('STOP_BEFORE_ANY_NETWORK') }
  const actor = { page, context: { setOffline: async () => {} } }
  await assert.rejects(networkRecovery(actor, 'known', new RecoveryLog(), 'https://dexample.cloudfront.net'))
  assert.equal(destination, 'https://dexample.cloudfront.net/#')
})
