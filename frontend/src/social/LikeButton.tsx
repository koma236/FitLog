import { useEffect, useId, useRef, useState } from 'react'
import { ApiError, getCsrf, getMe } from '../auth/api'
import type { Account } from '../auth/api'
import type { Workout } from '../workouts/types'
import { getWorkout } from '../workouts/api'
import { writeLike } from './api'
import type { SocialProps } from './types'
export default function LikeButton({ account, post, onLike, onIdentity, onBusy, onUncertain, onMissing, disabled }: SocialProps & { account: Account; post: Workout; onLike: (v: { like_count: number; is_liked: boolean }) => void; onMissing?: () => void; disabled?: boolean }) {
  const [busy, setBusy] = useState(false); const [unknown, setUnknown] = useState(false); const [message, setMessage] = useState('')
  const [abandonDialog, setAbandonDialog] = useState(false)
  const dialog = useRef<HTMLDialogElement>(null); const cancel = useRef<HTMLButtonElement>(null); const abandonButton = useRef<HTMLButtonElement>(null); const countId = useId()
  const token = useRef(Symbol()); const alive = useRef(true); const sending = useRef(false); const uncertain = useRef(false)
  const generation = useRef(0); const write = useRef<AbortController | null>(null); const read = useRef<AbortController | null>(null)
  const [config] = useState(() => ({ onBusy, onUncertain }))
  useEffect(() => {
    const lock = token.current; const op = generation
    alive.current = true
    const unload = (event: BeforeUnloadEvent) => { if (uncertain.current) { event.preventDefault() } }
    window.addEventListener('beforeunload', unload)
    return () => { alive.current = false; op.current++; write.current?.abort(); read.current?.abort(); config.onBusy(lock, false); config.onUncertain(lock, false); window.removeEventListener('beforeunload', unload) }
  }, [config])
  useEffect(() => {
    const element = dialog.current
    if (abandonDialog && element && !element.open) { element.showModal(); cancel.current?.focus() }
    return () => { if (element?.open) element.close() }
  }, [abandonDialog])
  function closeDialog() { dialog.current?.close(); setAbandonDialog(false); abandonButton.current?.focus() }
  function mark(value: boolean) { uncertain.current = value; setUnknown(value); onUncertain(token.current, value); onBusy(token.current, sending.current || value) }
  async function identity(version: number) {
    const me = await getMe()
    if (!alive.current || version !== generation.current) return false
    if (me.id !== account.id) { mark(false); onIdentity(me, 'ログインしているユーザーが変わりました。コメントやいいねを確認してください。'); return false }
    return true
  }
  async function run(confirm = false) {
    if (sending.current || disabled || unknown && !confirm) return
    const version = ++generation.current; const active = () => alive.current && version === generation.current
    const controller = new AbortController(); if (confirm) read.current = controller; else write.current = controller
    const intended = !post.is_liked; let sent = false
    sending.current = true; setBusy(true); onBusy(token.current, true); setMessage('')
    try {
      if (!await identity(version) || !active()) return
      if (confirm) {
        const value = await getWorkout(post.id, account.id, controller.signal)
        if (!active()) return
        onLike({ like_count: value.like_count, is_liked: value.is_liked }); mark(false); setMessage('現在のいいねの状態を表示しました。')
      } else {
        const csrf = await getCsrf(); if (!active()) return
        sent = true
        const value = await writeLike(post.id, intended, account.id, csrf, controller.signal)
        if (!active()) return
        onLike({ like_count: value.like_count, is_liked: value.is_liked }); mark(false)
      }
    } catch (cause) {
      if (!active()) return
      const error = cause instanceof ApiError ? cause : new ApiError(0, '', '接続できません。')
      if (error.status === 401 || error.code === 'SOCIAL_OWNER_CHANGED' || error.code === 'RECORD_OWNER_CHANGED') {
        mark(false); if (error.status === 401) onIdentity(null, 'ログイン後に記録のいいねとコメントを確認してください。自動再送はしません。')
        else { try { const me = await getMe(); if (active()) onIdentity(me, error.message) } catch { if (active()) onIdentity(null) } }
      } else if (error.status === 404) { mark(false); onMissing?.(); setMessage('記録が見つかりません。') }
      else if (error.code === 'CSRF_FAILED') {
        try { if (await identity(version) && active()) { await getCsrf(); if (active()) setMessage('安全性の確認を更新しました。もう一度操作してください。') } } catch (cause) { if (active()) { if (cause instanceof ApiError && cause.status === 401) { mark(false); onIdentity(null) } else setMessage('安全性を確認できません。もう一度操作してください。') } }
      } else {
        if (sent && (error.status === 0 || error.status >= 500 || error.code === 'INVALID_RESPONSE')) mark(true)
        setMessage(uncertain.current ? 'いいねの結果が不明です。状態を確認してください。' : sent ? error.message : '未送信です。ログイン状態を確認できません。')
      }
    } finally { sending.current = false; if (active()) { setBusy(false); onBusy(token.current, uncertain.current) } }
  }
  return <div className="social-like"><button type="button" aria-label="いいね" aria-describedby={countId} aria-pressed={post.is_liked} disabled={busy || unknown || disabled} onClick={() => { void run() }}><span aria-hidden="true">{post.is_liked ? '♥' : '♡'}</span> いいね</button><span id={countId}>{post.like_count}件</span>{message && <p role="alert">{message}</p>}{unknown && <><button type="button" disabled={busy || disabled} onClick={() => { void run(true) }}>いいねの状態を確認</button><button ref={abandonButton} type="button" disabled={busy || disabled} onClick={() => { setAbandonDialog(true) }}>確認を中断</button></>}
    {abandonDialog && <dialog ref={dialog} role="alertdialog" aria-label="いいねの確認の中断" onCancel={event => { event.preventDefault(); closeDialog() }} onClose={() => { setAbandonDialog(false) }}><p>いいねが変更された可能性があり、状態は未確認です。確認を中断すると画面を離れられます。いいねをもう一度変更する前に現在の状態を確認してください。</p><button ref={cancel} type="button" onClick={closeDialog}>キャンセル</button><button type="button" onClick={() => { uncertain.current = false; onBusy(token.current, false); onUncertain(token.current, false); setMessage('確認を中断しました。いいねの状態は未確認です。'); closeDialog() }}>中断して画面を離れる</button></dialog>}
  </div>
}
