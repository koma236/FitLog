import { expect } from '@playwright/test'
import { spawnSync } from 'node:child_process'
import { api, type Actor } from './app.js'
import { aws, ORIGIN, requestApi, savePrivate, sendBudget } from './environment.js'
import { measure, assertPerformanceState } from '../../perf/aws-load.mjs'
import { unchangedRecord } from './aws-oracles.mjs'

const results: Record<string, { status: string; started?: string; finished?: string }> = Object.fromEntries(['C01', 'C02', 'C03', 'C04', 'C05', 'C06', 'C07'].map(id => [id, { status: 'not_run' }]))
export function awsResult(id: string, status: string) {
  if (!aws) return
  const previous = results[id]
  results[id] = { ...previous, status, ...(status === 'running' ? { started: new Date().toISOString() } : { finished: new Date().toISOString() }) }
  savePrivate('aws-results', results)
}
export async function awsCase(id: string, work: () => Promise<void>) {
  awsResult(id, 'running')
  try { await work(); awsResult(id, 'pass') }
  catch { awsResult(id, 'fail'); throw Error('AWS_CASE_FAILED') }
}

export async function securityAndHealth(a: Actor, b: Actor, post: string, payload: Record<string, unknown>) {
  await awsCase('C02', async () => {
    for (const actor of [a, b]) {
      const cookies = await actor.context.cookies(ORIGIN)
      for (const name of ['sessionid', 'csrftoken']) {
        const value = cookies.find(c => c.name === name)
        expect(Boolean(value && value.secure && value.httpOnly && value.sameSite === 'Lax' && value.path === '/' && value.domain === new URL(ORIGIN).hostname)).toBe(true)
      }
    }
    const before = await api(a, '/api/posts/' + post)
    const csrf = await (await requestApi(a.context.request, '/api/auth/csrf')).json()
    const response = await requestApi(a.context.request, '/api/posts/' + post, { method: 'PUT',
      headers: { Origin: 'https://origin-probe.invalid', 'X-CSRFToken': csrf.csrf_token, 'X-Record-Owner': a.id, 'Content-Type': 'application/json' }, data: payload })
    expect(response.status()).toBe(403)
    expect((await response.json()).code).toBe('CSRF_FAILED')
    const after = await api(a, '/api/posts/' + post)
    expect(unchangedRecord(after.body)).toEqual(unchangedRecord(before.body))
    // Positive contrast uses the same body and the correct Origin/CSRF/session.
    expect((await api(a, '/api/posts/' + post, 'PUT', { ...payload, note: before.body.note })).status).toBe(200)
  })
  await awsCase('C03', async () => {
    for (const path of ['/api/health/live', '/api/health/ready']) {
      const response = await requestApi(a.context.request, path)
      expect(response.status()).toBe(200)
      expect(await response.json()).toEqual({ status: 'ok' })
    }
  })
  savePrivate('storage-evidence', { public_http_health: 'pass', rds_reference: 'pass', s3_reference: aws?.storage_evidence_ready ? 'pass' : 'not_run' })
  if (!aws?.storage_evidence_ready) awsResult('C03', 'not_run')
}

export async function performanceProbe(actors: Actor[], ids: string[]) {
  await awsCase('C06', async () => {
    const paths = ['/api/timeline/all?limit=20', '/api/timeline/following?limit=20']
    const posts = ids.map((id, i) => ({ id, owner_id: actors[i].id, date: '2026-01-15' }))
    const following: string[][] = []
    for (const actor of actors) {
      expect((await api(actor, '/api/auth/me')).body.id).toBe(actor.id)
      const data = (await api(actor, paths[1])).body
      following.push(data.items.map((item: { id: string }) => item.id))
    }
    assertPerformanceState(actors, posts, following)
    const detail = (await api(actors[1], '/api/posts/' + ids[1])).body
    expect(detail.image).toBeNull()
    let recorded: unknown[] = []
    const rows = await measure(async (index: number, kind: string) => {
      const actor = actors[index]
      const pathname = kind === 'all' ? paths[0] : kind === 'following' ? paths[1] : '/api/posts/' + ids[1]
      const began = performance.now()
      const response = await requestApi(actor.context.request, pathname)
      const raw = await response.body()
      const elapsed_ms = performance.now() - began
      await response.dispose()
      if (raw.length > 16 * 1024 * 1024) throw Error('BODY_LIMIT')
      const body = JSON.parse(raw.toString())
      expect(response.status()).toBe(200); expect(body.viewer_id).toBe(actor.id)
      if (kind === 'detail') {
        expect(body.id).toBe(ids[1]); expect(body.author.id).toBe(actors[1].id)
        expect(body.is_owner).toBe(index === 1); expect(body.note).toBe(detail.note)
      } else {
        // E03 creates A fully before B; API orders created_at DESC then UUID DESC.
        const expected = kind === 'all' ? [ids[1], ids[0]] : [ids[index]]
        expect(body.items.map((item: { id: string }) => item.id)).toEqual(expected)
        expect(body.next_cursor).toBeNull()
        for (const item of body.items) expect(item.viewer_id).toBe(actor.id)
      }
      return { status: response.status(), elapsed_ms }
    }, { observe: (value: unknown[]) => { recorded = value; savePrivate('performance-requests', recorded) } })
    const report = spawnSync('python3', ['-B', '-m', 'perf.aws_report'], { input: JSON.stringify(rows), encoding: 'utf8', timeout: 10000, maxBuffer: 1024 * 1024 })
    if (report.status !== 0) throw Error('PERFORMANCE_REPORT_FAILED')
    savePrivate('performance', JSON.parse(report.stdout))
  })
}

export function cleanupPhase() { sendBudget?.cleanup() }
