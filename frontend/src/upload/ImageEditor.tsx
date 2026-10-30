import { useEffect, useRef, useState } from 'react'
import { ApiError, getCsrf, getMe } from '../auth/api'
import type { Account } from '../auth/api'
import { getProfile, validProfile } from '../profile/api'
import { getWorkout, validPost } from '../workouts/api'
import { writeImage } from './api'
import { fileError } from './types'
import type { ImageAsset } from './types'

type Props = { account: Account; postId?: string; image: ImageAsset | null; initialFile?: File | null; disabled?: boolean; onImage: (image: ImageAsset | null, mutation?: boolean) => void; onIdentity: (v: Account | null, notice?: string) => void; onBusy: (token: symbol, value: boolean) => void; onWorking: (value: boolean) => void }
export default function ImageEditor(props: Props) {
  const [config] = useState(() => ({ account: props.account, postId: props.postId, onImage: props.onImage, onIdentity: props.onIdentity, onBusy: props.onBusy, onWorking: props.onWorking, auto: Boolean(props.initialFile) }))
  const avatar = !props.postId
  const [file, setFile] = useState<File | null>(props.initialFile ?? null)
  const [preview, setPreview] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [unknown, setUnknown] = useState(false)
  const [waiting, setWaiting] = useState(false)
  const [confirm, setConfirm] = useState(false)
  const operation = useRef(crypto.randomUUID())
  const alive = useRef(true)
  const lifecycle = useRef(0)
  const sending = useRef(false)
  const controller = useRef<AbortController | null>(null)
  const readController = useRef<AbortController | null>(null)
  const token = useRef(Symbol('image-write'))
  const csrf = useRef('')
  const timer = useRef<number | undefined>(undefined)
  const action = useRef<'put' | 'delete'>('put')
  const dialog = useRef<HTMLDialogElement>(null)
  const cancel = useRef<HTMLButtonElement>(null)
  const currentFile = useRef(file)
  const disabled = useRef(props.disabled); disabled.current = props.disabled
  const active = () => alive.current
  function discard() { currentFile.current = null; setFile(null); setUnknown(false); operation.current = crypto.randomUUID() }
  async function identity() {
    const me = await getMe()
    if (!active()) return false
    if (me.id !== config.account.id) { discard(); config.onIdentity(me, 'ログインしているユーザーが変わりました。画像を選び直してください。'); return false }
    return true
  }
  async function read() {
    const abort = new AbortController(); readController.current?.abort(); readController.current = abort
    if (config.postId) return (await getWorkout(config.postId, config.account.id, abort.signal)).image
    return (await getProfile('me', config.account.id, abort.signal)).avatar
  }
  async function fail(error: unknown) {
    if (!active()) return
    if (error instanceof ApiError && error.status === 401) { discard(); config.onIdentity(null, avatar ? 'ログインが切れました。ログイン後にプロフィールで画像の保存状態を確認してください。' : 'ログインが切れました。ログイン後に本人の記録一覧で画像の保存状態を確認してください。画像を自動再送することはありません。'); return }
    if (error instanceof ApiError && (error.code === 'PROFILE_OWNER_CHANGED' || error.code === 'RECORD_OWNER_CHANGED')) {
      discard(); try { const me = await getMe(); if (active()) config.onIdentity(me) } catch { if (active()) config.onIdentity(null) } return
    }
    throw error
  }
  async function check() {
    const value = await read()
    if (!active()) return
    const matched = (action.current === 'put' && value?.id === operation.current) || (action.current === 'delete' && value === null)
    config.onImage(value, matched)
    if (action.current === 'put' && value?.id === operation.current || action.current === 'delete' && value === null) { discard(); setMessage(action.current === 'delete' ? '画像を削除しました。' : '画像を保存しました。') }
    else { setUnknown(true); setMessage('画像の保存結果を確定できません。現在の画像を表示しました。画像だけ再試行できます。') }
  }
  async function perform(remove = false, verify = false) {
    if (sending.current || waiting || disabled.current) return
    if (!verify && !remove && !currentFile.current) return
    const previous = { unknown, action: action.current }
    if (!verify) action.current = remove ? 'delete' : 'put'
    let dispatched = false
    sending.current = true; setBusy(true); config.onWorking(true); config.onBusy(token.current, true); setMessage('')
    const abort = new AbortController(); controller.current = abort
    const canceled = () => abort.signal.aborted
    try {
      if (!await identity() || !active()) return
      if (canceled()) throw new ApiError(0, 'ABORTED', '送信を中止しました。')
      if (verify) { await check(); return }
      if (!csrf.current) csrf.current = await getCsrf()
      if (!active()) return
      if (canceled()) throw new ApiError(0, 'ABORTED', '送信を中止しました。')
      dispatched = true
      const value = await writeImage(config.postId ? '/api/posts/' + encodeURIComponent(config.postId) + '/image' : '/api/users/me/avatar', config.account.id, avatar, csrf.current, remove ? null : currentFile.current, operation.current, abort.signal)
      if (!active()) return
      if (remove) config.onImage(null, true)
      else if (config.postId) {
        if (!validPost(value, config.account.id) || value.id !== config.postId || !value.is_owner || value.image?.id !== operation.current) throw new ApiError(200, 'INVALID_RESPONSE', '画像の保存結果を確認できません。')
        config.onImage(value.image, true)
      } else {
        if (!validProfile(value, config.account.id) || !value.is_owner || value.avatar?.id !== operation.current) throw new ApiError(200, 'INVALID_RESPONSE', '画像の保存結果を確認できません。')
        config.onImage(value.avatar, true)
      }
      discard(); setConfirm(false); setMessage(remove ? '画像を削除しました。' : '画像を保存しました。')
    } catch (error) {
      try {
        await fail(error)
      } catch (cause) {
        if (!active()) return
        if (!dispatched && !verify) {
          action.current = previous.action; setUnknown(previous.unknown); setConfirm(false)
          setMessage(previous.unknown ? '今回は画像を送信していません。前回の画像操作は結果不明です。保存状態を確認してください。' : '画像はまだ送信していません。もう一度操作してください。')
        }
        else if (cause instanceof ApiError && cause.code === 'CSRF_FAILED') {
          try { if (await identity()) { csrf.current = await getCsrf(); if (active()) setMessage('安全性の確認を更新しました。画像だけもう一度保存してください。') } } catch (next) { try { await fail(next) } catch { if (active()) setMessage('安全性の確認を更新できません。もう一度操作してください。') } }
        } else if (cause instanceof ApiError && (cause.code === 'IMAGE_PROCESSING_BUSY' || cause.code === 'IMAGE_OPERATION_PENDING')) {
          setUnknown(cause.code === 'IMAGE_OPERATION_PENDING'); setWaiting(true); setMessage('画像を処理中です。2秒後に画像だけ再試行してください。')
          timer.current = window.setTimeout(() => { if (active()) setWaiting(false) }, 2000)
        } else if (cause instanceof ApiError && cause.status === 409) {
          setUnknown(false); setMessage('この画像操作は再利用できません。現在の画像を確認し、画像を選び直してください。')
          try { const value = await read(); if (active()) config.onImage(value) } catch (next) { try { await fail(next) } catch { /* The explicit conflict message remains available. */ } }
          discard()
        } else if (verify) { setUnknown(true); setMessage('画像の保存状態を読み込めません。もう一度確認してください。') }
        else if (!(cause instanceof ApiError) || cause.status === 0 || cause.status >= 500 || cause.code === 'INVALID_RESPONSE') {
          setUnknown(true); setConfirm(false)
          try { await check() } catch (next) { try { await fail(next) } catch { if (active()) setMessage('画像の保存結果を確認できません。保存状態を確認してください。') } }
        } else setMessage(cause instanceof Error ? cause.message : '画像を保存できません。')
      }
    } finally {
      sending.current = false; config.onBusy(token.current, false)
      if (active()) { setBusy(false); config.onWorking(false) }
    }
  }
  const [start] = useState(() => perform)
  useEffect(() => {
    alive.current = true
    const version = ++lifecycle.current
    if (config.auto) queueMicrotask(() => { if (alive.current && lifecycle.current === version) void start() })
    const ownerToken = token.current
    return () => { alive.current = false; controller.current?.abort(); readController.current?.abort(); window.clearTimeout(timer.current); config.onBusy(ownerToken, false) }
  }, [config, start])
  useEffect(() => {
    if (!file) { setPreview(''); return }
    const url = URL.createObjectURL(file); setPreview(url)
    return () => { URL.revokeObjectURL(url) }
  }, [file])
  useEffect(() => {
    const element = dialog.current
    if (confirm && element && !element.open) { element.showModal(); cancel.current?.focus() }
    return () => { if (element?.open) element.close() }
  }, [confirm])
  return <section className="image-editor" aria-label={avatar ? 'アバターの変更' : '記録画像の変更'}><h2>{avatar ? 'プロフィール画像' : '記録の写真'}</h2>
    <p>PNG・JPEG、{avatar ? '2' : '5'}MiB以下。画像は会員間に公開されます。</p>
    {message && <p role="alert">{message}</p>}
    <label className="field">{avatar ? 'アバターを選択' : '記録画像を選択'}<input type="file" accept="image/png,image/jpeg" disabled={busy || props.disabled} onChange={event => {
      const next = event.target.files?.[0]; event.target.value = ''; if (!next) return
      const error = fileError(next, avatar); if (error) { setMessage(error); return }
      currentFile.current = next; setFile(next); setUnknown(false); setMessage(''); operation.current = crypto.randomUUID()
    }} /></label>
    {preview && <><img className="image-preview" src={preview} alt="選択した画像のプレビュー" referrerPolicy="no-referrer" /><button type="button" disabled={busy || props.disabled} onClick={discard}>選択を取り消す</button></>}
    {file && <button type="button" disabled={busy || waiting || props.disabled} onClick={() => { void perform() }}>{busy ? '画像を保存中…' : unknown || message ? '画像だけ再試行' : '画像を保存'}</button>}
    {unknown && <button type="button" disabled={busy || waiting || props.disabled} onClick={() => { void perform(false, true) }}>画像の保存状態を確認</button>}
    {busy && <button type="button" onClick={() => { controller.current?.abort(); readController.current?.abort() }}>画像の通信を中止</button>}
    {props.image && <button type="button" disabled={busy || waiting || props.disabled} onClick={() => { setConfirm(true) }}>画像を削除</button>}
    {confirm && <dialog ref={dialog} aria-label="画像の削除確認" role="alertdialog" onCancel={event => { event.preventDefault(); if (!busy) setConfirm(false) }} onClose={() => { setConfirm(false) }}><p>画像を削除しますか？元に戻せません。</p><button ref={cancel} type="button" disabled={busy} onClick={() => { setConfirm(false) }}>キャンセル</button><button type="button" disabled={busy} onClick={() => { void perform(true) }}>削除する</button></dialog>}
  </section>
}
