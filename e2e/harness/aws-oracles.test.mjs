import test from 'node:test'
import assert from 'node:assert/strict'
import { unchangedRecord } from '../support/aws-oracles.mjs'
test('unchanged record ignores expiring media capabilities but retains content and owner', () => {
  const a = { id: 'post', note: 'fixed', author: { id: 'owner', avatar: { id: 'avatar', url: 'secret-first' } }, image: { id: 'image', url: 'signed-first', expires_at: 'first' }, exercises: [{ name: 'bench', sets: [{ reps: 10 }] }] }
  const b = structuredClone(a); b.image.url = 'signed-second'; b.image.expires_at = 'second'; b.author.avatar.url = 'secret-second'
  assert.deepEqual(unchangedRecord(a), unchangedRecord(b))
  b.note = 'changed'
  assert.notDeepEqual(unchangedRecord(a), unchangedRecord(b))
  assert.doesNotMatch(JSON.stringify(unchangedRecord(a)), /secret|signed/)
})
