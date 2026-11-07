import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, statSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { saveArtifact } from '../support/private-artifacts.mjs'
import { SendBudget } from '../support/aws-policy.mjs'
import { Budget } from '../support/safety.mjs'
test('real budget and result writers produce the filenames consumed by the runner', () => {
  const directory = mkdtempSync(path.join(tmpdir(), 'fitlog-artifact-'))
  try {
    const persist = (name, value) => saveArtifact(directory, name, value)
    new Budget({ users: 2 }, used => persist('resource-budget', used)).take('users')
    new SendBudget({ expires: Date.now() + 600000, persist: state => persist('budget', state) }).take('GET', 'https://dexample.cloudfront.net/')
    for (const name of ['aws-results', 'storage-evidence', 'performance-requests', 'performance']) persist(name, { status: 'not_run' })
    assert.equal(JSON.parse(readFileSync(path.join(directory, 'budget.json'))).requests, 1)
    assert.equal(JSON.parse(readFileSync(path.join(directory, 'resource-budget.json'))).users, 1)
    for (const name of ['budget', 'resource-budget', 'aws-results', 'storage-evidence', 'performance-requests', 'performance']) assert.equal(statSync(path.join(directory, name + '.json')).mode & 0o777, 0o600)
    assert.throws(() => persist('../escape', {}), /ARTIFACT_NAME_INVALID/)
  } finally { rmSync(directory, { recursive: true }) }
})
