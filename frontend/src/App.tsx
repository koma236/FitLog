import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, getCsrf, getMe, signOut, submitAuth } from './auth/api'
import type { Account, FieldErrors } from './auth/api'
import AuthForm from './auth/AuthForm'
import ProfileScreen from './profile/ProfileScreen'
import WorkoutScreen from './workouts/WorkoutScreen'
import WorkoutFeed from './workouts/WorkoutFeed'
import type { Workout } from './workouts/types'

export default function App() {
  const profileLock = useRef<{ token: symbol; hash: string } | null>(null)
  const [profileSaving, setProfileSaving] = useState(false)
  const profileBusy = useCallback((token: symbol, saving: boolean) => {
    if (!saving && profileLock.current !== null && profileLock.current.token !== token) return
    profileLock.current = saving ? { token, hash: location.hash } : null
    setProfileSaving(saving)
  }, [])
  const [hash, setHash] = useState(location.hash)
  useEffect(() => {
    const changed = () => {
      if (profileLock.current !== null && location.hash !== profileLock.current.hash) history.replaceState(null, '', profileLock.current.hash)
      setHash(location.hash)
    }
    window.addEventListener('hashchange', changed)
    return () => { window.removeEventListener('hashchange', changed) }
  }, [])
  const workoutUnknown = useRef<symbol | null>(null)
  const workoutUncertain = useCallback((token: symbol, value: boolean) => {
    if (value) workoutUnknown.current = token
    else if (workoutUnknown.current === token) workoutUnknown.current = null
  }, [])
  const [savedWorkout, setSavedWorkout] = useState<Workout | null>(null)
  const clearSavedWorkout = useCallback(() => { setSavedWorkout(null) }, [])
  const [user, setUser] = useState<Account | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [fields, setFields] = useState<FieldErrors>({})
  const csrf = useRef('')
  const sending = useRef(false)
  const operation = useRef(0)
  const alive = useRef(true)

  const onIdentity = useCallback((next: Account | null, notice?: string) => { operation.current += 1; workoutUnknown.current = null; setSavedWorkout(null); if (notice) setMessage(notice); csrf.current = ''; profileLock.current = null; setProfileSaving(false); setUser(next) }, [])
  const onName = useCallback((id: string, name: string) => { setUser(previous => previous?.id === id ? { ...previous, display_name: name } : previous) }, [])
  const showProfile = hash === '#profile' || hash === '#profile-edit' || hash.startsWith('#profile/')
  const showWorkout = hash === '#record-new' || hash.startsWith('#record/') || hash.startsWith('#record-edit/')
  const workoutId = hash.startsWith('#record-edit/') ? hash.slice(13) : hash.startsWith('#record/') ? hash.slice(8) : null
  let target = 'me'
  if (hash.startsWith('#profile/')) {
    try { target = decodeURIComponent(hash.slice(9)) } catch { target = 'invalid-profile' }
  }

  const refreshCsrf = useCallback(async () => { csrf.current = await getCsrf() }, [])
  const restore = useCallback(async () => {
    try {
      const account = await getMe()
      if (alive.current) { setSavedWorkout(null); setUser(account) }
    } catch (error) {
      if (!alive.current) return
      if (error instanceof ApiError && error.status === 401) { setSavedWorkout(null); setUser(null) }
      else throw error
    }
  }, [])

  useEffect(() => {
    alive.current = true
    async function load() {
      try { await restore(); await refreshCsrf() }
      catch (error) { if (alive.current) setMessage(error instanceof Error ? error.message : '接続できません。') }
      finally { if (alive.current) setLoading(false) }
    }
    void load()
    return () => { alive.current = false }
  }, [restore, refreshCsrf])

  useEffect(() => {
    async function checkSession() {
      const version = operation.current
      try {
        const account = await getMe()
        if (alive.current && version === operation.current) { if (account.id !== user?.id) onIdentity(account, location.hash.startsWith('#record') ? 'ログインしているユーザーが変わりました。記録を開き直してください。' : undefined); else setUser(account) }
      } catch (error) {
        if (!alive.current || version !== operation.current) return
        if (error instanceof ApiError && error.status === 401) {
          onIdentity(null, workoutUnknown.current ? 'ログインが切れました。ログイン後に記録一覧で保存されたか確認してください。同じ内容を新しい記録として自動保存することはありません。' : 'セッションの有効期限が切れました。ログインしてください。')
          csrf.current = ''
        } else setMessage(error instanceof Error ? error.message : '接続できません。')
      }
    }
    if (!user) return
    const onFocus = () => { if (!sending.current && profileLock.current === null) void checkSession() }
    window.addEventListener('focus', onFocus)
    return () => { window.removeEventListener('focus', onFocus) }
  }, [user, onIdentity])

  async function failure(error: unknown) {
    if (!(error instanceof ApiError)) { setMessage('処理結果を確認できません。'); return }
    setFields(error.fields)
    setMessage(error.message)
    if (error.status === 403 && error.code === 'CSRF_FAILED') {
      try { await refreshCsrf(); setMessage('安全性の確認を更新しました。入力を確認してもう一度操作してください。') }
      catch { csrf.current = ''; setMessage('安全性の確認を更新できません。時間をおいてもう一度操作してください。') }
    } else if (error.status === 409 && error.code === 'ALREADY_AUTHENTICATED') {
      try { await restore(); await refreshCsrf() }
      catch (cause) { setMessage(cause instanceof Error ? cause.message : '接続できません。') }
    } else if (error.status === 401 && user) {
      setUser(null); csrf.current = ''; setMessage('セッションの有効期限が切れました。ログインしてください。')
    }
  }

  async function perform(action: () => Promise<void>) {
    if (sending.current) return
    operation.current += 1
    sending.current = true; setBusy(true); setMessage(''); setFields({})
    try {
      if (!csrf.current) await refreshCsrf()
      await action()
    } catch (error) { await failure(error) }
    finally { sending.current = false; if (alive.current) setBusy(false) }
  }

  async function authenticate(action: 'login' | 'signup', data: Record<string, string>) {
    await perform(async () => {
      const account = await submitAuth(action, data, csrf.current)
      setSavedWorkout(null); setUser(account)
      csrf.current = ''
      await refreshCsrf()
    })
  }

  return (
    <main className={user ? "app-shell" : "auth-shell"}>
      <div className="brand">Fit<span>Log</span></div>
      {message && <p role="alert" className="form-error">{message}</p>}
      {loading ? <p role="status">確認中…</p> : user ? (
        <section className="profile-frame">
          <nav className="profile-nav" aria-label="メニュー"><a aria-disabled={profileSaving} href="#" onClick={event => { if (profileSaving) event.preventDefault() }}>ホーム</a><a aria-disabled={profileSaving} href="#profile" onClick={event => { if (profileSaving) event.preventDefault() }}>プロフィール</a></nav>
          {!showProfile && !showWorkout && <><p className="eyebrow">HOME</p><h1>{user.display_name}さん</h1></>}
          <button type="button" disabled={busy || profileSaving} onClick={() => { void perform(async () => {
            await signOut(csrf.current); setSavedWorkout(null); setUser(null); csrf.current = ''; await refreshCsrf()
          }) }}>{busy ? '送信中…' : 'ログアウト'}</button>
          {showWorkout && <WorkoutScreen key={`${user.id}:${hash}`} account={user} id={workoutId} editing={hash.startsWith("#record-edit/")} initial={savedWorkout?.id === workoutId && savedWorkout.viewer_id === user.id ? savedWorkout : null} onIdentity={onIdentity} onBusy={profileBusy} onSaved={setSavedWorkout} onClearSaved={clearSavedWorkout} onUncertain={workoutUncertain} />}
          {showProfile && <ProfileScreen key={user.id} account={user} target={target} editing={hash === '#profile-edit'} onIdentity={onIdentity} onName={onName} onBusy={profileBusy} />}
          {!showWorkout && hash !== "#profile-edit" && <WorkoutFeed key={`${user.id}:${target}:${hash}`} account={user} username={target === "me" ? user.username : target} onIdentity={onIdentity} />}
        </section>
      ) : <AuthForm busy={busy} fields={fields} onSubmit={authenticate} onSwitch={() => { setMessage(''); setFields({}) }} />}
      {!loading && message && <button className="text-button" disabled={busy} onClick={() => {
        void perform(async () => { await restore(); await refreshCsrf() })
      }}>ログイン状態を確認</button>}
    </main>
  )
}
