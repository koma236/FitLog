import { useEffect, useRef, useState } from 'react'
import { ApiError, getCsrf, getMe } from '../auth/api'
import type { Account } from '../auth/api'
import { getProfile } from '../profile/api'
import type { SocialProps } from './types'
import { writeFollow } from './followApi'
import type { FollowResult, Relation } from './followApi'

type Props = SocialProps & { account: Account; target: { id: string; username: string } & Relation; onFollow: (value: Relation, actorFollowing?: number) => void; disabled?: boolean; canStart?: () => boolean }
export default function FollowButton({ account, target, onFollow, onIdentity, onBusy, onUncertain, disabled, canStart }: Props) {
  const [busy, setBusy] = useState(false); const [unknown, setUnknown] = useState(false); const [message, setMessage] = useState(''); const [abandon, setAbandon] = useState(false)
  const token = useRef(Symbol('follow')); const generation = useRef(0); const alive = useRef(true); const sending = useRef(false); const uncertain = useRef(false)
  const controller = useRef<AbortController | null>(null); const dialog = useRef<HTMLDialogElement>(null); const cancel = useRef<HTMLButtonElement>(null); const opener = useRef<HTMLButtonElement>(null)
  const [config] = useState(() => ({ onBusy, onUncertain }))
  useEffect(() => {
    const op = generation; const lock = token.current; alive.current = true
    const unload = (event: BeforeUnloadEvent) => { if (uncertain.current) event.preventDefault() }
    window.addEventListener('beforeunload', unload)
    return () => { alive.current = false; op.current++; controller.current?.abort(); config.onBusy(lock, false); config.onUncertain(lock, false); window.removeEventListener('beforeunload', unload) }
  }, [config])
  useEffect(() => { const element = dialog.current; if (abandon && element && !element.open) { element.showModal(); cancel.current?.focus() }; return () => { if (element?.open) element.close() } }, [abandon])
  function mark(value: boolean) { uncertain.current = value; setUnknown(value); onUncertain(token.current, value); onBusy(token.current, sending.current || value) }
  async function run(confirm = false) {
    if (sending.current || disabled || unknown && !confirm || canStart?.() === false) return
    const version = ++generation.current; const active = () => alive.current && version === generation.current
    controller.current?.abort(); const abort = new AbortController(); controller.current = abort
    sending.current = true; setBusy(true); onBusy(token.current, true); setMessage(''); let sent = false
    try {
      const me = await getMe(); if (!active()) return
      if (me.id !== account.id) { mark(false); onIdentity(me); return }
      if (confirm) {
        const [profile, owner] = await Promise.all([
          getProfile(target.username, account.id, abort.signal),
          getProfile('me', account.id, abort.signal),
        ])
        if (!active()) return
        if (profile.id !== target.id) throw new ApiError(200, 'INVALID_RESPONSE', '対象を確認できません。')
        onFollow({ is_following: profile.is_following, follower_count: profile.follower_count, following_count: profile.following_count }, owner.following_count); mark(false); setMessage('現在のフォローの状態を表示しました。')
      } else {
        const csrf = await getCsrf(); if (!active()) return
        sent = true
        const value: FollowResult = await writeFollow(target.id, !target.is_following, account.id, csrf, abort.signal)
        if (!active()) return
        // Result.following_count belongs to the actor; target.following_count stays unchanged.
        onFollow({ is_following: value.is_following, follower_count: value.follower_count, following_count: target.following_count }, value.following_count); mark(false)
      }
    } catch (cause) {
      if (!active()) return
      const error = cause instanceof ApiError ? cause : new ApiError(0, '', '接続できません。')
      if (error.status === 401 || ['SOCIAL_OWNER_CHANGED', 'PROFILE_OWNER_CHANGED'].includes(error.code)) {
        mark(false)
        if (error.status === 401) onIdentity(null)
        else { try { const me = await getMe(); if (active()) onIdentity(me) } catch { if (active()) onIdentity(null) } }
      } else if (error.code === 'CSRF_FAILED') { setMessage('安全性を確認できません。もう一度操作してください。') }
      else {
        if (sent && (error.status === 0 || error.status >= 500 || error.code === 'INVALID_RESPONSE')) mark(true)
        setMessage(uncertain.current ? 'フォローの結果が不明です。状態を確認してください。' : sent || confirm ? error.message : '未送信です。ログイン状態を確認できません。')
      }
    } finally { sending.current = false; if (active()) { setBusy(false); onBusy(token.current, uncertain.current) } }
  }
  const close = () => { dialog.current?.close(); setAbandon(false); opener.current?.focus() }
  return <div className="follow-control"><button type="button" disabled={busy || unknown || disabled} aria-pressed={target.is_following} onClick={() => { void run() }}>{target.is_following ? 'フォローを解除' : 'フォローする'}</button>
    {message && <p role="alert">{message}</p>}{unknown && <><button type="button" disabled={busy || disabled} onClick={() => { void run(true) }}>フォローの状態を確認</button><button type="button" ref={opener} disabled={busy || disabled} onClick={() => { setAbandon(true) }}>確認を中断</button></>}
    {abandon && <dialog ref={dialog} aria-label="フォローの確認の中断" role="alertdialog" onCancel={event => { event.preventDefault(); close() }}><p>フォローが変更された可能性があり、状態は未確認です。確認を中断すると画面を離れられます。再操作する前に状態を確認してください。</p><button ref={cancel} type="button" onClick={close}>キャンセル</button><button type="button" onClick={() => { uncertain.current = false; onBusy(token.current, false); onUncertain(token.current, false); setMessage('確認を中断しました。フォローの状態は未確認です。'); close() }}>中断して画面を離れる</button></dialog>}
  </div>
}
