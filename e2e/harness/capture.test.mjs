import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import { withinCancellableDeadline } from '../support/safety.mjs'

const source = readFileSync(new URL('../specs/journey.spec.ts', import.meta.url), 'utf8')
const captureSource = source.slice(source.indexOf('async function capture('))
const delay = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds))

function fixture({ creationDelay = 0, closeDelay = 0 } = {}) {
  const events = []
  let contexts = 0
  const page = {
    on() {}, mainFrame() {},
    getByRole: () => ({ click: async () => {} }),
    getByLabel: () => ({ fill: async () => {}, isVisible: async () => false }),
    locator: () => ({}), reload: async () => {},
  }
  const sandbox = {
    artifact: '/unused', runId: 'fixture', path: { join: (...parts) => parts.join('/') }, mkdirSync() {}, writeFileSync: () => events.push('marker'),
    expect: () => ({ toBeVisible: async () => {} }), responseFor: async () => {},
    go: async () => { events.push('navigation') },
    guardedPage: async context => context.newPage(),
    guardedContext: async () => {
      contexts++; events.push('creating')
      await delay(creationDelay)
      events.push('created')
      return { addInitScript: async () => {}, newPage: async () => page, close: async () => { events.push('closing'); await delay(closeDelay); events.push('closed') } }
    },
  }
  vm.createContext(sandbox)
  vm.runInContext(ts.transpileModule(captureSource, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText, sandbox)
  const context = { storageState: async () => ({}) }
  const a = { context, username: 'a', name: 'A' }; const b = { context, username: 'b', name: 'B' }
  return { events, contextCount: () => contexts, run: scope => sandbox.capture({}, a, b, 'post', value => events.push(value), scope) }
}

test('a timeout while A is closing cannot start B and waits for A to close', async () => {
  const f = fixture({ closeDelay: 35 })
  await assert.rejects(withinCancellableDeadline(f.run, 15), /CASE_TIMEOUT/)
  assert.equal(f.contextCount(), 1)
  assert.equal(f.events.includes('capture-B'), false)
  assert.equal(f.events.at(-1), 'closed')
  assert.equal(f.events.includes('marker'), false)
})

test('a context created after cancellation closes before returning and cannot navigate', async () => {
  const f = fixture({ creationDelay: 35 })
  await assert.rejects(withinCancellableDeadline(f.run, 10), /CASE_TIMEOUT/)
  assert.equal(f.contextCount(), 1)
  assert.equal(f.events.includes('navigation'), false)
  assert.equal(f.events.at(-1), 'closed')
  assert.equal(f.events.filter(value => value === 'closing').length, 1)
})

test('cancellation prevents a queued operation after a pending operation resolves', async () => {
  let writes = 0
  await assert.rejects(withinCancellableDeadline(async scope => {
    await scope.step(() => delay(30))
    await scope.step(async () => { writes++ })
  }, 5), /CASE_TIMEOUT/)
  assert.equal(writes, 0)
})

test('normal completion returns its result and normal failure still closes resources', async () => {
  assert.equal(await withinCancellableDeadline(async scope => scope.step(async () => 42), 100), 42)
  let closed = false
  await assert.rejects(withinCancellableDeadline(scope => scope.using(async () => ({ close: async () => { closed = true } }), async () => { throw new Error('EXPECTED_FAILURE') }), 100), /EXPECTED_FAILURE/)
  assert.equal(closed, true)
})
