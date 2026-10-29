import { useEffect, useRef, useState } from 'react'
import { ApiError, getMe } from '../auth/api'
import type { Account } from '../auth/api'
import { listWorkouts } from './api'
import type { Page } from './types'
import WorkoutCard from './WorkoutCard'

export default function WorkoutFeed({ account, username, onIdentity }: { account: Account; username: string; onIdentity: (v: Account | null) => void }) {
  const [page, setPage] = useState<Page | null>(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [invalid, setInvalid] = useState(false)
  const controller = useRef<AbortController | null>(null)
  const version = useRef(0)
  const sending = useRef(false)
  async function load(cursor?: string) {
    if (sending.current) return
    const op = ++version.current; const abort = new AbortController(); controller.current?.abort(); controller.current = abort
    sending.current = true; setBusy(true); setMessage('')
    try {
      const next = await listWorkouts(username, account.id, abort.signal, cursor)
      if (version.current !== op) return
      setPage(previous => cursor && previous ? { ...next, items: [...previous.items, ...next.items.filter(p => !previous.items.some(old => old.id === p.id))] } : next); setInvalid(false)
    } catch (error) {
      if (version.current !== op) return
      if (error instanceof ApiError && error.status === 401) { setPage(null); onIdentity(null) }
      else if (error instanceof ApiError && error.code === 'RECORD_OWNER_CHANGED') { setPage(null); try { const next = await getMe(); if (version.current === op) onIdentity(next) } catch { if (version.current === op) onIdentity(null) } }
      else { setInvalid(error instanceof ApiError && error.code === 'INVALID_CURSOR'); setMessage(cursor ? '続きを読み込めませんでした。' : '記録を読み込めませんでした。') }
    } finally { if (version.current === op) { sending.current = false; setBusy(false) } }
  }
  const [initialLoad] = useState(() => load)
  useEffect(() => {
    const operations = version
    void initialLoad()
    return () => { operations.current++; controller.current?.abort(); sending.current = false }
  }, [initialLoad])
  return <section aria-label="記録一覧" className="workout-feed"><h2>トレーニングの記録</h2>
    {username === account.username && <a className="button" href="#record-new">トレーニングを記録する</a>}
    {message && <div role="alert"><p>{invalid ? '一覧の続きが無効になりました。最初から読み込み直してください。' : message}</p><button disabled={busy} onClick={() => { void load(invalid ? undefined : page?.next_cursor ?? undefined) }}>{invalid ? '一覧を最初から読み込み直す' : 'もう一度読み込む'}</button></div>}
    {!page && !message && <p role="status">記録を読み込んでいます…</p>}
    {page?.items.length === 0 && <p>まだ記録がありません。</p>}
    {page?.items.map(post => <WorkoutCard key={post.id} post={post} />)}
    {page?.next_cursor && !message && <button disabled={busy} onClick={() => { void load(page.next_cursor ?? undefined) }}>{busy ? '読込み中…' : 'もっと見る'}</button>}
  </section>
}
