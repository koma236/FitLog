import { ApiError } from '../auth/api'
import { validImage } from '../upload/types'
import type { Comment, CommentPage, CommentResult, LikeResult } from './types'
function object(v: unknown): v is Record<string, unknown> { return typeof v === 'object' && v !== null && !Array.isArray(v) }
function keys(v: Record<string, unknown>, names: string[]) { return Object.keys(v).length === names.length && names.every(k => Object.hasOwn(v, k)) }
function count(v: unknown) { return typeof v === 'number' && Number.isSafeInteger(v) && v >= 0 }
function validComment(v: unknown, actor: string): v is Comment {
  return object(v) && keys(v, ['id', 'post_id', 'body', 'created_at', 'updated_at', 'author', 'is_owner']) && ['id', 'post_id', 'body', 'created_at', 'updated_at'].every(k => typeof v[k] === 'string') && object(v.author) && keys(v.author, ['id', 'username', 'display_name', 'avatar']) && ['id', 'username', 'display_name'].every(k => object(v.author) && typeof v.author[k] === 'string') && validImage(v.author.avatar) && v.is_owner === (v.author.id === actor)
}
async function request(path: string, actor: string, signal: AbortSignal, method = 'GET', csrf = '', data?: Record<string, unknown>): Promise<unknown> {
  const controller = new AbortController(); const abort = () => { controller.abort() }
  signal.addEventListener('abort', abort, { once: true }); if (signal.aborted) abort()
  const timer = window.setTimeout(abort, 10000)
  try {
    const headers: Record<string, string> = { Accept: 'application/json' }
    if (method !== 'GET') Object.assign(headers, { 'X-Social-Owner': actor, 'X-CSRFToken': csrf, ...(data ? { 'Content-Type': 'application/json' } : {}) })
    const response = await fetch('/api/' + path, { method, headers, signal: controller.signal, credentials: 'same-origin', cache: 'no-store', ...(data ? { body: JSON.stringify(data) } : {}) })
    if (method === 'DELETE' && path.startsWith('comments/') && response.status === 204) return null
    let v: unknown
    try { v = await response.json() } catch { throw new ApiError(response.status, 'INVALID_RESPONSE', '処理結果を確認できません。') }
    if (!response.ok) {
      const fields: Record<string, string[]> = {}
      if (object(v) && object(v.fieldErrors)) for (const [k, value] of Object.entries(v.fieldErrors)) if (Array.isArray(value) && value.every(x => typeof x === 'string')) fields[k] = value
      throw new ApiError(response.status, object(v) && typeof v.code === 'string' ? v.code : '', object(v) && typeof v.message === 'string' ? v.message : '操作できません。', fields)
    }
    if (response.status !== (method === 'POST' && path.endsWith('/comments') ? 201 : 200)) throw new ApiError(response.status, 'INVALID_RESPONSE', '処理結果を確認できません。')
    if (object(v) && typeof v.viewer_id === 'string' && v.viewer_id !== actor) throw new ApiError(409, 'SOCIAL_OWNER_CHANGED', 'ログインしているユーザーが変わりました。開き直してください。')
    return v
  } catch (error) { if (error instanceof ApiError) throw error; throw new ApiError(0, signal.aborted ? 'ABORTED' : 'NETWORK_ERROR', '処理結果を確認できません。') }
  finally { clearTimeout(timer); signal.removeEventListener('abort', abort) }
}
function result(v: unknown, actor: string, post: string, id?: string): CommentResult {
  if (!object(v) || !keys(v, ['viewer_id', 'post_id', 'comment_count', 'comment']) || v.viewer_id !== actor || v.post_id !== post || !count(v.comment_count) || !validComment(v.comment, actor) || v.comment.post_id !== post || id !== undefined && v.comment.id !== id) throw new ApiError(200, 'INVALID_RESPONSE', '処理結果を確認できません。')
  return v as CommentResult
}
export async function listComments(post: string, actor: string, signal: AbortSignal, cursor?: string): Promise<CommentPage> {
  const v = await request('posts/' + encodeURIComponent(post) + '/comments' + (cursor ? '?cursor=' + encodeURIComponent(cursor) : ''), actor, signal)
  if (!object(v) || !keys(v, ['viewer_id', 'post_id', 'comment_count', 'items', 'next_cursor']) || v.viewer_id !== actor || v.post_id !== post || !count(v.comment_count) || !Array.isArray(v.items) || !v.items.every(x => validComment(x, actor) && x.post_id === post) || (v.next_cursor !== null && typeof v.next_cursor !== 'string')) throw new ApiError(200, 'INVALID_RESPONSE', 'コメントを確認できません。')
  return v as CommentPage
}
export async function getComment(id: string, post: string, actor: string, signal: AbortSignal) { return result(await request('comments/' + encodeURIComponent(id), actor, signal), actor, post, id) }
export async function writeComment(post: string, id: string, action: 'create' | 'update' | 'delete', body: string, actor: string, csrf: string, signal: AbortSignal): Promise<CommentResult | null> {
  const v = await request(action === 'create' ? 'posts/' + encodeURIComponent(post) + '/comments' : 'comments/' + encodeURIComponent(id), actor, signal, action === 'create' ? 'POST' : action === 'update' ? 'PUT' : 'DELETE', csrf, action === 'create' ? { id, body } : action === 'update' ? { body } : undefined)
  if (action === 'delete' && v === null) return null
  const value = result(v, actor, post, id)
  if (!value.comment.is_owner || value.comment.body !== body) throw new ApiError(200, 'INVALID_RESPONSE', '処理結果を確認できません。')
  return value
}
export async function writeLike(post: string, liked: boolean, actor: string, csrf: string, signal: AbortSignal): Promise<LikeResult> {
  const v = await request('posts/' + encodeURIComponent(post) + '/like', actor, signal, liked ? 'POST' : 'DELETE', csrf)
  if (!object(v) || !keys(v, ['viewer_id', 'post_id', 'is_liked', 'like_count']) || v.viewer_id !== actor || v.post_id !== post || v.is_liked !== liked || !count(v.like_count)) throw new ApiError(200, 'INVALID_RESPONSE', 'いいねの状態を確認できません。')
  return v as LikeResult
}
// Match the server's CRLF conversion and Python strip without stripping FEFF.
export function normalizeBody(body: string) {
  const converted = body.replace(/\r\n/g, '\n')
  for (const char of converted) { const code = char.codePointAt(0) ?? 0; if (code < 32 && code !== 9 && code !== 10 || code === 127 || code >= 0xd800 && code <= 0xdfff) throw new ApiError(400, 'VALIDATION_ERROR', '使用できない文字が含まれています。') }
  return converted.replace(/^[\t\n \u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+|[\t\n \u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/g, '')
}
