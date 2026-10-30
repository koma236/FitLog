import { useEffect, useRef, useState } from 'react'
import { ApiError, getCsrf, getMe } from '../auth/api'
import type { Account } from '../auth/api'
import { getWorkout } from '../workouts/api'
import Photo from '../upload/Photo'
import { getComment, listComments, normalizeBody, writeComment } from './api'
import type { Comment, CommentPage, CommentResult, SocialProps } from './types'
type Snapshot = { readonly id: string; readonly body: string; readonly action: 'create' | 'update' | 'delete'; readonly actor: string; unknown: boolean; retried: boolean; conflict: boolean }
type Props = SocialProps & { account: Account; postId: string; onCount: (count: number) => void; onMissing: () => void; disabled?: boolean }
export default function CommentsPanel({ account, postId, onCount, onMissing, onIdentity, onBusy, onUncertain, disabled }: Props) {
  const [page, setPage] = useState<CommentPage | null>(null); const [confirmation, setConfirmation] = useState<Comment | null>(null)
  const [draft, setDraft] = useState(''); const [editing, setEditing] = useState<Comment | null>(null)
  const editor = useRef<HTMLTextAreaElement>(null)
  const [editMissing, setEditMissing] = useState(false)
  const [parentMissing, setParentMissing] = useState(false)
  const [busy, setBusy] = useState(false); const [loading, setLoading] = useState(false); const [message, setMessage] = useState(''); const [listError, setListError] = useState('')
  const [unknown, setUnknown] = useState(false); const [retryable, setRetryable] = useState(false); const [different, setDifferent] = useState<Comment | null>(null); const [deleteRemains, setDeleteRemains] = useState(false)
  const [dialogMode, setDialogMode] = useState<'delete' | 'abandon' | null>(null); const [deleteTarget, setDeleteTarget] = useState<Comment | null>(null)
  const token = useRef(Symbol()); const snapshot = useRef<Snapshot | null>(null); const pendingId = useRef<string | null>(null)
  const alive = useRef(true); const generation = useRef(0); const readGeneration = useRef(0); const sending = useRef(false)
  const writeController = useRef<AbortController | null>(null); const pageController = useRef<AbortController | null>(null); const recoveryController = useRef<AbortController | null>(null)
  const heading = useRef<HTMLHeadingElement>(null); const dialog = useRef<HTMLDialogElement>(null); const cancel = useRef<HTMLButtonElement>(null); const returnFocus = useRef<HTMLElement | null>(null)
  const active = (version: number) => alive.current && generation.current === version
  function mark(value: boolean) { setUnknown(value); onUncertain(token.current, value); onBusy(token.current, sending.current || value) }
  function clear() { snapshot.current = null; pendingId.current = null; mark(false); setRetryable(false); setDifferent(null); setDeleteRemains(false) }
  function identityLost(next: Account | null, notice?: string) {
    clear(); generation.current++; readGeneration.current++; writeController.current?.abort(); pageController.current?.abort(); recoveryController.current?.abort()
    setDraft(''); setEditing(null); setPage(null); setConfirmation(null); onBusy(token.current, false); onIdentity(next, notice ?? 'ログイン後に既存のコメントを確認してください。自動再送はしません。')
  }
  async function identity(version: number) {
    const me = await getMe()
    if (!active(version)) return false
    if (me.id !== account.id) { identityLost(me, 'ログインしているユーザーが変わりました。コメントを開き直してください。'); return false }
    return true
  }
  function missingParent() { setParentMissing(true); setRetryable(false); onMissing() }
  async function special(error: ApiError, version: number) {
    if (error.status === 401) { identityLost(null); return true }
    if (error.code === 'SOCIAL_OWNER_CHANGED' || error.code === 'RECORD_OWNER_CHANGED') {
      try { const me = await getMe(); if (active(version)) identityLost(me, error.message) } catch { if (active(version)) identityLost(null) }
      return true
    }
    if (error.code === 'CSRF_FAILED') {
      try { if (await identity(version) && active(version)) { await getCsrf(); if (active(version)) setMessage(snapshot.current?.unknown ? '安全性の確認を更新しました。前回結果不明のまま状態を確認してください。' : '安全性の確認を更新しました。入力を確認してもう一度操作してください。') } } catch (cause) { if (active(version)) { if (cause instanceof ApiError && cause.status === 401) identityLost(null); else setMessage('安全性を確認できません。もう一度操作してください。') } }
      return true
    }
    return false
  }
  async function checkParent(version: number, signal: AbortSignal) {
    try { const parent = await getWorkout(postId, account.id, signal); if (active(version)) onCount(parent.comment_count) }
    catch (cause) {
      if (!active(version)) return
      if (cause instanceof ApiError) { if (await special(cause, version)) return; if (cause.status === 404) { if (snapshot.current) snapshot.current.conflict = true; missingParent(); return } }
      setListError('記録の表示状態を確認できません。入力を保持しています。明示的に一覧を再読み込みしてください。')
    }
  }
  async function load(cursor?: string, successNotice = '') {
    const version = generation.current; const op = ++readGeneration.current
    const controller = new AbortController(); pageController.current?.abort(); pageController.current = controller
    if (!cursor) setPage(null)
    setLoading(true); setListError('')
    try {
      const value = await listComments(postId, account.id, controller.signal, cursor)
      if (!active(version) || op !== readGeneration.current) return
      setPage(previous => cursor && previous ? { ...value, items: [...previous.items, ...value.items.filter(row => !previous.items.some(old => old.id === row.id))] } : value)
      setConfirmation(previous => previous && value.items.some(row => row.id === previous.id) ? null : previous)
      onCount(value.comment_count)
    } catch (cause) {
      if (!active(version) || op !== readGeneration.current) return
      const error = cause instanceof ApiError ? cause : new ApiError(0, '', '接続できません。')
      if (await special(error, version)) return
      if (error.status === 404) { missingParent(); return }
      if (error.code === 'INVALID_CURSOR') {
        try {
          if (!await identity(version) || !active(version) || op !== readGeneration.current) return
          setPage(null); setListError('一覧の続きが無効になりました。先頭から再読み込みしてください。')
        } catch (cause) { if (active(version) && op === readGeneration.current) { if (cause instanceof ApiError && cause.status === 401) identityLost(null); else setListError('本人確認ができません。コメントを先頭から再読み込みしてください。') } }
      } else setListError(successNotice || 'コメントを読み込めません。先頭から再読み込みしてください。')
    } finally { if (active(version) && op === readGeneration.current) setLoading(false) }
  }
  const [config] = useState(() => ({ onBusy, onUncertain }))
  const [lifecycle] = useState(() => ({ load, identity, special }))
  useEffect(() => {
    alive.current = true
    const lock = token.current; const versions = generation; const reads = readGeneration
    void lifecycle.load()
    const focus = () => { if (!sending.current) { const op = versions.current; void lifecycle.identity(op).catch((cause: unknown) => { if (cause instanceof ApiError && active(op)) void lifecycle.special(cause, op) }) } }
    const unload = (event: BeforeUnloadEvent) => { if (snapshot.current?.unknown) { event.preventDefault() } }
    window.addEventListener('focus', focus); window.addEventListener('beforeunload', unload)
    return () => { alive.current = false; versions.current++; reads.current++; pageController.current?.abort(); writeController.current?.abort(); recoveryController.current?.abort(); config.onBusy(lock, false); config.onUncertain(lock, false); window.removeEventListener('focus', focus); window.removeEventListener('beforeunload', unload) }
  }, [config, lifecycle])
  useEffect(() => { if (editing) editor.current?.focus() }, [editing])
  useEffect(() => {
    const element = dialog.current
    if (dialogMode && element && !element.open) { element.showModal(); cancel.current?.focus() }
    return () => { if (element?.open) element.close() }
  }, [dialogMode])
  function closeDialog() { dialog.current?.close(); setDialogMode(null); returnFocus.current?.focus() }
  function openDialog(mode: 'delete' | 'abandon', target?: Comment) { returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null; setDeleteTarget(target ?? null); setDialogMode(mode) }
  function resetReads(clearPage = true) { readGeneration.current++; pageController.current?.abort(); if (clearPage) setPage(null); setLoading(false) }
  async function success(value: CommentResult | null, submission: Snapshot, neutralDelete = false) {
    clear(); if (submission.action !== 'delete' || editing?.id === submission.id) { setEditing(null); setDraft('') } closeDialog(); resetReads(submission.action !== 'update')
    if (value) {
      onCount(value.comment_count)
      if (submission.action === 'create') { setConfirmation(value.comment); setMessage('コメントを送信しました。'); await load(undefined, '送信済み。一覧を再読み込みしてください。') }
      else { setPage(previous => previous ? { ...previous, items: previous.items.map(row => row.id === value.comment.id ? value.comment : row) } : previous); setConfirmation(previous => previous?.id === value.comment.id ? value.comment : previous); setMessage('コメントを保存しました。') }
    } else {
      setConfirmation(previous => previous?.id === submission.id ? null : previous)
      setMessage(neutralDelete ? '現在は表示されていません。' : 'コメントを削除しました。')
      heading.current?.focus(); await load(undefined, neutralDelete ? '現在は表示されていません。一覧の件数を更新できません。' : '削除済み、件数を更新できません。一覧を再読み込みしてください。')
      heading.current?.focus()
    }
  }
  async function perform(action: Snapshot['action'], target?: Comment, retry = false) {
    if (sending.current || disabled || parentMissing || editMissing || snapshot.current?.unknown && !retry) return
    const previous = snapshot.current
    if (retry && (!previous || action === 'create' && (!retryable || previous.retried || previous.conflict))) return
    let body: string
    try { body = previous && retry ? previous.body : normalizeBody(action === 'delete' ? target?.body ?? '' : draft) } catch { setMessage('使用できない文字が含まれています。'); return }
    if (action !== 'delete' && (!body || Array.from(body).length > 500)) { setMessage('コメントは1〜500文字で、使用できる文字を入力してください。'); return }
    if (action === 'create' && !pendingId.current) pendingId.current = crypto.randomUUID()
    const id = previous && retry ? previous.id : target?.id ?? editing?.id ?? pendingId.current ?? ''
    const version = generation.current; const controller = new AbortController(); writeController.current = controller
    sending.current = true; setBusy(true); onBusy(token.current, true); setMessage(''); setRetryable(false); let sent = false
    resetReads(false)
    try {
      if (!await identity(version) || !active(version)) return
      const csrf = await getCsrf(); if (!active(version)) return
      const submission: Snapshot = previous && retry ? { ...previous, retried: action === 'create' ? true : previous.retried } : { id, body, actor: account.id, action, unknown: false, conflict: false, retried: false }
      body = submission.body; snapshot.current = submission; sent = true
      const value = await writeComment(postId, submission.id, submission.action, body, submission.actor, csrf, controller.signal)
      if (!active(version)) return
      await success(value, submission)
    } catch (cause) {
      if (!active(version)) return
      const error = cause instanceof ApiError ? cause : new ApiError(0, '', '接続できません。')
      if (!sent) snapshot.current = previous
      if (await special(error, version)) return
      if (!sent) { mark(previous?.unknown === true); setRetryable(previous?.action === 'create' && !previous.retried && !previous.conflict && retry); setMessage(previous?.unknown ? '今回未送信、前回結果不明です。状態を確認してください。' : '未送信です。入力を保持しています。もう一度操作してください。'); return }
      const submission = snapshot.current
      if (!submission) return
      if (error.status === 404 && submission.action !== 'create') {
        closeDialog()
        if (submission.unknown) { mark(true); setMessage('現在は表示されていません。前回の結果は不明です。状態を確認するか確認を中断してください。') }
        else if (submission.action === 'delete') { await success(null, submission, true); return }
        else { setPage(previous => previous ? { ...previous, items: previous.items.filter(row => row.id !== submission.id) } : previous); setConfirmation(previous => previous?.id === submission.id ? null : previous); snapshot.current = null; mark(false); setEditMissing(true); setMessage('現在は表示されていません。編集内容を保持しています。編集をキャンセルして一覧へ戻れます。') }
        await checkParent(version, controller.signal)
        return
      }
      if (error.code === 'COMMENT_ID_CONFLICT') submission.conflict = true
      if (submission.unknown || error.status === 0 || error.status >= 500 || error.code === 'INVALID_RESPONSE' || error.code === 'COMMENT_ID_CONFLICT') {
        submission.unknown = true; mark(true); closeDialog(); setMessage(error.status === 404 ? '記録は現在表示されていません。前回の保存結果は不明です。' : '保存できたか確認できません。状態を確認してください。')
        if (error.status === 404) { submission.conflict = true; missingParent() }
      } else { snapshot.current = null; mark(false); setMessage(error.fields.body?.join(' ') || error.message); if (error.status === 404) missingParent(); if (error.status === 403) setEditing(null) }
    } finally { sending.current = false; if (active(version)) { setBusy(false); onBusy(token.current, snapshot.current?.unknown === true) } }
  }
  async function recover() {
    const submission = snapshot.current
    if (!submission || !submission.unknown || sending.current || disabled) return
    const version = generation.current; const controller = new AbortController(); recoveryController.current = controller
    sending.current = true; setBusy(true); setRetryable(false); setMessage(''); onBusy(token.current, true)
    try {
      if (!await identity(version) || !active(version)) return
      const value = await getComment(submission.id, postId, account.id, controller.signal)
      if (!active(version)) return
      if (submission.action === 'delete') { setDeleteRemains(true); setMessage('現在はコメントが残っています。削除する場合は明示的に操作してください。'); return }
      if (value.comment.is_owner && value.comment.author.id === submission.actor && value.comment.body === submission.body) await success(value, submission)
      else { setDifferent(value.comment); setMessage('現在の保存内容'); submission.conflict = true }
    } catch (cause) {
      if (!active(version)) return
      const error = cause instanceof ApiError ? cause : new ApiError(0, '', '接続できません。')
      if (await special(error, version)) return
      if (error.status === 404) {
        if (submission.action === 'delete') { await success(null, submission, true); return }
        setRetryable(submission.action === 'create' && !submission.retried && !submission.conflict)
        setMessage(submission.action !== 'create' ? '現在は表示されていません。確認を中断して一覧へ戻れます。' : submission.retried || submission.conflict ? '保存された可能性がありますが現在は表示されていません。再送しません。' : 'まだ保存されていないか削除されています。同じ内容を1回だけ再送できます。')
        await checkParent(version, controller.signal)
      } else setMessage('前回の結果は不明です。状態を確認するか確認を中断してください。')
    } finally { sending.current = false; if (active(version)) { setBusy(false); onBusy(token.current, snapshot.current?.unknown === true) } }
  }
  async function reload() {
    if (sending.current || loading || disabled) return
    const version = generation.current; const op = readGeneration.current
    if (confirmation) {
      const controller = new AbortController(); recoveryController.current = controller
      try { await getComment(confirmation.id, postId, account.id, controller.signal) }
      catch (cause) {
        if (!active(version) || op !== readGeneration.current) return
        if (cause instanceof ApiError) { if (cause.status === 404) setConfirmation(current => current?.id === confirmation.id ? null : current); else if (await special(cause, version)) return }
      }
      if (!active(version) || op !== readGeneration.current) return
    }
    await load()
  }
  function row(item: Comment, controls = true) { return <article className="comment-row" key={item.id}><header><Photo image={item.author.avatar} avatar alt={item.author.display_name} /><a href={'#profile/' + encodeURIComponent(item.author.username)}>{item.author.display_name} @{item.author.username}</a><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString('ja-JP')}</time></header><p className="comment-body">{item.body}</p>{controls && item.is_owner && <div className="row"><button type="button" disabled={busy || unknown || disabled || parentMissing || editMissing} onClick={() => { setEditMissing(false); setEditing(item); setDraft(item.body) }}>編集</button><button type="button" disabled={busy || unknown || disabled || parentMissing || editMissing} onClick={() => { openDialog('delete', item) }}>削除</button></div>}</article> }
  return <section className="comments-panel" aria-label="コメント一覧"><h2 ref={heading} tabIndex={-1}>コメント</h2><p>コメント一覧は古い順です。もっと見るで続きも確認できます。</p>
    {message && <p role="alert">{message}</p>}{listError && <p role="alert">{listError}</p>}
    {confirmation && <section aria-label="送信したコメント" className="comment-confirmation"><h3>送信したコメント</h3>{row(confirmation)}</section>}
    {page?.items.map(item => row(item))}{page?.items.length === 0 && <p>まだコメントがありません。</p>}
    {loading && <p role="status">コメントを読み込んでいます…</p>}
    {page?.next_cursor && !listError && <button type="button" disabled={loading || busy || disabled} onClick={() => { void load(page.next_cursor ?? undefined) }}>もっとコメントを見る</button>}
    <button type="button" disabled={loading || busy || disabled} onClick={() => { void reload() }}>コメントを先頭から再読み込み</button>
    {!unknown && <form onSubmit={event => { event.preventDefault(); void perform(editing ? 'update' : 'create') }}><label>コメント本文<textarea ref={editor} aria-describedby={editing ? 'comment-edit-target' : undefined} readOnly={editMissing} value={draft} disabled={busy || disabled || parentMissing} onChange={event => { setDraft(event.target.value) }} /></label>{editing && <p id="comment-edit-target">編集対象: {editing.author.display_name}、{new Date(editing.created_at).toLocaleString('ja-JP')}のコメント</p>}<p>{Array.from(draft).length} / 500文字</p><button type="submit" disabled={busy || disabled || parentMissing || editMissing}>{editing ? '変更を保存' : 'コメントする'}</button>{editing && <button type="button" disabled={busy || disabled} onClick={() => { setEditing(null); setEditMissing(false); setDraft(''); void load(); heading.current?.focus() }}>編集をキャンセル</button>}</form>}
    {unknown && <div className="comment-recovery"><label>送信した本文<textarea value={snapshot.current?.body ?? ''} readOnly /></label>{different && <div>{row(different, false)}{different.is_owner && <button type="button" disabled={busy || disabled} onClick={() => { const value = different; clear(); setEditMissing(false); setEditing(value); setDraft(value.body); setMessage('現在の内容で編集を再開しました。') }}>現在の内容で編集を開き直す</button>}</div>}
      <button type="button" disabled={busy || disabled} onClick={() => { void recover() }}>状態を確認</button>{retryable && <button type="button" disabled={busy || disabled} onClick={() => { void perform('create', undefined, true) }}>同じ内容で1回再送</button>}{deleteRemains && <button type="button" disabled={busy || disabled} onClick={() => { void perform('delete', undefined, true) }}>同じコメントを削除する</button>}<button type="button" disabled={busy || disabled} onClick={() => { openDialog('abandon') }}>確認を中断</button>
    </div>}
    {dialogMode && <dialog ref={dialog} role="alertdialog" aria-label={dialogMode === 'delete' ? 'コメントの削除確認' : '確認の中断'} onCancel={event => { event.preventDefault(); if (!sending.current) closeDialog() }} onClose={() => { setDialogMode(null) }}><p>{dialogMode === 'delete' ? 'このコメントを削除しますか？元に戻せません。' : 'コメントは保存された可能性があります。確認を中断して手入力すると別のコメントとして重複する可能性があります。送信した本文は中断前にコピーできます。'}</p><button ref={cancel} type="button" disabled={busy} onClick={closeDialog}>キャンセル</button><button type="button" disabled={busy} onClick={() => { if (dialogMode === 'delete') void perform('delete', deleteTarget ?? undefined); else { clear(); setDraft(''); setEditing(null); closeDialog(); setMessage('確認を中断しました。再入力する前に既存のコメントを確認してください。'); heading.current?.focus() } }}>{dialogMode === 'delete' ? 'コメントを削除する' : '中断して一覧へ戻る'}</button></dialog>}
  </section>
}
