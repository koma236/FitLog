import { test as base, type Browser } from '@playwright/test'
import { isAws, artifact, runId, sendBudget } from './environment.js'
import { launchOwnedBrowser } from './owned-browser.mjs'

const owned = base.extend<{}, { browser: Browser }>({
  browser: [async ({ playwright }, use, worker) => {
    const browser = await launchOwnedBrowser(playwright.chromium, artifact, runId, worker.workerIndex)
    const unwatch = sendBudget!.watch(() => browser.close())
    try { await use(browser) }
    finally { unwatch(); await browser.close() }
  }, { scope: 'worker' }],
})
export const test = isAws ? owned : base
