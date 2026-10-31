import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, getMe } from '../auth/api'
import type { Account } from '../auth/api'
import Photo from '../upload/Photo'
import type { SocialProps } from './types'
import { searchUsers } from './followApi'
import type { Relation, SearchPage } from './followApi'
import FollowButton from './FollowButton'

export default function UserSearch({ account, onIdentity, onBusy, onUncertain }: SocialProps & { account: Account }) {
  const [input, setInput] = useState(''); const [query, setQuery] = useState({ q: '', epoch: 0 }); const [page, setPage] = useState<SearchPage | null>(null)
  const [busy, setBusy] = useState(false); const [message, setMessage] = useState(''); const [failed, setFailed] = useState<{ cursor?: string } | null>(null)
  const version = useRef(0); const viewGeneration = useRef(0); const controller = useRef<AbortController | null>(null); const locks = useRef(new Map<symbol, string>()); const [locked, setLocked] = useState(false)
  const imagePages = useRef<{ cursor?: string; ids: string[]; used: boolean }[]>([])
  const imageReads = useRef(new Set<AbortController>())
  const working = useCallback((id: string, token: symbol, value: boolean) => { if (value) locks.current.set(token, id); else locks.current.delete(token); setLocked(locks.current.size > 0); onBusy(token, value) }, [onBusy])
  const load = useCallback(async (cursor?: string) => {
    if (locks.current.size > 0) return
    if (!cursor) viewGeneration.current++
    const op = ++version.current; controller.current?.abort(); const abort = new AbortController(); controller.current = abort
    setBusy(true); setMessage(''); setFailed(null)
    try {
      const value = await searchUsers(query.q, account.id, abort.signal, cursor)
      if (version.current !== op) return
      const group = { cursor, ids: value.items.map(item => item.id), used: false }
      imagePages.current = cursor ? [...imagePages.current, group] : [group]
      setPage(old => cursor && old ? { ...value, items: [...old.items, ...value.items.filter(item => !old.items.some(prior => prior.id === item.id))] } : value)
    } catch (cause) {
      if (version.current !== op) return
      if (cause instanceof ApiError && cause.status === 401) { setPage(null); onIdentity(null) }
      else if (cause instanceof ApiError && cause.code === 'SOCIAL_OWNER_CHANGED') { setPage(null); try { const me = await getMe(); if (version.current === op) onIdentity(me) } catch { if (version.current === op) onIdentity(null) } }
      else { setMessage(cause instanceof Error ? cause.message : '検索できません。'); setFailed(cause instanceof ApiError && cause.code === 'INVALID_CURSOR' ? {} : { cursor }) }
    } finally { if (version.current === op) setBusy(false) }
  }, [account.id, query.q, onIdentity])
  useEffect(() => {
    setPage(null); void load()
    const op = version; const view = viewGeneration; const reads = imageReads.current
    return () => { op.current++; view.current++; controller.current?.abort(); for (const abort of reads) abort.abort() }
  }, [query, load])
  async function refreshImages(id: string) {
    const group = imagePages.current.find(item => item.ids.includes(id))
    if (!group || group.used) return
    group.used = true
    const op = viewGeneration.current; const abort = new AbortController(); imageReads.current.add(abort)
    try {
      const value = await searchUsers(query.q, account.id, abort.signal, group.cursor)
      if (viewGeneration.current !== op) return
      if (value.items.length !== group.ids.length || !value.items.every((item, i) => group.ids[i] === item.id)) {
        setMessage('一覧を最初から読み込み直してください。'); setFailed({}); return
      }
      setPage(old => old ? { ...old, items: old.items.map(item => {
        const fresh = value.items.find(next => next.id === item.id)
        return fresh && fresh.avatar?.id === item.avatar?.id ? { ...item, avatar: fresh.avatar } : item
      }) } : old)
    } catch (cause) {
      if (viewGeneration.current !== op) return
      if (cause instanceof ApiError && cause.status === 401) { setPage(null); onIdentity(null) }
      else if (cause instanceof ApiError && cause.code === 'SOCIAL_OWNER_CHANGED') { setPage(null); try { const me = await getMe(); if (viewGeneration.current === op) onIdentity(me) } catch { if (viewGeneration.current === op) onIdentity(null) } }
      else { setMessage('画像を読み込めません。最初から読み込み直してください。'); setFailed({}) }
    } finally { imageReads.current.delete(abort) }
  }
  function update(id: string, value: Relation, actorFollowing?: number) {
    setPage(old => old ? { ...old, items: old.items.map(item => item.id === id ? { ...item, ...value } : item.id === account.id && actorFollowing !== undefined ? { ...item, following_count: actorFollowing } : item) } : old)
  }
  return <section aria-label="ユーザー検索"><h1>ユーザー検索</h1><form role="search" onSubmit={event => { event.preventDefault(); if (!locked) { setPage(null); setQuery(old => ({ q: input, epoch: old.epoch + 1 })) } }}><label htmlFor="user-search">ユーザー名・表示名</label><input id="user-search" value={input} disabled={locked} onChange={event => { setInput(event.target.value) }} /><button disabled={locked} type="submit">検索</button></form>
    {busy && <p role="status">検索中…</p>}{message && <p role="alert">{message}</p>}{failed && <button disabled={busy || locked} onClick={() => { void load(failed.cursor) }}>検索を再試行</button>}
    {page?.items.length === 0 && !busy && <p>ユーザーが見つかりません。</p>}
    <ul className="user-results">{page?.items.map(item => <li key={item.id}><Photo avatar image={item.avatar} alt={item.display_name} onError={() => { void refreshImages(item.id) }} /><a href={'#profile/' + encodeURIComponent(item.username)}>{item.display_name}</a><p>@{item.username}</p><p>{item.following_count} フォロー中 · {item.follower_count} フォロワー</p>{!item.is_owner && <FollowButton account={account} target={item} disabled={locked && [...locks.current.values()].some(id => id !== item.id)} canStart={() => ![...locks.current.values()].some(id => id !== item.id)} onFollow={(value, count) => { update(item.id, value, count) }} onIdentity={onIdentity} onBusy={(token, value) => { working(item.id, token, value) }} onUncertain={onUncertain} />}</li>)}</ul>
    {page?.next_cursor && !message && <button disabled={busy || locked} onClick={() => { void load(page.next_cursor ?? undefined) }}>もっと見る</button>}
  </section>
}
