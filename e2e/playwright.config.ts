import { defineConfig } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { assertQuietEnvironment } from './support/safety.mjs'

assertQuietEnvironment(process.env)
const run = process.env.FITLOG_E2E_RUN_ID
if (!run || !/^[a-f0-9]{12}$/.test(run)) throw new Error('RUNTIME_RUNNER_REQUIRED')
const owner = JSON.parse(readFileSync('/Users/saki/project/FitLog/.git/fitlog-runtime.lock/owner.json', 'utf8'))
if (owner.run_id !== run || owner.worktree !== fileURLToPath(new URL('..', import.meta.url)).replace(/\/$/, '') || typeof owner.branch !== 'string' || ['main', 'master'].includes(owner.branch)) throw new Error('RUNTIME_OWNER_MISMATCH')
process.kill(owner.pid, 0)
// Playwright 1.65 otherwise writes an aria snapshot into error-context.md.
process.env.PLAYWRIGHT_NO_COPY_PROMPT = '1'

export default defineConfig({
  testDir: './specs', workers: 1, fullyParallel: false, retries: 0,
  timeout: 120_000, globalTimeout: 900_000,
  expect: { timeout: 10_000 },
  outputDir: `.artifacts/${run}/playwright`, preserveOutput: 'never',
  reporter: [['./support/reporter.ts']],
  use: { browserName: 'chromium', baseURL: 'http://127.0.0.1:15173',
    locale: 'ja-JP', timezoneId: 'Asia/Tokyo', viewport: { width: 1280, height: 800 },
    actionTimeout: 10_000, navigationTimeout: 10_000,
    trace: 'off', screenshot: 'off', video: 'off', serviceWorkers: 'block' },
})
