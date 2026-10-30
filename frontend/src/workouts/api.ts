import { validImage } from '../upload/types'
import { ApiError } from '../auth/api'
import type { Page, Workout } from './types'

function object(v: unknown): v is Record<string, unknown> { return typeof v === 'object' && v !== null && !Array.isArray(v) }
function keys(v: Record<string, unknown>, allowed: string[], required = allowed) { return Object.keys(v).every(k => allowed.includes(k)) && required.every(k => Object.hasOwn(v, k)) }
export function validPost(v: unknown, actor: string): v is Workout {
  if (!object(v) || !object(v.author) || !keys(v.author, ['id', 'username', 'display_name', 'avatar']) || !['id', 'username', 'display_name'].every(k => typeof v.author === 'object' && v.author !== null && typeof (v.author as Record<string, unknown>)[k] === 'string') || !validImage(v.author.avatar) || !validImage(v.image)) return false
  const owner = v.author.id === actor
  if (!keys(v, ['image', 'viewer_id', 'id', 'author', 'is_owner', 'performed_on', 'note', 'created_at', 'updated_at', 'exercises', 'energy', 'energy_input', ...(owner ? ['visibility'] : [])]) || v.is_owner !== owner || v.viewer_id !== actor) return false
  if (!['id', 'performed_on', 'note', 'created_at', 'updated_at'].every(k => typeof v[k] === 'string') || !object(v.energy_input) || !keys(v.energy_input, ['minutes', 'kind'], owner ? ['minutes', 'kind'] : [])) return false
  const { minutes, kind } = v.energy_input
  if (minutes !== undefined && minutes !== null && (typeof minutes !== 'number' || !Number.isInteger(minutes) || minutes < 1 || minutes > 240)) return false
  if (kind !== undefined && kind !== null && (typeof kind !== 'string' || !['general', 'squat', 'vigorous'].includes(kind))) return false
  if (!owner && (minutes === null || kind === null)) return false
  if (owner && (!object(v.visibility) || !keys(v.visibility, ['minutes', 'kind']) || !Object.values(v.visibility).every(x => x === 'public' || x === 'private'))) return false
  if (v.energy !== null && (!object(v.energy) || !keys(v.energy, ['kcal', 'method']) || v.energy.method !== 'met-gross-v1' || typeof v.energy.kcal !== 'number' || !Number.isSafeInteger(v.energy.kcal) || v.energy.kcal < 1)) return false
  return Array.isArray(v.exercises) && v.exercises.length >= 1 && v.exercises.length <= 10 && v.exercises.every((ex: unknown) => object(ex) && keys(ex, ['name', 'sets']) && typeof ex.name === 'string' && Array.isArray(ex.sets) && ex.sets.length >= 1 && ex.sets.length <= 20 && ex.sets.every((row: unknown) => object(row) && keys(row, ['weight_kg', 'reps']) && typeof row.weight_kg === 'string' && /^(0|[1-9][0-9]{0,2})\.[0-9]{2}$/.test(row.weight_kg) && typeof row.reps === 'number' && Number.isInteger(row.reps) && row.reps >= 1 && row.reps <= 999))
}
async function request(path: string, actor: string, signal: AbortSignal, method = 'GET', data?: Record<string, unknown>, csrf = ''): Promise<unknown> {
  const controller = new AbortController(); const abort = () => { controller.abort() }
  signal.addEventListener('abort', abort, { once: true }); if (signal.aborted) abort()
  const timeout = window.setTimeout(abort, 10000)
  try {
    const headers: Record<string, string> = { Accept: 'application/json' }
    if (method !== 'GET') Object.assign(headers, { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, 'X-Record-Owner': actor })
    const response = await fetch('/api/' + path, { method, headers, signal: controller.signal, credentials: 'same-origin', cache: 'no-store', ...(data ? { body: JSON.stringify(data) } : {}) })
    if (response.status === 204 && method === 'DELETE') return null
    let value: unknown
    try { value = await response.json() } catch { throw new ApiError(response.status, 'INVALID_RESPONSE', '保存できたか確認できません。保存状態を確認してください。') }
    if (!response.ok) {
      const fields: Record<string, string[]> = {}
      if (object(value) && object(value.fieldErrors)) for (const [k, item] of Object.entries(value.fieldErrors)) if (Array.isArray(item) && item.every((x: unknown) => typeof x === 'string')) fields[k] = item
      throw new ApiError(response.status, object(value) && typeof value.code === 'string' ? value.code : '', object(value) && typeof value.message === 'string' ? value.message : '入力を確認してください。', fields)
    }
    if (response.status !== (method === 'POST' ? 201 : 200)) throw new ApiError(response.status, 'INVALID_RESPONSE', '応答を確認できません。')
    if (object(value) && typeof value.viewer_id === 'string' && value.viewer_id !== actor) throw new ApiError(409, 'RECORD_OWNER_CHANGED', 'ログインしているユーザーが変わりました。記録を開き直してください。')
    return value
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError(0, signal.aborted ? 'ABORTED' : 'NETWORK_ERROR', '保存できたか確認できません。保存状態を確認してください。')
  } finally { window.clearTimeout(timeout); signal.removeEventListener('abort', abort) }
}
export async function getWorkout(id: string, actor: string, signal: AbortSignal): Promise<Workout> {
  const v = await request('posts/' + encodeURIComponent(id), actor, signal)
  if (!validPost(v, actor) || v.id !== id) throw new ApiError(200, 'INVALID_RESPONSE', '応答を確認できません。')
  return v
}
export async function listWorkouts(username: string, actor: string, signal: AbortSignal, cursor?: string): Promise<Page> {
  const v = await request('users/' + encodeURIComponent(username) + '/posts' + (cursor ? '?cursor=' + encodeURIComponent(cursor) : ''), actor, signal)
  if (!object(v) || v.viewer_id !== actor || !keys(v, ['viewer_id', 'items', 'next_cursor']) || !Array.isArray(v.items) || !v.items.every((x: unknown) => validPost(x, actor)) || (v.next_cursor !== null && typeof v.next_cursor !== 'string')) throw new ApiError(200, 'INVALID_RESPONSE', '応答を確認できません。')
  return v as Page
}
export async function writeWorkout(id: string | null, actor: string, csrf: string, data: Record<string, unknown> | null, signal: AbortSignal): Promise<Workout | null> {
  const v = await request('posts' + (id ? '/' + encodeURIComponent(id) : ''), actor, signal, data === null ? 'DELETE' : id ? 'PUT' : 'POST', data ?? undefined, csrf)
  if (data === null && v === null) return null
  if (!validPost(v, actor) || !v.is_owner || v.id !== (id ?? data?.id)) throw new ApiError(200, 'INVALID_RESPONSE', '保存できたか確認できません。保存状態を確認してください。')
  return v
}
