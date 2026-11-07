import { execFileSync } from 'node:child_process'
import { saveArtifact } from './private-artifacts.mjs'

export function browserIdentity(pid) {
  const value = execFileSync('ps', ['-p', String(pid), '-o', 'lstart=', '-o', 'pgid='], { encoding: 'utf8', timeout: 2000, env: { ...process.env, LC_ALL: 'C', TZ: 'UTC' } }).trim()
  const match = /^(.+?)\s+(\d+)$/.exec(value)
  if (!match || Number(match[2]) !== pid) throw Error('BROWSER_IDENTITY_UNKNOWN')
  return { birth: match[1].trim(), pgid: Number(match[2]) }
}

/** Default Chromium pipe transport: no launchServer or extra listening port. */
export async function launchOwnedBrowser(type, directory, run, worker, { identity = browserIdentity, launchOptions = {} } = {}) {
  const name = 'browser-worker-' + worker
  const row = { schema_version: 1, run_id: run, node_pid: process.pid, phase: 'launching', pid: null, pgid: null, birth: null }
  saveArtifact(directory, name, row)
  let browser
  try {
    browser = await type.launch(launchOptions)
    const session = await browser.newBrowserCDPSession()
    const data = await session.send('SystemInfo.getProcessInfo')
    await session.detach()
    const processes = data.processInfo.filter(item => item.type === 'browser')
    if (processes.length !== 1 || !Number.isSafeInteger(processes[0].id) || processes[0].id <= 1) throw Error('BROWSER_IDENTITY_UNKNOWN')
    const pid = processes[0].id
    Object.assign(row, identity(pid), { pid, phase: 'launched' })
    saveArtifact(directory, name, row)
    return browser
  } catch {
    // Parent retains the intent/lock if launch happened before identity persisted.
    await browser?.close().catch(() => {})
    throw Error('BROWSER_START_FAILED')
  }
}
