import { ApiError } from '../auth/api'
export async function writeImage(path: string, actor: string, avatar: boolean, csrf: string, file: File | null, operation: string, signal: AbortSignal): Promise<unknown> {
  const controller = new AbortController(); const abort = () => { controller.abort() }
  signal.addEventListener('abort', abort, { once: true }); if (signal.aborted) abort()
  const timeout = window.setTimeout(abort, 45000)
  const headers: Record<string, string> = { Accept: 'application/json', 'X-CSRFToken': csrf, [avatar ? 'X-Profile-Owner' : 'X-Record-Owner']: actor }
  let body: FormData | undefined
  if (file) { headers['X-Image-Operation'] = operation; body = new FormData(); body.append('image', file) }
  try {
    const response = await fetch(path, { method: file ? 'PUT' : 'DELETE', body, headers, signal: controller.signal, credentials: 'same-origin', cache: 'no-store' })
    if (!file && response.status === 204) return null
    let data: unknown
    try { data = await response.json() } catch { throw new ApiError(response.status, 'INVALID_RESPONSE', '画像の保存結果を確認できません。') }
    if (!response.ok) {
      const v = typeof data === 'object' && data !== null ? data as Record<string, unknown> : {}
      throw new ApiError(response.status, typeof v.code === 'string' ? v.code : '', typeof v.message === 'string' ? v.message : '画像を保存できません。')
    }
    if (response.status !== 200) throw new ApiError(response.status, 'INVALID_RESPONSE', '画像の保存結果を確認できません。')
    if (typeof data === 'object' && data !== null && 'viewer_id' in data && data.viewer_id !== actor) throw new ApiError(409, avatar ? 'PROFILE_OWNER_CHANGED' : 'RECORD_OWNER_CHANGED', 'ログインしているユーザーが変わりました。画像を選び直してください。')
    return data
  } catch (error) { if (error instanceof ApiError) throw error; throw new ApiError(0, 'NETWORK_ERROR', '画像の保存結果を確認できません。') }
  finally { window.clearTimeout(timeout); signal.removeEventListener('abort', abort) }
}
