import { ApiError } from '../auth/api'
import { validImage } from '../upload/types'
import type { ImageAsset } from '../upload/types'
import { socialRequest } from './api'

export type Relation = { is_following: boolean; follower_count: number; following_count: number }
export type SearchUser = Relation & { id: string; username: string; display_name: string; avatar: ImageAsset | null; is_owner: boolean }
export type SearchPage = { viewer_id: string; items: SearchUser[]; next_cursor: string | null }
export type FollowResult = Relation & { viewer_id: string; user_id: string }
function object(v: unknown): v is Record<string, unknown> { return typeof v === 'object' && v !== null && !Array.isArray(v) }
function keys(v: Record<string, unknown>, names: string[]) { return Object.keys(v).length === names.length && names.every(k => Object.hasOwn(v, k)) }
const uuid = (v: unknown) => typeof v === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(v)
export function validRelation(v: Record<string, unknown>): boolean {
  return typeof v.is_following === 'boolean' && [v.follower_count, v.following_count].every(n => typeof n === 'number' && Number.isSafeInteger(n) && n >= 0)
}
function validUser(v: unknown, actor: string): v is SearchUser {
  return object(v) && keys(v, ['id', 'username', 'display_name', 'avatar', 'is_owner', 'is_following', 'follower_count', 'following_count']) && uuid(v.id) && typeof v.username === 'string' && /^[a-z0-9_]{3,30}$/.test(v.username) && typeof v.display_name === 'string' && validImage(v.avatar) && v.is_owner === (v.id === actor) && validRelation(v) && (!v.is_owner || v.is_following === false)
}
export async function searchUsers(q: string, actor: string, signal: AbortSignal, cursor?: string): Promise<SearchPage> {
  const params = new URLSearchParams({ q }); if (cursor !== undefined) params.set('cursor', cursor)
  const v = await socialRequest('users/search?' + params.toString(), actor, signal)
  if (!object(v) || !keys(v, ['viewer_id', 'items', 'next_cursor']) || v.viewer_id !== actor || !Array.isArray(v.items) || !v.items.every(item => validUser(item, actor)) || new Set(v.items.map(item => item.id)).size !== v.items.length || (v.next_cursor !== null && (typeof v.next_cursor !== 'string' || !v.next_cursor || v.next_cursor.length > 2048 || !/^[\x20-\x7e]+$/.test(v.next_cursor)))) throw new ApiError(200, 'INVALID_RESPONSE', '検索結果を確認できません。')
  return v as SearchPage
}
export async function writeFollow(id: string, following: boolean, actor: string, csrf: string, signal: AbortSignal): Promise<FollowResult> {
  const v = await socialRequest('users/' + encodeURIComponent(id) + '/follow', actor, signal, following ? 'POST' : 'DELETE', csrf)
  if (!object(v) || !keys(v, ['viewer_id', 'user_id', 'is_following', 'follower_count', 'following_count']) || v.viewer_id !== actor || v.user_id !== id || v.is_following !== following || !validRelation(v)) throw new ApiError(200, 'INVALID_RESPONSE', 'フォローの状態を確認できません。')
  return v as FollowResult
}
