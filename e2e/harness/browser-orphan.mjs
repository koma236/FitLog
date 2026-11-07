// Kill this fixture's own Node without exit handlers; leave the owned browser
// suspended so the Python supervisor must cancel its distinct process group.
import { chromium } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { launchOwnedBrowser } from '../support/owned-browser.mjs'
const run = process.env.FITLOG_GUARD_FIXTURE_RUN
const owner = JSON.parse(readFileSync('/Users/saki/project/FitLog/.git/fitlog-runtime.lock/owner.json', 'utf8'))
if (!run?.startsWith('aws-fixture-') || owner.run_id !== run) throw Error('FIXTURE_RUNNER_REQUIRED')
const directory = new URL('../.artifacts/' + run + '/', import.meta.url)
await launchOwnedBrowser(chromium, fileURLToPath(directory), run, 1, { launchOptions: { args: ['--host-resolver-rules=MAP * ~NOTFOUND'] } })
const row = JSON.parse(readFileSync(new URL('browser-worker-1.json', directory)))
if (row.run_id !== run || row.pid !== row.pgid || row.phase !== 'launched') throw Error('FIXTURE_IDENTITY_REQUIRED')
process.kill(row.pid, 'SIGSTOP')
process.kill(process.pid, 'SIGKILL')
