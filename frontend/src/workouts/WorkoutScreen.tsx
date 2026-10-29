import { useEffect, useRef, useState } from 'react'
import { ApiError, getCsrf, getMe } from '../auth/api'
import type { Account, FieldErrors } from '../auth/api'
import { getProfile } from '../profile/api'
import { getWorkout, writeWorkout } from './api'
import type { Workout } from './types'
import WorkoutCard from './WorkoutCard'
import WorkoutEditor from './WorkoutEditor'

type Props = {
  account: Account; id: string | null; editing: boolean; initial: Workout | null
  onIdentity: (v: Account | null, notice?: string) => void
  onBusy: (token: symbol, busy: boolean) => void
  onSaved: (v: Workout) => void; onClearSaved: () => void
  onUncertain: (token: symbol, uncertain: boolean) => void
}
type Submission = {
  id: string; action: 'create' | 'update' | 'delete'; conflict: boolean
  payload: Record<string, unknown> | null; retried: boolean; unknown: boolean
}
const loginNotice = 'ログインが切れました。ログイン後に記録一覧で保存されたか確認してください。同じ内容を新しい記録として自動保存することはありません。'
export default function WorkoutScreen({ account, id, editing, initial, onIdentity, onBusy, onSaved, onClearSaved, onUncertain }: Props) {
  const [post, setPost] = useState<Workout | null>(initial)
  const [ready, setReady] = useState(false)
  const [missing, setMissing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [viewOnly, setViewOnly] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [message, setMessage] = useState(initial && !editing ? '記録を保存しました。' : '')
  const [fields, setFields] = useState<FieldErrors>({})
  const [uncertain, setUncertain] = useState(false)
  const [retryAvailable, setRetryAvailable] = useState(false)
  const [epoch, setEpoch] = useState(0)
  const [health, setHealth] = useState<{ weight: string | null; age: number | null }>({ weight: null, age: null })
  const alive = useRef(true)
  const generation = useRef(0)
  const controller = useRef<AbortController | null>(null)
  const sending = useRef(false)
  const lock = useRef(Symbol())
  const csrf = useRef('')
  const submitted = useRef<Submission | null>(null)
  const dialog = useRef<HTMLDialogElement>(null)
  const cancelButton = useRef<HTMLButtonElement>(null)
  const current = (v: number) => alive.current && v === generation.current
  function markUncertain(value: boolean) {
    setUncertain(value)
    onUncertain(lock.current, value && submitted.current?.unknown === true)
  }
  function dismissDelete() { dialog.current?.close(); setConfirmDelete(false) }
  async function identityMatches() {
    const version = generation.current
    const me = await getMe()
    if (!alive.current || version !== generation.current) return false
    if (me.id !== account.id) {
      setPost(null); setReady(false); submitted.current = null
      onIdentity(me, 'ログインしているユーザーが変わりました。記録を開き直してください。')
      return false
    }
    return true
  }
  async function failed(cause: unknown, version: number) {
    if (!current(version)) return
    const error = cause instanceof ApiError ? cause : new ApiError(0, 'NETWORK_ERROR', '保存できたか確認できません。保存状態を確認してください。')
    if (error.status === 401) {
      const notice = submitted.current?.unknown ? loginNotice : 'セッションの有効期限が切れました。ログインしてください。'
      setPost(null); setReady(false); submitted.current = null; markUncertain(false)
      onIdentity(null, notice)
      return
    }
    if (error.code === 'RECORD_OWNER_CHANGED') {
      setPost(null); setReady(false); submitted.current = null; markUncertain(false)
      try { const next = await getMe(); if (current(version)) onIdentity(next, error.message) }
      catch { if (current(version)) onIdentity(null) }
      return
    }
    if (error.status === 403 && error.code === 'CSRF_FAILED') {
      const wasUnknown = submitted.current?.unknown === true
      if (!wasUnknown) submitted.current = null
      markUncertain(wasUnknown); dismissDelete()
      try {
        if (!await identityMatches() || !current(version)) return
        const token = await getCsrf()
        if (current(version)) { csrf.current = token; setMessage(wasUnknown ? '安全性の確認を更新しました。保存状態を確認してください。' : '安全性の確認を更新しました。入力を確認してもう一度保存してください。') }
      } catch (next) {
        if (!current(version)) return
        if (next instanceof ApiError && next.status === 401) onIdentity(null)
        else setMessage('安全性の確認を更新できません。時間をおいてもう一度操作してください。')
      }
      return
    }
    if (error.status === 404) {
      submitted.current = null; markUncertain(false); onClearSaved(); dismissDelete()
      setMissing(true); setPost(null); setMessage('記録が見つかりません。')
      return
    }
    if (error.status === 403) {
      submitted.current = null; markUncertain(false); dismissDelete(); setViewOnly(true)
      setMessage('この記録は編集できません。')
      return
    }
    if (!submitted.current && (error.status === 0 || error.status >= 500 || error.code === 'INVALID_RESPONSE')) {
      setMessage('ログイン状態を確認できません。時間をおいてもう一度操作してください。')
      return
    }
    setFields(error.fields)
    const ambiguous = submitted.current !== null && (submitted.current.unknown || error.status === 0 || error.status >= 500 || error.code === 'INVALID_RESPONSE' || error.code === 'POST_ID_CONFLICT')
    if (submitted.current) {
      submitted.current.unknown = ambiguous
      if (error.code === 'POST_ID_CONFLICT') submitted.current.conflict = true
      if (!ambiguous) submitted.current = null
    }
    markUncertain(ambiguous)
    if (ambiguous) dismissDelete()
    setMessage(ambiguous ? '保存できたか確認できません。保存状態を確認してください。' : error.status === 413 ? '入力データが大きすぎます。種目・セット・メモを確認してください。' : error.status === 415 ? '入力形式を確認してください。' : '入力を確認してください。')
  }
  const [config] = useState(() => ({ account, id, editing, initial, onIdentity, onBusy, onClearSaved, onUncertain }))
  const [lifecycle] = useState(() => ({ identityMatches, failed }))
  useEffect(() => {
    const version = ++generation.current
    const operations = generation
    const active = () => alive.current && version === operations.current
    const token = lock.current
    alive.current = true
    const abort = new AbortController(); controller.current = abort
    // The local state keeps this handoff; the parent cache is consumed once.
    if (config.initial) config.onClearSaved()
    async function load() {
      try {
        if (!await lifecycle.identityMatches() || !active()) return
        if (config.id && !config.initial) {
          const value = await getWorkout(config.id, config.account.id, abort.signal)
          if (active()) { setPost(value); if (config.editing && !value.is_owner) setMessage('この記録は編集できません。') }
        }
        if (config.editing || !config.id) {
          const profile = await getProfile('me', config.account.id, abort.signal)
          if (active()) setHealth({ weight: profile.health.weight ?? null, age: profile.health.age ?? null })
        }
        if (active()) setReady(true)
      } catch (error) { await lifecycle.failed(error, version) }
    }
    void load()
    const focus = () => {
      if (!sending.current) void lifecycle.identityMatches().catch((error: unknown) => { void lifecycle.failed(error, version) })
    }
    window.addEventListener('focus', focus)
    return () => {
      alive.current = false; operations.current++; abort.abort(); controller.current?.abort()
      config.onBusy(token, false); config.onUncertain(token, false)
      window.removeEventListener('focus', focus)
    }
  }, [config, lifecycle])
  useEffect(() => {
    const element = dialog.current
    if (confirmDelete && element && !element.open) { element.showModal(); cancelButton.current?.focus() }
    return () => { if (element?.open) element.close() }
  }, [confirmDelete])
  async function perform(data: Record<string, unknown> | null, retry = false) {
    if (sending.current || uncertain && !retry) return
    const previous = submitted.current
    if (retry && (!retryAvailable || !previous || previous.retried || previous.action !== 'create')) return
    const version = generation.current
    const abort = new AbortController(); controller.current = abort
    sending.current = true; onBusy(lock.current, true); setBusy(true); setFields({}); setMessage(''); setRetryAvailable(false)
    let destination: string | null = null
    try {
      if (!await identityMatches() || !current(version)) return
      if (!csrf.current) csrf.current = await getCsrf()
      const payload = retry && previous ? previous.payload : data
      submitted.current = { id: id ?? String(payload?.id), action: payload === null ? 'delete' : id ? 'update' : 'create', conflict: false, payload: payload === null ? null : structuredClone(payload), retried: retry, unknown: retry && previous?.unknown === true }
      const result = await writeWorkout(id, account.id, csrf.current, payload, abort.signal)
      if (!current(version)) return
      markUncertain(false)
      if (result) { setPost(result); onSaved(result); setMessage('記録を保存しました。'); destination = '#record/' + result.id }
      else { onClearSaved(); setPost(null); setMissing(true); destination = '#profile' }
      submitted.current = null; dismissDelete()
    } catch (error) { await failed(error, version) }
    finally { sending.current = false; onBusy(lock.current, false); if (current(version)) setBusy(false) }
    if (destination && current(version)) location.hash = destination
  }
  async function recover() {
    if (sending.current) return
    if (!submitted.current) { markUncertain(false); setMessage('保存状態を確認する送信済みの記録はありません。'); return }
    const submission = submitted.current
    const version = generation.current
    const abort = new AbortController(); controller.current = abort
    sending.current = true; onBusy(lock.current, true); setBusy(true); setRetryAvailable(false)
    try {
      if (!await identityMatches() || !current(version)) return
      const value = await getWorkout(submission.id, account.id, abort.signal)
      if (!current(version)) return
      onClearSaved()
      if (!value.is_owner) { submitted.current = null; markUncertain(false); setPost(null); setMissing(true); setMessage('この識別子は使用できません。新しい記録を作り直してください。'); return }
      setPost(value); markUncertain(false); dismissDelete(); setEpoch(v => v + 1); submitted.current = null
      if (submission.action === 'create') {
        onSaved(value); setMessage('記録を保存しました。'); onBusy(lock.current, false); location.hash = '#record/' + value.id
      } else setMessage(submission.action === 'delete' ? '保存済みの記録を表示しました。削除する場合はもう一度確認してください。' : '保存済みの記録を表示しました。変更が反映されているか確認してください。')
    } catch (error) {
      if (!current(version)) return
      if (error instanceof ApiError && error.status === 404) {
        onClearSaved()
        if (submission.action !== 'create') {
          submitted.current = null; markUncertain(false); dismissDelete(); setPost(null); setMissing(true)
          setMessage(submission.action === 'delete' ? '記録を削除しました。' : '記録が見つかりません。')
        } else if (submission.conflict) {
          submitted.current = null; markUncertain(false); setPost(null); setMissing(true)
          setMessage('この識別子は使用できません。記録一覧で保存状態を確認してから、新しい記録として作り直してください。')
        } else {
          setRetryAvailable(!submission.retried)
          setMessage(submission.retried ? '保存状態を確認できません。記録一覧で確認してください。' : 'まだ保存されていないか、削除されています。同じ内容を1回だけ再送できます。')
        }
      } else await failed(error, version)
    } finally { sending.current = false; onBusy(lock.current, false); if (current(version)) setBusy(false) }
  }
  return <section className="workout-content">
    {message && <div role="alert"><p>{message}</p>{fields._form && <p>{fields._form.join(' ')}</p>}</div>}
    {missing ? <a href="#profile">記録一覧へ戻る</a> : !ready ? !message && <p role="status">記録を読み込んでいます…</p> : (!id || editing && post?.is_owner && !viewOnly) ? <WorkoutEditor key={epoch} post={post} busy={busy || uncertain} fields={fields} health={health} onSave={v => { void perform(v) }} /> : post && <><WorkoutCard post={post} />{post.is_owner && !viewOnly && <div className="row"><a href={'#record-edit/' + post.id}>編集</a><button disabled={busy || uncertain} type="button" onClick={() => { setConfirmDelete(true) }}>記録を削除</button></div>}</>}
    {uncertain && !missing && <button disabled={busy} type="button" onClick={() => { void recover() }}>保存状態を確認（入力を破棄して保存済みの記録を表示）</button>}
    {retryAvailable && !missing && <button disabled={busy} type="button" onClick={() => { void perform(submitted.current?.payload ?? null, true) }}>同じ内容で1回再送</button>}
    {confirmDelete && <dialog ref={dialog} role="alertdialog" onClose={() => { setConfirmDelete(false) }} aria-label="記録の削除確認" className="delete-dialog" onCancel={event => { event.preventDefault(); if (!sending.current) dismissDelete() }}><p>この記録を削除しますか？削除すると元に戻せません。</p><p>{post?.performed_on} {post?.exercises[0]?.name}</p><button ref={cancelButton} type="button" disabled={busy} onClick={dismissDelete}>キャンセル</button><button type="button" disabled={busy || uncertain} onClick={() => { void perform(null) }}>削除する</button></dialog>}
  </section>
}
