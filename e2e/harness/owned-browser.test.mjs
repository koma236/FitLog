import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { launchOwnedBrowser } from '../support/owned-browser.mjs'

test('browser PID is obtained through CDP and bound before use, without a listener', async () => {
  const directory = mkdtempSync(path.join(tmpdir(), 'fitlog-browser-'))
  let detached = false
  const browser = { close: async () => {}, newBrowserCDPSession: async () => ({ send: async command => { assert.equal(command, 'SystemInfo.getProcessInfo'); return { processInfo: [{ type: 'browser', id: 12345 }] } }, detach: async () => { detached = true } }) }
  try {
    const value = await launchOwnedBrowser({ launch: async () => browser }, directory, 'aaaaaaaaaaaa', 0, { identity: pid => ({ pgid: pid, birth: 'fixture-birth' }) })
    assert.equal(value, browser); assert.equal(detached, true)
    const record = JSON.parse(readFileSync(path.join(directory, 'browser-worker-0.json')))
    assert.equal(record.pid, 12345); assert.equal(record.pgid, 12345)
    assert.equal(record.run_id, 'aaaaaaaaaaaa'); assert.equal(record.birth, 'fixture-birth')
  } finally { rmSync(directory, { recursive: true }) }
})
test('failed launch leaves a durable unknown intent rather than inventing a stopped browser', async () => {
  const directory = mkdtempSync(path.join(tmpdir(), 'fitlog-browser-'))
  try {
    await assert.rejects(launchOwnedBrowser({ launch: async () => { throw Error('SECRET') } }, directory, 'aaaaaaaaaaaa', 0), /BROWSER_START_FAILED/)
    const record = JSON.parse(readFileSync(path.join(directory, 'browser-worker-0.json')))
    assert.equal(record.phase, 'launching'); assert.equal(record.pid, null)
    assert.doesNotMatch(JSON.stringify(record), /SECRET/)
  } finally { rmSync(directory, { recursive: true }) }
})
