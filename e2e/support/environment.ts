/** Runtime-produced, non-secret input. Local mode is never enabled by an URL. */
import { readFileSync, realpathSync, statSync, writeFileSync, renameSync } from 'node:fs'
import path from 'node:path'
import { ORIGIN as LOCAL_ORIGIN } from './safety.mjs'
import { SendBudget, urlPolicy, apiSend, nativeBodyBytes } from './aws-policy.mjs'
import type { APIRequestContext } from '@playwright/test'

const input = process.env.FITLOG_AWS_INPUT
export const isAws = Boolean(input)
export const runId = process.env.FITLOG_E2E_RUN_ID!
export const artifact = process.env.FITLOG_AWS_OUTPUT ?? path.resolve(import.meta.dirname, '../.artifacts', runId ?? 'invalid')
export function savePrivate(name: string, data: unknown) {
  if (!/^[a-z0-9-]+\.json$/.test(name)) throw Error('ARTIFACT_NAME_INVALID')
  const target = path.join(artifact, name); const temporary = target + '.tmp'
  writeFileSync(temporary, JSON.stringify(data, null, 2), { mode: 0o600, flag: 'wx' })
  renameSync(temporary, target)
}

function loadAws() {
  if (!input) return null
  const s = statSync(input)
  if (realpathSync(input) !== input || !s.isFile() || (s.mode & 0o777) !== 0o600 || s.uid !== process.getuid?.() || path.dirname(input) !== artifact) throw Error('AWS_RUNTIME_REQUIRED')
  const value = JSON.parse(readFileSync(input, 'utf8'))
  const owner = JSON.parse(readFileSync('/Users/saki/project/FitLog/.git/fitlog-runtime.lock/owner.json', 'utf8'))
  if (value.test_run !== runId || owner.run_id !== runId || owner.worktree !== path.resolve(import.meta.dirname, '../..') || value.mode !== 'aws' || value.origin !== value.contract.origin) throw Error('AWS_RUNTIME_REQUIRED')
  process.kill(owner.pid, 0)
  urlPolicy(value.origin)
  if (Date.now() < Date.parse(value.contract.starts_at) || Date.now() >= Date.parse(value.contract.expires_at)) throw Error('AWS_DEADLINE')
  return value as { origin: string; test_run: string; mode: string; contract: { expires_at: string; starts_at: string }; final_evidence_ready: boolean; storage_evidence_ready: boolean }
}
export const aws = loadAws()
export const ORIGIN = aws?.origin ?? LOCAL_ORIGIN
export const sendBudget = aws ? new SendBudget({ expires: Date.parse(aws.contract.expires_at), persist: (state: unknown) => savePrivate('budget', state) }) : null
export const validateUrl = aws ? urlPolicy(ORIGIN) : null
export async function requestApi(request: APIRequestContext, pathname: string, options: { method?: string; headers?: Record<string, string>; data?: unknown } = {}) {
  if (aws && sendBudget) return apiSend(request, { origin: ORIGIN, budget: sendBudget }, pathname, options)
  return request.fetch(ORIGIN + pathname, { ...options, maxRedirects: 0 })
}

/** Byte-exact native payload accounting; unknown bodies are never guessed. */
export function reserveNative(event: { request: { method: string; url: string; hasPostData?: boolean; postData?: string; postDataEntries?: { bytes?: string }[] } }) {
  const r = event.request
  if (!sendBudget) throw Error('AWS_RUNTIME_REQUIRED')
  sendBudget.take(r.method, r.url, nativeBodyBytes(r))
}
