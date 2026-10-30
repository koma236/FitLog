import { StrictMode, useState } from 'react'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import ImageEditor from './ImageEditor'
import App from '../App'
import Photo from './Photo'
import WorkoutScreen from '../workouts/WorkoutScreen'
import WorkoutFeed from '../workouts/WorkoutFeed'
import ProfileScreen from '../profile/ProfileScreen'
import type { ImageAsset } from './types'
import type { Workout } from '../workouts/types'
import { privateFlags } from '../profile/types'

const account = { id: '11111111-1111-4111-8111-111111111111', username: 'river', display_name: 'River', email: 'river@example.test' }
const postId = '33333333-3333-4333-8333-333333333333'
const oldId = '44444444-4444-4444-8444-444444444444'
const image = (id: string, url = '/media/' + id): ImageAsset => ({ id, url, expires_at: '2030-01-01T00:00:00Z', width: 2, height: 3, content_type: 'image/png' })
const post = (attachment: ImageAsset | null = null): Workout => ({ viewer_id: account.id, id: postId, image: attachment, author: { id: account.id, username: 'river', display_name: 'River', avatar: null }, is_owner: true, performed_on: '2026-10-29', note: '', created_at: '2026-10-29T00:00:00Z', updated_at: '2026-10-29T00:00:00Z', exercises: [{ name: 'ベンチプレス', sets: [{ weight_kg: '60.00', reps: 10 }] }], energy_input: { minutes: null, kind: null }, energy: null, visibility: { minutes: 'private', kind: 'private' } })
const profile = () => ({ viewer_id: account.id, id: account.id, avatar: null, username: 'river', display_name: 'River', bio: '', is_owner: true, health: { height: null, weight: null, age: null, formula: null, activity: null }, energy: { bmr: null, tdee: null, intake: null }, visibility: privateFlags() })
function reply(status: number, data: unknown = null) { return new Response(status === 204 ? null : JSON.stringify(data), { status }) }
type Handler = (url: string, init: RequestInit) => Response | Promise<Response>
function network(handler: Handler) {
  const fetcher = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    if (url === '/api/auth/me') return reply(200, account)
    if (url === '/api/auth/csrf') return reply(200, { csrf_token: 'csrf-current' })
    return handler(url, init)
  })
  vi.stubGlobal('fetch', fetcher)
  return fetcher
}
const photo = () => new File(['fixed synthetic pixels'], 'photo.png', { type: 'image/png' })
const identity = vi.fn()
const busy = vi.fn()
function editor() { return render(<ImageEditor account={account} postId={postId} image={image(oldId)} onImage={vi.fn()} onIdentity={identity} onBusy={busy} onWorking={vi.fn()} />) }
function select() { fireEvent.change(screen.getByLabelText('記録画像を選択'), { target: { files: [photo()] } }) }
const createPreview = vi.fn(() => 'blob:preview')
const revokePreview = vi.fn()
beforeEach(() => { vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: createPreview, revokeObjectURL: revokePreview })) })
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.clearAllMocks(); vi.useRealTimers(); location.hash = '' })
it('keeps the saved record after upload failure and retries only its image with the same file and operation', async () => {
  let recordWrites = 0; let uploads = 0; let operation = ''; let sentFile: FormDataEntryValue | null = null
  network((url, init) => {
    if (url === '/api/users/me') return reply(200, profile())
    if (url === '/api/posts') { recordWrites++; const data = JSON.parse(typeof init.body === 'string' ? init.body : '{}') as Record<string, unknown>; return reply(201, { ...post(), id: data.id }) }
    if (url.endsWith('/image')) {
      uploads++; const headers = new Headers(init.headers); const body = init.body as FormData
      // FL-05 approved design §3: exactly one multipart field named image.
      expect([...body.keys()]).toEqual(['image'])
      expect(headers.get('X-CSRFToken')).toBe('csrf-current'); expect(headers.get('X-Record-Owner')).toBe(account.id); expect(headers.has('Content-Type')).toBe(false)
      expect(init.cache).toBe('no-store'); expect(init.credentials).toBe('same-origin')
      if (uploads === 1) { operation = headers.get('X-Image-Operation') ?? ''; sentFile = body.get('image'); return reply(415, { code: 'IMAGE_INVALID', message: '画像を処理できません。' }) }
      expect(headers.get('X-Image-Operation')).toBe(operation); expect(body.get('image')).toBe(sentFile)
      return reply(200, { ...post(image(operation)), id: url.split('/')[3] })
    }
    throw new Error(url)
  })
  render(<WorkoutScreen account={account} id={null} initial={null} editing onIdentity={identity} onBusy={busy} onSaved={vi.fn()} onClearSaved={vi.fn()} onUncertain={vi.fn()} />)
  await screen.findByRole('button', { name: '記録する' })
  fireEvent.change(screen.getByLabelText('写真（任意）'), { target: { files: [photo()] } })
  fireEvent.click(screen.getByRole('button', { name: '記録する' }))
  expect(await screen.findByText('記録は保存済みです。写真の保存結果は下に表示します。')).toBeVisible()
  await screen.findByText('画像を処理できません。')
  expect(screen.queryByRole('button', { name: '記録する' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '画像だけ再試行' }))
  await screen.findByText('画像を保存しました。')
  expect(recordWrites).toBe(1); expect(uploads).toBe(2)
  expect(revokePreview).toHaveBeenCalled()
})
it.each([true, false])('resolves an ambiguous PUT only when the fetched image id matches: %s', async match => {
  let operation = ''; let puts = 0; let gets = 0
  network((_url, init) => {
    if (init.method === 'PUT') { puts++; operation = new Headers(init.headers).get('X-Image-Operation') ?? ''; return reply(500, { code: 'STORAGE_ERROR' }) }
    gets++; return reply(200, post(image(match ? operation : oldId)))
  })
  editor(); select(); fireEvent.click(screen.getByRole('button', { name: '画像を保存' }))
  if (match) await screen.findByText('画像を保存しました。')
  else { await screen.findByText('画像の保存結果を確定できません。現在の画像を表示しました。画像だけ再試行できます。'); expect(screen.queryByText('画像を保存しました。')).not.toBeInTheDocument(); expect(screen.getByRole('img', { name: '選択した画像のプレビュー' })).toBeVisible() }
  expect(puts).toBe(1); expect(gets).toBe(1)
})
it('refreshes CSRF once without automatic upload and keeps the operation for explicit retry', async () => {
  const operations: string[] = []
  const fetcher = network((_url, init) => { const operation = new Headers(init.headers).get('X-Image-Operation') ?? ''; operations.push(operation); return operations.length === 1 ? reply(403, { code: 'CSRF_FAILED' }) : reply(200, post(image(operation))) })
  editor(); select(); fireEvent.click(screen.getByRole('button', { name: '画像を保存' }))
  await screen.findByText('安全性の確認を更新しました。画像だけもう一度保存してください。')
  expect(operations).toHaveLength(1)
  fireEvent.click(screen.getByRole('button', { name: '画像だけ再試行' })); await screen.findByText('画像を保存しました。')
  expect(operations[1]).toBe(operations[0]); expect(fetcher.mock.calls.filter(([url]) => url === '/api/auth/csrf')).toHaveLength(2)
})
it('discards the preview on 401 and ignores an upload response after unmount', async () => {
  network(() => reply(401, { code: 'AUTH_REQUIRED' }))
  editor(); select(); fireEvent.click(screen.getByRole('button', { name: '画像を保存' }))
  await waitFor(() => { expect(identity).toHaveBeenCalledWith(null, expect.stringContaining("保存状態")); expect(screen.queryByRole('img')).not.toBeInTheDocument() })
   expect(revokePreview).toHaveBeenCalledWith('blob:preview')
  cleanup(); identity.mockClear()
  let finish: ((r: Response) => void) | undefined; let operation = ''
  network((_url, init) => { operation = new Headers(init.headers).get('X-Image-Operation') ?? ''; return new Promise<Response>(resolve => { finish = resolve }) })
  const changed = vi.fn(); const view = render(<ImageEditor account={account} postId={postId} image={null} onImage={changed} onIdentity={identity} onBusy={busy} onWorking={vi.fn()} />)
  select(); fireEvent.click(screen.getByRole('button', { name: '画像を保存' })); await waitFor(() => { expect(finish).toBeDefined() })
  view.unmount(); await act(async () => { finish?.(reply(200, post(image(operation)))); await Promise.resolve() })
  expect(changed).not.toHaveBeenCalled(); expect(identity).not.toHaveBeenCalled()
})
it('sends no File after detecting an account switch', async () => {
  const fetcher = network(() => { throw new Error('Image request must not be made') })
  fetcher.mockImplementation(() => Promise.resolve(reply(200, { ...account, id: '22222222-2222-4222-8222-222222222222' })))
  editor(); select(); fireEvent.click(screen.getByRole('button', { name: '画像を保存' }))
  await waitFor(() => { expect(identity).toHaveBeenCalled(); expect(screen.queryByRole('img')).not.toBeInTheDocument() })
  expect(fetcher).toHaveBeenCalledTimes(1)
})
it('preserves profile field drafts when saving an independent avatar', async () => {
  network((url, init) => {
    if (url.endsWith('/avatar')) { const operation = new Headers(init.headers).get('X-Image-Operation') ?? ''; expect(new Headers(init.headers).get('X-Profile-Owner')).toBe(account.id); return reply(200, { ...profile(), avatar: image(operation) }) }
    return reply(200, profile())
  })
  render(<ProfileScreen account={account} target="me" editing onIdentity={identity} onName={vi.fn()} onBusy={busy} />)
  fireEvent.change(await screen.findByLabelText('表示名'), { target: { value: '未保存の表示名' } })
  fireEvent.change(screen.getByLabelText('アバターを選択'), { target: { files: [photo()] } })
  fireEvent.click(screen.getByRole('button', { name: '画像を保存' })); await screen.findByText('画像を保存しました。')
  expect(screen.getByLabelText('表示名')).toHaveValue('未保存の表示名')
})
it('coalesces all images and avatars per fetched page and never loops after refreshed URLs fail', async () => {
  const pages = { first: 0, second: 0 }
  const values = (second: boolean, refreshed: boolean) => Array.from({ length: 10 }, (_, index) => ({ ...post(), id: (second ? 'second-' : 'first-') + String(index), image: image(oldId, '/media/post-' + String(index) + (refreshed ? '-fresh' : '')), author: { ...post().author, avatar: image(oldId, '/media/avatar-' + String(index) + (refreshed ? '-fresh' : '')) } }))
  network((url) => { const second = url.includes('cursor=second'); const key = second ? 'second' : 'first'; pages[key]++; return reply(200, { viewer_id: account.id, items: values(second, pages[key] > 1), next_cursor: second ? null : 'second' }) })
  const photos = () => screen.getAllByRole('img').filter(element => element.tagName === 'IMG')
  render(<WorkoutFeed account={account} username="river" onIdentity={identity} />)
  await screen.findByRole('button', { name: 'もっと見る' })
  for (const img of photos()) fireEvent.error(img)
  await waitFor(() => { expect(pages.first).toBe(2); expect(photos()).toHaveLength(20) })
  for (const img of photos()) fireEvent.error(img)
  expect(pages.first).toBe(2)
  fireEvent.click(screen.getByRole('button', { name: 'もっと見る' }))
  await waitFor(() => { expect(pages.second).toBe(1); expect(photos()).toHaveLength(20) })
  for (const img of photos()) fireEvent.error(img)
  await waitFor(() => { expect(pages.second).toBe(2) })
  expect(pages.first).toBe(2)
})
it('starts the initial upload only once in StrictMode', async () => {
  let puts = 0
  network((_url, init) => { puts++; return reply(200, post(image(new Headers(init.headers).get('X-Image-Operation') ?? ''))) })
  render(<StrictMode><ImageEditor account={account} postId={postId} image={null} initialFile={photo()} onImage={vi.fn()} onIdentity={identity} onBusy={busy} onWorking={vi.fn()} /></StrictMode>)
  await screen.findByText('画像を保存しました。'); expect(puts).toBe(1)
})
it('deletes only after accessible native confirmation and keeps the parent record intact', async () => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function (this: HTMLDialogElement) { this.open = true } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function (this: HTMLDialogElement) { this.open = false } })
  let deletes = 0
  network((url, init) => { expect(url).toBe('/api/posts/' + postId + '/image'); expect(init.method).toBe('DELETE'); expect(new Headers(init.headers).has('X-Image-Operation')).toBe(false); deletes++; return reply(204) })
  function Controlled() { const [value, setValue] = useState<ImageAsset | null>(image(oldId)); return <ImageEditor account={account} postId={postId} image={value} onImage={setValue} onIdentity={identity} onBusy={busy} onWorking={vi.fn()} /> }
  render(<Controlled />); fireEvent.click(screen.getByRole('button', { name: '画像を削除' })); expect(deletes).toBe(0)
  expect(screen.getByRole('alertdialog', { name: '画像の削除確認' })).toBeVisible(); expect(screen.getByRole('button', { name: 'キャンセル' })).toHaveFocus()
  fireEvent.click(screen.getByRole('button', { name: '削除する' })); await screen.findByText('画像を削除しました。'); expect(deletes).toBe(1)
})
it.each(['IMAGE_PROCESSING_BUSY', 'IMAGE_OPERATION_PENDING'])('waits two seconds and requires an explicit retry for %s', async code => {
  let puts = 0
  network(() => { puts++; return reply(code === 'IMAGE_PROCESSING_BUSY' ? 503 : 409, { code }) })
  editor(); select(); vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: '画像を保存' })); await Promise.resolve() })
  expect(screen.getByText('画像を処理中です。2秒後に画像だけ再試行してください。')).toBeVisible()
  expect(screen.getByRole('button', { name: '画像だけ再試行' })).toBeDisabled()
  await act(async () => { await vi.advanceTimersByTimeAsync(1999) })
  expect(screen.getByRole('button', { name: '画像だけ再試行' })).toBeDisabled()
  await act(async () => { await vi.advanceTimersByTimeAsync(1) })
  expect(screen.getByRole('button', { name: '画像だけ再試行' })).toBeEnabled(); expect(puts).toBe(1)
})
it('cancels an upload into neutral saved-state checking and releases its busy token', async () => {
  network((_url, init) => {
    if (init.method === 'PUT') return new Promise<Response>((_resolve, reject) => { init.signal?.addEventListener('abort', () => { reject(new DOMException('Aborted', 'AbortError')) }) })
    return reply(200, post(image(oldId)))
  })
  editor(); select(); fireEvent.click(screen.getByRole('button', { name: '画像を保存' }))
  const cancel = await screen.findByRole('button', { name: '画像の通信を中止' })
  await waitFor(() => { expect(busy).toHaveBeenCalledWith(expect.any(Symbol), true) })
  fireEvent.click(cancel)
  await screen.findByText('画像の保存結果を確定できません。現在の画像を表示しました。画像だけ再試行できます。')
  expect(busy).toHaveBeenLastCalledWith(expect.any(Symbol), false)
  expect(screen.getByRole('button', { name: '画像だけ再試行' })).toBeEnabled()
})
it('rejects an oversized photo while preserving all record input', async () => {
  network(() => reply(200, profile()))
  render(<WorkoutScreen account={account} id={null} initial={null} editing onIdentity={identity} onBusy={busy} onSaved={vi.fn()} onClearSaved={vi.fn()} onUncertain={vi.fn()} />)
  fireEvent.change(await screen.findByLabelText('種目名'), { target: { value: 'ベンチプレス' } })
  fireEvent.change(screen.getByLabelText('メモ'), { target: { value: '保存前のメモ' } })
  const oversized = photo(); Object.defineProperty(oversized, 'size', { value: 5242881 })
  fireEvent.change(screen.getByLabelText('写真（任意）'), { target: { files: [oversized] } })
  expect(screen.getByText('5MiB以下の画像を選択してください。')).toBeVisible()
  expect(screen.getByLabelText('種目名')).toHaveValue('ベンチプレス'); expect(screen.getByLabelText('メモ')).toHaveValue('保存前のメモ')
})
it('does not adopt URLs from a page whose membership changed and offers explicit full reload', async () => {
  let reads = 0
  network(() => { reads++; return reply(200, { viewer_id: account.id, items: [{ ...post(image(oldId)), id: reads === 1 ? postId : 'different-post' }], next_cursor: null }) })
  render(<WorkoutFeed account={account} username="river" onIdentity={identity} />)
  fireEvent.error(await screen.findByRole('img', { name: 'ベンチプレス' }))
  await screen.findByText('一覧の続きが無効になりました。最初から読み込み直してください。')
  expect(screen.getByRole('button', { name: '一覧を最初から読み込み直す' })).toBeEnabled(); expect(reads).toBe(2)
})
it('keeps earlier-page URL refresh alive while a new independent page is loaded', async () => {
  let firstReads = 0; let finish: ((r: Response) => void) | undefined
  network(url => {
    if (url.includes('cursor=second')) return reply(200, { viewer_id: account.id, items: [{ ...post(), id: 'second-post' }], next_cursor: null })
    firstReads++
    if (firstReads === 1) return reply(200, { viewer_id: account.id, items: [post(image(oldId))], next_cursor: 'second' })
    return new Promise<Response>(resolve => { finish = resolve })
  })
  render(<WorkoutFeed account={account} username="river" onIdentity={identity} />)
  fireEvent.error(await screen.findByRole('img', { name: 'ベンチプレス' }))
  await waitFor(() => { expect(finish).toBeDefined() })
  fireEvent.click(screen.getByRole('button', { name: 'もっと見る' }))
  await waitFor(() => { expect(screen.getAllByRole('article')).toHaveLength(2) })
  await act(async () => { finish?.(reply(200, { viewer_id: account.id, items: [post(image(oldId, '/media/refreshed-first'))], next_cursor: 'second' })); await Promise.resolve() })
  expect(screen.getByRole('img', { name: 'ベンチプレス' })).toHaveAttribute('src', '/media/refreshed-first'); expect(firstReads).toBe(2)
})
it('blocks navigation and signout while an avatar request owns the shared busy token', async () => {
  location.hash = '#profile-edit'
  let finish: ((r: Response) => void) | undefined; let operation = ''
  network((url, init) => {
    if (url.endsWith('/avatar')) { operation = new Headers(init.headers).get('X-Image-Operation') ?? ''; return new Promise<Response>(resolve => { finish = resolve }) }
    return reply(200, profile())
  })
  render(<App />)
  fireEvent.change(await screen.findByLabelText('アバターを選択'), { target: { files: [photo()] } })
  fireEvent.click(screen.getByRole('button', { name: '画像を保存' })); await waitFor(() => { expect(finish).toBeDefined() })
  expect(screen.getByRole('button', { name: 'ログアウト' })).toBeDisabled()
  fireEvent.click(screen.getByRole('link', { name: 'ホーム' })); expect(location.hash).toBe('#profile-edit')
  await act(async () => { location.hash = '#profile'; window.dispatchEvent(new HashChangeEvent('hashchange')); await Promise.resolve() })
  expect(location.hash).toBe('#profile-edit')
  await act(async () => { finish?.(reply(200, { ...profile(), avatar: image(operation) })); await Promise.resolve() })
  await screen.findByText('画像を保存しました。'); expect(screen.getByRole('button', { name: 'ログアウト' })).toBeEnabled()
})
function nativeDialog() {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function (this: HTMLDialogElement) { this.open = true } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function (this: HTMLDialogElement) { this.open = false } })
}
function StatefulImageEditor() {
  const [value, setValue] = useState<ImageAsset | null>(image(oldId))
  return <ImageEditor account={account} postId={postId} image={value} onImage={setValue} onIdentity={identity} onBusy={busy} onWorking={vi.fn()} />
}
async function deleteImage() {
  fireEvent.click(screen.getByRole('button', { name: '画像を削除' }))
  fireEvent.click(screen.getByRole('button', { name: '削除する' }))
  await screen.findByText('画像を削除しました。')
}
it('deletes a newly created record with a photo through its saved record id', async () => {
  nativeDialog()
  let created = ''; const deletions: string[] = []
  network((url, init) => {
    if (url === '/api/users/me') return reply(200, profile())
    if (init.method === 'POST') { const data = JSON.parse(typeof init.body === 'string' ? init.body : '{}') as Record<string, unknown>; created = String(data.id); return reply(201, { ...post(), id: created }) }
    if (init.method === 'PUT') return reply(200, { ...post(image(new Headers(init.headers).get('X-Image-Operation') ?? '')), id: created })
    if (init.method === 'DELETE') { deletions.push(url); return url === '/api/posts/' + created ? reply(204) : reply(405, { code: 'METHOD_NOT_ALLOWED' }) }
    throw new Error(url)
  })
  render(<WorkoutScreen account={account} id={null} initial={null} editing onIdentity={identity} onBusy={busy} onSaved={vi.fn()} onClearSaved={vi.fn()} onUncertain={vi.fn()} />)
  await screen.findByRole('button', { name: '記録する' })
  fireEvent.change(screen.getByLabelText('写真（任意）'), { target: { files: [photo()] } })
  fireEvent.click(screen.getByRole('button', { name: '記録する' }))
  await screen.findByText('画像を保存しました。')
  fireEvent.click(screen.getByRole('button', { name: '記録を削除' }))
  fireEvent.click(screen.getByRole('button', { name: '削除する' }))
  await waitFor(() => { expect(deletions).toEqual(['/api/posts/' + created]) })
  await screen.findByRole('link', { name: '記録一覧へ戻る' })
})
it('keeps an unsent photo after a previous DELETE when the new PUT identity preflight fails', async () => {
  nativeDialog(); let puts = 0; let reads = 0
  const fetcher = network((_url, init) => { if (init.method === 'DELETE') return reply(204); if (init.method === 'PUT') puts++; else reads++; return reply(200, post()) })
  render(<StatefulImageEditor />); await deleteImage(); select()
  fetcher.mockImplementationOnce(() => Promise.resolve(reply(503, { code: 'SESSION_UNAVAILABLE' })))
  fireEvent.click(screen.getByRole('button', { name: '画像を保存' }))
  await screen.findByText('画像はまだ送信していません。もう一度操作してください。')
  expect(screen.getByRole('img', { name: '選択した画像のプレビュー' })).toBeVisible()
  expect(screen.queryByText('画像を削除しました。')).not.toBeInTheDocument()
  expect(puts).toBe(0); expect(reads).toBe(0)
  expect(screen.getByRole('button', { name: '画像だけ再試行' })).toBeEnabled()
})
it('keeps the selected photo and sends no image PUT when canceled during identity preflight', async () => {
  nativeDialog(); let puts = 0; let reads = 0; let finish: ((r: Response) => void) | undefined
  const fetcher = network((_url, init) => { if (init.method === 'DELETE') return reply(204); if (init.method === 'PUT') puts++; else reads++; return reply(200, post()) })
  render(<StatefulImageEditor />); await deleteImage(); select()
  fetcher.mockImplementationOnce(() => new Promise<Response>(resolve => { finish = resolve }))
  fireEvent.click(screen.getByRole('button', { name: '画像を保存' }))
  await waitFor(() => { expect(finish).toBeDefined() })
  fireEvent.click(screen.getByRole('button', { name: '画像の通信を中止' }))
  await act(async () => { finish?.(reply(200, account)); await Promise.resolve() })
  await screen.findByText('画像はまだ送信していません。もう一度操作してください。')
  expect(screen.getByRole('img', { name: '選択した画像のプレビュー' })).toBeVisible()
  expect(puts).toBe(0); expect(reads).toBe(0)
  expect(screen.queryByRole('button', { name: '画像の保存状態を確認' })).not.toBeInTheDocument()
})
it.each([null, image(oldId)])('gives the avatar fallback an accessible display name for image %s', value => {
  render(<Photo image={value} alt="River のアバター" avatar />)
  if (value) fireEvent.error(screen.getByRole('img', { name: 'River のアバター' }))
  const fallback = screen.getByRole('img', { name: 'River のアバター' })
  expect(fallback).toHaveClass('avatar-fallback')
  expect(fallback.querySelector('[aria-hidden="true"]')).toHaveTextContent('R')
})
it('aborts the image saved-state GET on unmount after the write has completed', async () => {
  let readSignal: AbortSignal | null | undefined
  network((_url, init) => {
    if (init.method === 'PUT') return reply(500, { code: 'STORAGE_UNAVAILABLE' })
    readSignal = init.signal; return new Promise<Response>(() => { /* Read remains in flight until unmount. */ })
  })
  const view = editor(); select(); fireEvent.click(screen.getByRole('button', { name: '画像を保存' }))
  await waitFor(() => { expect(readSignal).toBeDefined() })
  view.unmount()
  expect(readSignal?.aborted).toBe(true)
})
it('aborts a record DELETE and an independent image URL refresh on unmount', async () => {
  nativeDialog(); let writeSignal: AbortSignal | null | undefined; let readSignal: AbortSignal | null | undefined
  network((_url, init) => {
    if (init.method === 'DELETE') writeSignal = init.signal
    else readSignal = init.signal
    return new Promise<Response>(() => { /* Both operations remain in flight until unmount. */ })
  })
  const view = render(<WorkoutScreen account={account} id={postId} initial={post(image(oldId))} editing={false} onIdentity={identity} onBusy={busy} onSaved={vi.fn()} onClearSaved={vi.fn()} onUncertain={vi.fn()} />)
  fireEvent.click(await screen.findByRole('button', { name: '記録を削除' }))
  fireEvent.click(screen.getByRole('button', { name: '削除する' })); await waitFor(() => { expect(writeSignal).toBeDefined() })
  fireEvent.error(screen.getByRole('img', { name: 'ベンチプレス' })); await waitFor(() => { expect(readSignal).toBeDefined() })
  view.unmount()
  expect(writeSignal?.aborted).toBe(true); expect(readSignal?.aborted).toBe(true)
})
it('aborts a profile save and an image refresh retained across editor navigation on unmount', async () => {
  let gets = 0; let readSignal: AbortSignal | null | undefined; let writeSignal: AbortSignal | null | undefined
  network((_url, init) => {
    if (init.method === 'PUT') { writeSignal = init.signal; return new Promise<Response>(() => { /* Save remains pending. */ }) }
    gets++
    if (gets === 2) { readSignal = init.signal; return new Promise<Response>(() => { /* Image refresh remains pending across editor navigation. */ }) }
    return reply(200, { ...profile(), avatar: image(oldId) })
  })
  const props = { account, target: 'me', onIdentity: identity, onName: vi.fn(), onBusy: busy }
  const view = render(<ProfileScreen {...props} editing={false} />)
  fireEvent.error(await screen.findByRole('img', { name: 'River' })); await waitFor(() => { expect(readSignal).toBeDefined() })
  view.rerender(<ProfileScreen {...props} editing />)
  fireEvent.click(await screen.findByRole('button', { name: '変更を保存' })); await waitFor(() => { expect(writeSignal).toBeDefined() })
  view.unmount()
  expect(readSignal?.aborted).toBe(true); expect(writeSignal?.aborted).toBe(true)
})
it.each(['retry', 'delete'])('preserves the earlier unknown PUT when %s fails before dispatch and checks the original operation', async nextAction => {
  nativeDialog(); let operation = ''; let puts = 0; let deletes = 0; let reads = 0
  const fetcher = network((_url, init) => {
    if (init.method === 'PUT') { puts++; operation = new Headers(init.headers).get('X-Image-Operation') ?? ''; return reply(503, { code: 'STORAGE_UNAVAILABLE' }) }
    if (init.method === 'DELETE') { deletes++; return reply(204) }
    reads++; return reply(200, post(image(reads === 1 ? oldId : operation)))
  })
  editor(); select(); fireEvent.click(screen.getByRole('button', { name: '画像を保存' }))
  await screen.findByText('画像の保存結果を確定できません。現在の画像を表示しました。画像だけ再試行できます。')
  fetcher.mockImplementationOnce(() => Promise.resolve(reply(503, { code: 'SESSION_UNAVAILABLE' })))
  if (nextAction === 'retry') fireEvent.click(screen.getByRole('button', { name: '画像だけ再試行' }))
  else { fireEvent.click(screen.getByRole('button', { name: '画像を削除' })); fireEvent.click(screen.getByRole('button', { name: '削除する' })) }
  await screen.findByText('今回は画像を送信していません。前回の画像操作は結果不明です。保存状態を確認してください。')
  expect(screen.getByRole('img', { name: '選択した画像のプレビュー' })).toBeVisible()
  expect(puts).toBe(1); expect(deletes).toBe(0); expect(reads).toBe(1)
  fireEvent.click(screen.getByRole('button', { name: '画像の保存状態を確認' }))
  await screen.findByText('画像を保存しました。')
  expect(screen.queryByText('画像を削除しました。')).not.toBeInTheDocument()
  expect(reads).toBe(2); expect(puts).toBe(1); expect(deletes).toBe(0)
})
