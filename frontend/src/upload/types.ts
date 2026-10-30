export type ImageAsset = { id: string; url: string; expires_at: string; width: number; height: number; content_type: 'image/png' | 'image/jpeg' }
export function validImage(value: unknown): value is ImageAsset | null {
  if (value === null) return true
  if (typeof value !== 'object' || Array.isArray(value)) return false
  const v = value as Record<string, unknown>
  return Object.keys(v).length === 6 && ['id', 'url', 'expires_at'].every(k => typeof v[k] === 'string') && typeof v.id === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(v.id) && typeof v.url === 'string' && (v.url.startsWith('/') && !v.url.startsWith('//') || v.url.startsWith('https://')) && typeof v.expires_at === 'string' && Number.isFinite(Date.parse(v.expires_at)) && ['width', 'height'].every(k => typeof v[k] === 'number' && Number.isInteger(v[k]) && v[k] > 0 && v[k] <= 20000000) && (v.content_type === 'image/png' || v.content_type === 'image/jpeg')
}
export function fileError(file: File, avatar: boolean): string {
  if (!['image/png', 'image/jpeg'].includes(file.type)) return 'PNGまたはJPEGを選択してください。'
  if (file.size > (avatar ? 2 : 5) * 1024 * 1024) return `${avatar ? '2' : '5'}MiB以下の画像を選択してください。`
  return ''
}
