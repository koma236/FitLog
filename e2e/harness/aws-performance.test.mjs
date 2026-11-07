import test from 'node:test'
import assert from 'node:assert/strict'
import { assertPerformanceState, measure } from '../../perf/aws-load.mjs'

const actors = [{ id: 'A' }, { id: 'B' }]
const posts = [{ id: 'a', owner_id: 'A', date: '2026-01-15' }, { id: 'b', owner_id: 'B', date: '2026-01-15' }]
test('performance prerequisites use known owned posts and no remaining cross follow', () => {
  assert.doesNotThrow(() => assertPerformanceState(actors, posts, [['a'], ['b']]))
  assert.throws(() => assertPerformanceState(actors, posts, [['a', 'b'], ['b']]))
  assert.throws(() => assertPerformanceState(actors, posts.slice(0, 1), [['a'], ['b']]))
})
test('two paced actors produce exactly 180 measured slots, with 20 warmup slots excluded', async () => {
  let count = 0
  const rows = await measure(async () => { count++; return { status: 200 } }, { sleep: async () => {}, clock: () => 0 })
  assert.equal(count, 200)
  assert.equal(rows.length, 180)
  for (const kind of ['all', 'following', 'detail']) assert.equal(rows.filter(row => row.route === kind).length, 60)
})
test('one unexpected response terminates load rather than continuing or retrying', async () => {
  let count = 0
  await assert.rejects(measure(async () => { count++; throw Error('SECRET') }, { sleep: async () => {}, clock: () => 0 }), /^Error: PERFORMANCE_FAILED$/)
  assert.ok(count <= 2)
})
