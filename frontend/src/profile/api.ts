import { validImage } from '../upload/types'
import { ApiError } from '../auth/api'
import { energyKeys, healthKeys, profileKeys } from './types'
import type { Profile } from './types'

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
function exactKeys(value: Record<string, unknown>, allowed: readonly string[], required = allowed): boolean {
  return Object.keys(value).every(key => allowed.includes(key)) && required.every(key => Object.hasOwn(value, key))
}
export function validProfile(value: unknown, actor: string): value is Profile {
  if (!record(value) || typeof value.is_owner !== 'boolean') return false
  const keys = ['viewer_id', 'avatar', 'id', 'username', 'display_name', 'bio', 'is_owner', 'health', 'energy', ...(value.is_owner ? ['visibility'] : [])]
  if (value.viewer_id !== actor || !validImage(value.avatar) || !exactKeys(value, keys) || !['id', 'username', 'display_name', 'bio'].every(key => typeof value[key] === 'string') || value.is_owner !== (value.id === actor)) return false
  if (!record(value.health) || !record(value.energy) || !exactKeys(value.health, healthKeys, value.is_owner ? healthKeys : []) || !exactKeys(value.energy, energyKeys, value.is_owner ? energyKeys : [])) return false
  for (const [key, item] of Object.entries(value.health)) {
    if (item === null) continue
    if (key === 'age') { if (typeof item !== 'number' || !Number.isInteger(item) || item < 0 || item > 120) return false }
    else if (key === 'formula') { if (item !== 'male' && item !== 'female') return false }
    else if (key === 'activity') { if (item !== 'low' && item !== 'medium' && item !== 'high') return false }
    else if (typeof item !== 'string' || !/^[1-9][0-9]{1,2}\.[0-9]$/.test(item)) return false
  }
  if (!Object.values(value.energy).every(item => item === null || (typeof item === 'number' && Number.isSafeInteger(item) && item > 0))) return false
  if (value.is_owner && (!record(value.visibility) || !exactKeys(value.visibility, profileKeys) || !Object.values(value.visibility).every(flag => flag === 'public' || flag === 'private'))) return false
  return true
}
async function request(target: string, actor: string, init: RequestInit, signal?: AbortSignal): Promise<Profile> {
  const controller = new AbortController()
  const abort = () => { controller.abort() }
  signal?.addEventListener('abort', abort, { once: true })
  if (signal?.aborted) controller.abort()
  const timeout = window.setTimeout(abort, 10000)
  try {
    const response = await fetch(`/api/users/${encodeURIComponent(target)}`, { ...init, signal: controller.signal, cache: 'no-store', credentials: 'same-origin' })
    let value: unknown
    try { value = await response.json() } catch { throw new ApiError(response.status, 'INVALID_RESPONSE', '応答を確認できません。') }
    if (!response.ok) {
      const fields: Record<string, string[]> = {}
      if (record(value) && record(value.fieldErrors)) {
        for (const [key, item] of Object.entries(value.fieldErrors)) if (Array.isArray(item) && item.every((part: unknown) => typeof part === 'string')) fields[key] = item
      }
      throw new ApiError(response.status, record(value) && typeof value.code === 'string' ? value.code : '', record(value) && typeof value.message === 'string' ? value.message : '応答を確認できません。', fields)
    }
    if (record(value) && typeof value.viewer_id === 'string' && value.viewer_id !== actor) throw new ApiError(409, 'PROFILE_OWNER_CHANGED', 'ログインしているユーザーが変わりました。')
    if (response.status !== 200 || !validProfile(value, actor)) throw new ApiError(response.status, 'INVALID_RESPONSE', '応答を確認できません。')
    return value
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError(0, signal?.aborted ? 'ABORTED' : 'NETWORK_ERROR', '処理結果を確認できません。保存状態を読み直してください。')
  } finally {
    window.clearTimeout(timeout); signal?.removeEventListener('abort', abort)
  }
}
export async function getProfile(target: string, actor: string, signal: AbortSignal): Promise<Profile> {
  const profile = await request(target, actor, { headers: { Accept: 'application/json' } }, signal)
  if (target === 'me' ? !profile.is_owner : profile.username !== target) throw new ApiError(200, 'INVALID_RESPONSE', '応答を確認できません。')
  return profile
}
export async function saveProfile(data: Record<string, unknown>, owner: string, csrf: string, signal: AbortSignal): Promise<Profile> {
  const profile = await request('me', owner, { method: 'PUT', headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': csrf, 'X-Profile-Owner': owner }, body: JSON.stringify(data) }, signal)
  if (!profile.is_owner || profile.id !== owner) throw new ApiError(200, 'INVALID_RESPONSE', '応答を確認できません。')
  return profile
}
