import test from 'node:test'
import assert from 'node:assert/strict'
import * as oracles from '../support/aws-oracles.mjs'
const { unchangedRecord, captureAllowed } = oracles
test('unchanged record ignores expiring media capabilities but retains content and owner', () => {
  const a = { id: 'post', note: 'fixed', author: { id: 'owner', avatar: { id: 'avatar', url: 'secret-first' } }, image: { id: 'image', url: 'signed-first', expires_at: 'first' }, exercises: [{ name: 'bench', sets: [{ reps: 10 }] }] }
  const b = structuredClone(a); b.image.url = 'signed-second'; b.image.expires_at = 'second'; b.author.avatar.url = 'secret-second'
  assert.deepEqual(unchangedRecord(a), unchangedRecord(b))
  b.note = 'changed'
  assert.notDeepEqual(unchangedRecord(a), unchangedRecord(b))
  assert.doesNotMatch(JSON.stringify(unchangedRecord(a)), /secret|signed/)
})
test('failed AWS recovery can only clean up, while local continuation stays compatible', () => {
  assert.equal(captureAllowed(true, true), false)
  assert.equal(captureAllowed(true, false), true)
  assert.equal(captureAllowed(false, true), true)
})

function contrastFixture(fault) {
  let record = { id: 'post', note: 'before', exercises: [{ name: 'bench' }], author: { id: 'owner' } }
  const calls = []
  const send = async (path, options = {}) => {
    calls.push(structuredClone({ path, ...options }))
    let status = 200; let body
    if (path === '/api/auth/csrf') body = { csrf_token: 'PRIVATE-CSRF-CANARY' }
    else if (!options.method) body = structuredClone(record)
    else {
      const negative = options.headers.Origin === 'https://origin-probe.invalid'
      const data = JSON.parse(options.data)
      if (negative) {
        status = 403; body = { code: fault === 'wrong-code' ? 'NOT_OWNER' : 'CSRF_FAILED' }
        if (fault === 'negative-mutates') record.note = data.note
      } else if (fault === 'positive-fails' || (fault === 'restore-fails' && data.note === 'before')) {
        status = 403; body = { code: 'CSRF_FAILED' }
      } else {
        const { recalculate: _recalculate, ...fields } = data
        if (fault !== 'positive-noop') record = { ...record, ...fields }
        body = structuredClone(record)
      }
    }
    return { status: () => status, json: async () => body, dispose: async () => {} }
  }
  return { send, calls }
}

const contrastInput = { origin: 'https://dexample.cloudfront.net', owner: 'owner', post: 'post',
  payload: { note: 'before', exercises: [{ name: 'bench' }] }, marker: 'origin-contrast-run' }

test('Origin contrast changes only Origin and restores a distinguishable state before denial', async () => {
  assert.equal(typeof oracles.originContrast, 'function')
  const fixture = contrastFixture()
  assert.deepEqual(await oracles.originContrast(fixture.send, contrastInput), { positive: 200, restored: 200, negative: 403, unchanged: true })
  const puts = fixture.calls.filter(c => c.method === 'PUT')
  assert.equal(puts.length, 3)
  const [positive, restore, negative] = puts
  assert.notEqual(positive.data, restore.data)
  assert.equal(positive.data, negative.data)
  assert.equal(positive.path, '/api/posts/post')
  assert.equal(negative.headers.Origin, 'https://origin-probe.invalid')
  assert.deepEqual({ ...positive, headers: { ...positive.headers, Origin: 'ignored' } }, { ...negative, headers: { ...negative.headers, Origin: 'ignored' } })
  assert.equal(fixture.calls.filter(c => c.path === '/api/auth/csrf').length, 1)
  assert.equal(fixture.calls.length, 8)
})

for (const fault of ['positive-fails', 'positive-noop', 'restore-fails', 'wrong-code', 'negative-mutates']) {
  test('Origin contrast rejects ' + fault, async () => {
    assert.equal(typeof oracles.originContrast, 'function')
    const fixture = contrastFixture(fault)
    await assert.rejects(oracles.originContrast(fixture.send, contrastInput), /^Error: ORIGIN_CONTRAST_FAILED$/)
  })
}
