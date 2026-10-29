import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, getCsrf, getMe } from '../auth/api'
import type { Account, FieldErrors } from '../auth/api'
import { getProfile, saveProfile } from './api'
import ProfileEditor from './ProfileEditor'
import ProfileView from './ProfileView'
import type { Profile } from './types'

type Props = { account: Account; target: string; editing: boolean; onIdentity: (account: Account | null) => void; onName: (id: string, name: string) => void; onBusy: (token: symbol, busy: boolean) => void }
export default function ProfileScreen({ account, target, editing, onIdentity, onName, onBusy }: Props) {
  const [loaded, setLoaded] = useState<{ key: string; value: Profile } | null>(null)
  const [message, setMessage] = useState('')
  const [fields, setFields] = useState<FieldErrors>({})
  const [busy, setBusy] = useState(false)
  const [draftEpoch, setDraftEpoch] = useState(0)
  const [reload, setReload] = useState(0)
  const [uncertain, setUncertain] = useState(false)
  const lockToken = useRef(Symbol('profile-write'))
  const alive = useRef(true)
  const sending = useRef(false)
  const csrf = useRef('')
  const generation = useRef(0)
  const write = useRef<AbortController | null>(null)
  const active = useCallback((version: number) => alive.current && generation.current === version, [])
  const invalidate = useCallback(() => { generation.current++ }, [])
  const key = `${account.id}:${target}:${String(editing)}:${String(reload)}`
  const profile = loaded?.key === key ? loaded.value : null

  useEffect(() => {
    alive.current = true
    const token = lockToken.current
    return () => { alive.current = false; invalidate(); write.current?.abort(); csrf.current = ''; onBusy(token, false) }
  }, [onBusy, invalidate])
  useEffect(() => {
    const controller = new AbortController()
    const version = ++generation.current
    setLoaded(null); setFields({}); setMessage(''); setUncertain(false)
    async function load() {
      try {
        const value = await getProfile(target, account.id, controller.signal)
        if (active(version)) setLoaded({ key, value })
      } catch (error) {
        if (!active(version) || controller.signal.aborted) return
        if (error instanceof ApiError && error.status === 401) { setLoaded(null); onIdentity(null) }
        else setMessage(error instanceof Error ? error.message : '接続できません。')
      }
    }
    void load()
    return () => { controller.abort(); invalidate() }
  }, [account.id, target, key, onIdentity, active, invalidate])

  async function identityMatches(owner: string): Promise<boolean> {
    const current = await getMe()
    if (!alive.current) return false
    if (current.id === owner) return true
    generation.current++; setLoaded(null); csrf.current = ''; setFields({})
    onIdentity(current); location.hash = '#profile'
    return false
  }
  async function save(data: Record<string, unknown>) {
    if (!profile || !profile.is_owner || sending.current) return
    const owner = profile.id
    const version = generation.current
    const controller = new AbortController()
    write.current = controller; sending.current = true; onBusy(lockToken.current, true)
    setBusy(true); setMessage(''); setFields({}); setUncertain(false)
    try {
      if (!await identityMatches(owner) || !active(version)) return
      if (!csrf.current) csrf.current = await getCsrf()
      if (!active(version)) return
      const value = await saveProfile(data, owner, csrf.current, controller.signal)
      if (!active(version)) return
      onName(value.id, value.display_name)
      setLoaded({ key, value }); location.hash = '#profile'
    } catch (error) {
      if (!active(version)) return
      if (error instanceof ApiError) {
        if (error.status === 401) { generation.current++; setLoaded(null); csrf.current = ''; onIdentity(null); return }
        if (error.status === 409 && error.code === 'PROFILE_OWNER_CHANGED') {
          setLoaded(null); csrf.current = ''
          try {
            if (await identityMatches(owner)) { setReload(v => v + 1); location.hash = '#profile' }
          } catch (cause) {
            if (cause instanceof ApiError && cause.status === 401) onIdentity(null)
            else if (active(version)) { setMessage('ログイン状態を確認できません。'); setUncertain(true) }
          }
          return
        }
        if (error.status === 403 && error.code === 'CSRF_FAILED') {
          try {
            if (!await identityMatches(owner)) return
            csrf.current = await getCsrf()
            if (active(version)) setMessage('安全性の確認を更新しました。入力を確認してもう一度保存してください。')
          } catch (cause) {
            if (active(version)) {
              csrf.current = ''
              if (cause instanceof ApiError && cause.status === 401) { setLoaded(null); onIdentity(null) }
              else setMessage('安全性の確認を更新できません。時間をおいてもう一度操作してください。')
            }
          }
          return
        }
        setFields(error.fields)
        setUncertain(error.status === 0 || error.status >= 500 || error.code === 'INVALID_RESPONSE')
        setMessage(error.message)
      } else { setMessage('処理結果を確認できません。'); setUncertain(true) }
    } finally {
      sending.current = false; onBusy(lockToken.current, false)
      if (alive.current) setBusy(false)
    }
  }
  async function recover() {
    if (sending.current) return
    const version = generation.current
    const controller = new AbortController()
    write.current = controller; sending.current = true; onBusy(lockToken.current, true); setBusy(true)
    try {
      if (!await identityMatches(account.id) || !active(version)) return
      const value = await getProfile(target, account.id, controller.signal)
      if (!active(version)) return
      setLoaded({ key, value }); setDraftEpoch(v => v + 1); setFields({}); setMessage(''); setUncertain(false)
    } catch (error) {
      if (!active(version)) return
      if (error instanceof ApiError && error.status === 401) { setLoaded(null); onIdentity(null) }
      else setMessage(error instanceof Error ? error.message : '接続できません。')
    } finally {
      sending.current = false; onBusy(lockToken.current, false)
      if (alive.current) setBusy(false)
    }
  }
  return <div className="profile-content">
    {message && <p role="alert" className="form-error">{message}</p>}
    {profile ? editing ? <ProfileEditor key={`${key}:${String(draftEpoch)}`} profile={profile} busy={busy} fields={fields} onSave={save} /> : <ProfileView profile={profile} /> : !message && <p role="status">プロフィールを読み込んでいます…</p>}
    {(uncertain || (!profile && message)) && <button disabled={busy} type="button" onClick={() => { void recover() }}>{editing ? '保存状態を読み直す（入力を破棄）' : 'もう一度読み込む'}</button>}
  </div>
}
