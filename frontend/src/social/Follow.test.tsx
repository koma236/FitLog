import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import App from '../App'
import { privateFlags } from '../profile/types'
import ProfileScreen from '../profile/ProfileScreen'

const actor = { id: '11111111-1111-4111-8111-111111111111', username: 'alice', display_name: 'Alice' }
const other = { id: '22222222-2222-4222-8222-222222222222', username: 'bob', display_name: 'Bob' }
const user = (following = false) => ({ ...other, avatar: null, is_owner: false, is_following: following, follower_count: following ? 1 : 0, following_count: 7 })
const reply = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status })
afterEach(() => { cleanup(); vi.unstubAllGlobals(); location.hash = '' })

function setup(options: { write?: () => Response | Promise<Response>; search?: (url: string) => Response | Promise<Response>; identity?: () => Response; profileFollowing?: boolean; timeline?: (url: string, following: boolean) => Response } = {}) {
  let following = false
  const calls: string[] = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    calls.push(url)
    if (url === '/api/auth/me') return Promise.resolve(options.identity?.() ?? reply({ ...actor, email: 'alice@example.test' }))
    if (url === '/api/auth/csrf') return Promise.resolve(reply({ csrf_token: 'csrf' }))
    if (url.endsWith('/follow')) {
      if (options.write) return Promise.resolve(options.write())
      following = init?.method === 'POST'
      expect(new Headers(init?.headers).get('X-Social-Owner')).toBe(actor.id)
      expect(init?.body).toBeUndefined()
      return Promise.resolve(reply({ viewer_id: actor.id, user_id: other.id, is_following: following, follower_count: following ? 1 : 0, following_count: following ? 1 : 0 }))
    }
    if (url.startsWith('/api/users/search')) return Promise.resolve(options.search?.(url) ?? reply({ viewer_id: actor.id, items: [{ ...actor, avatar: null, is_owner: true, is_following: false, follower_count: 0, following_count: 0 }, user(following)], next_cursor: null }))
    if (url === '/api/users/bob') return Promise.resolve(reply({ ...user(options.profileFollowing ?? following), viewer_id: actor.id, bio: '', health: {}, energy: {} }))
    if (url === '/api/users/me') return Promise.resolve(reply({ ...actor, viewer_id: actor.id, avatar: null, bio: '', is_owner: true, is_following: false, follower_count: 0, following_count: options.profileFollowing ? 5 : 0, health: { height: null, weight: null, age: null, formula: null, activity: null }, energy: { bmr: null, tdee: null, intake: null }, visibility: privateFlags() }))
    if (url.startsWith('/api/timeline/')) return Promise.resolve(options.timeline?.(url, following) ?? reply({ viewer_id: actor.id, items: [], next_cursor: null }))
    return Promise.resolve(reply({ viewer_id: actor.id, items: [], next_cursor: null }))
  }))
  return calls
}

it('search submits only on button/Enter, follows without optimism and links to profile', async () => {
  location.hash = '#search'; const calls = setup(); render(<App />)
  expect(await screen.findByRole('link', { name: 'Bob' })).toHaveAttribute('href', '#profile/bob')
  expect(screen.queryByRole('region', { name: '記録一覧' })).not.toBeInTheDocument()
  expect(screen.getAllByRole('button', { name: 'フォローする' })).toHaveLength(1)
  fireEvent.change(screen.getByLabelText('ユーザー名・表示名'), { target: { value: '  B%_\\🙂  ' } })
  expect(calls.filter(url => url.startsWith('/api/users/search'))).toHaveLength(1)
  fireEvent.submit(screen.getByRole('search'))
  await waitFor(() => { expect(calls.some(url => url.includes(new URLSearchParams({ q: '  B%_\\🙂  ' }).toString()))).toBe(true) })
  fireEvent.click(screen.getByRole('button', { name: 'フォローする' }))
  expect(await screen.findByRole('button', { name: 'フォローを解除' })).toHaveAttribute('aria-pressed', 'true')
  fireEvent.click(screen.getByRole('link', { name: 'Bob' }))
  expect(await screen.findByRole('heading', { name: 'Bob' })).toBeVisible()
  expect(screen.getByText('7 フォロー中')).toBeVisible()
})

it('uncertain follow prevents inverse writes, then recovers using profile GET', async () => {
  location.hash = '#search'; const calls = setup({ write: () => reply({ code: 'INTERNAL_ERROR' }, 500) }); render(<App />)
  fireEvent.click(await screen.findByRole('button', { name: 'フォローする' }))
  expect(await screen.findByText('フォローの結果が不明です。状態を確認してください。')).toBeVisible()
  expect(screen.getByRole('button', { name: 'フォローする' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'フォローの状態を確認' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'フォローする' })).toBeEnabled())
  expect(calls.filter(url => url.endsWith('/follow'))).toHaveLength(1)
  expect(calls).toContain('/api/users/bob')
})

it.each(['', '#timeline/all', '#search?x', '#timeline/foo'])('routes %s to exactly one timeline', async hash => {
  location.hash = hash; const calls = setup(); render(<App />)
  expect(await screen.findByRole('tab', { name: hash === '#timeline/all' ? 'すべて' : 'フォロー中', selected: true })).toBeVisible()
  expect(screen.getAllByRole('region', { name: '記録一覧' })).toHaveLength(1)
  expect(calls.some(url => url.startsWith('/api/timeline/' + (hash === '#timeline/all' ? 'all' : 'following')))).toBe(true)
  expect(calls.some(url => url.includes('/posts'))).toBe(false)
})

it('drops stale search responses after the query changes', async () => {
  location.hash = '#search'
  let resolve: ((v: Response) => void) | undefined
  setup({ search: url => url.includes('q=old') ? new Promise<Response>(done => { resolve = done }) : reply({ viewer_id: actor.id, items: [], next_cursor: null }) })
  render(<App />); await screen.findByLabelText('ユーザー名・表示名')
  fireEvent.change(screen.getByLabelText('ユーザー名・表示名'), { target: { value: 'old' } }); fireEvent.submit(screen.getByRole('search'))
  fireEvent.change(screen.getByLabelText('ユーザー名・表示名'), { target: { value: 'new' } }); fireEvent.submit(screen.getByRole('search'))
  await screen.findByText('ユーザーが見つかりません。')
  await act(async () => { resolve?.(reply({ viewer_id: actor.id, items: [user()], next_cursor: null })); await Promise.resolve() })
  expect(screen.queryByText('Bob')).not.toBeInTheDocument()
})

it('refreshes expired search avatars once per page using the same query', async () => {
  location.hash = '#search'; let reads = 0
  setup({ search: () => { reads++; return reply({ viewer_id: actor.id, items: [{ ...user(), avatar: { id: '33333333-3333-4333-8333-333333333333', url: '/api/media/content/' + String(reads), expires_at: '2026-11-01T00:00:00Z', width: 40, height: 40, content_type: 'image/png' } }], next_cursor: null }) } })
  render(<App />)
  fireEvent.error(await screen.findByRole('img', { name: 'Bob' }))
  await waitFor(() => { expect(reads).toBe(2) })
  fireEvent.error(await screen.findByRole('img', { name: 'Bob' }))
  expect(reads).toBe(2)
})

it('does not show follow success until the server confirms, and keeps target following count', async () => {
  location.hash = '#search'
  let finish: ((v: Response) => void) | undefined
  setup({ write: () => new Promise<Response>(resolve => { finish = resolve }) }); render(<App />)
  fireEvent.click(await screen.findByRole('button', { name: 'フォローする' }))
  await waitFor(() => { expect(finish).toBeDefined() })
  expect(screen.getByRole('button', { name: 'フォローする' })).toBeDisabled()
  expect(screen.queryByRole('button', { name: 'フォローを解除' })).not.toBeInTheDocument()
  await act(async () => { finish?.(reply({ viewer_id: actor.id, user_id: other.id, is_following: true, follower_count: 2, following_count: 1 })); await Promise.resolve() })
  expect(await screen.findByRole('button', { name: 'フォローを解除' })).toBeEnabled()
  expect(screen.getByText('7 フォロー中 · 2 フォロワー')).toBeVisible()
  expect(screen.getByText('1 フォロー中 · 0 フォロワー')).toBeVisible()
})

it('keeps an identity check failure unsent with no automatic follow request', async () => {
  location.hash = '#search'; let reads = 0
  const calls = setup({ identity: () => { reads++; return reads === 1 ? reply({ ...actor, email: 'alice@example.test' }) : reply({ code: 'INTERNAL_ERROR' }, 500) } }); render(<App />)
  fireEvent.click(await screen.findByRole('button', { name: 'フォローする' }))
  expect(await screen.findByText('未送信です。ログイン状態を確認できません。')).toBeVisible()
  expect(calls.filter(url => url.endsWith('/follow'))).toHaveLength(0)
})

it('recovers the actor count as well as the target relation after a lost successful response', async () => {
  location.hash = '#search'
  setup({ write: () => reply({ code: 'INTERNAL_ERROR' }, 500), profileFollowing: true }); render(<App />)
  fireEvent.click(await screen.findByRole('button', { name: 'フォローする' }))
  fireEvent.click(await screen.findByRole('button', { name: 'フォローの状態を確認' }))
  expect(await screen.findByRole('button', { name: 'フォローを解除' })).toBeEnabled()
  expect(screen.getByText('5 フォロー中 · 0 フォロワー')).toBeVisible()
  expect(screen.getByText('7 フォロー中 · 1 フォロワー')).toBeVisible()
})

it.each(['pending', 'unknown'])('locks profile reload during a %s follow until explicit resolution', async mode => {
  location.hash = '#profile/bob'
  setup({ write: () => mode === 'pending' ? new Promise<Response>(() => {}) : reply({ code: 'INTERNAL_ERROR' }, 500) }); render(<App />)
  fireEvent.click(await screen.findByRole('button', { name: 'フォローする' }))
  if (mode === 'unknown') await screen.findByRole('button', { name: 'フォローの状態を確認' })
  expect(screen.getByRole('button', { name: '画像を再読み込み' })).toBeDisabled()
  expect(screen.getByRole('link', { name: 'ホーム' })).toHaveAttribute('aria-disabled', 'true')
})

it('serializes follow writes across different search rows without disabling active recovery', async () => {
  location.hash = '#search'
  const third = { ...user(), id: '33333333-3333-4333-8333-333333333333', username: 'charlie', display_name: 'Charlie' }
  setup({ search: () => reply({ viewer_id: actor.id, items: [user(), third], next_cursor: null }), write: () => reply({ code: 'INTERNAL_ERROR' }, 500) }); render(<App />)
  const bob = (await screen.findByRole('link', { name: 'Bob' })).closest('li')
  const charlie = screen.getByRole('link', { name: 'Charlie' }).closest('li')
  if (!bob || !charlie) throw new Error('Missing search rows')
  fireEvent.click(within(bob).getByRole('button', { name: 'フォローする' }))
  await screen.findByRole('button', { name: 'フォローの状態を確認' })
  expect(within(charlie).getByRole('button', { name: 'フォローする' })).toBeDisabled()
  expect(within(bob).getByRole('button', { name: 'フォローの状態を確認' })).toBeEnabled()
})

it('keeps a pending avatar refresh when continuation starts in the same search generation', async () => {
  location.hash = '#search'
  let initialReads = 0; let finish: ((v: Response) => void) | undefined
  const avatar = (url: string) => ({ id: '44444444-4444-4444-8444-444444444444', url, expires_at: '2026-11-01T00:00:00Z', width: 40, height: 40, content_type: 'image/png' })
  setup({ search: url => {
    if (url.includes('cursor=')) return reply({ viewer_id: actor.id, items: [], next_cursor: null })
    initialReads++
    return initialReads === 1 ? reply({ viewer_id: actor.id, items: [{ ...user(), avatar: avatar('/old') }], next_cursor: 'more' }) : new Promise<Response>(resolve => { finish = resolve })
  } }); render(<App />)
  fireEvent.error(await screen.findByRole('img', { name: 'Bob' }))
  await waitFor(() => { expect(finish).toBeDefined() })
  fireEvent.click(screen.getByRole('button', { name: 'もっと見る' }))
  await waitFor(() => { expect(screen.queryByRole('button', { name: 'もっと見る' })).not.toBeInTheDocument() })
  await act(async () => { finish?.(reply({ viewer_id: actor.id, items: [{ ...user(), avatar: avatar('/new') }], next_cursor: 'more' })); await Promise.resolve() })
  expect(screen.getByRole('img', { name: 'Bob' })).toHaveAttribute('src', '/new')
})

it('notifies the profile parent when a follow result becomes unknown', async () => {
  const uncertain = new Set<symbol>()
  setup({ write: () => reply({ code: 'INTERNAL_ERROR' }, 500) })
  render(<ProfileScreen account={{ ...actor, email: 'alice@example.test' }} target="bob" editing={false} onIdentity={() => {}} onName={() => {}} onBusy={() => {}} onUncertain={(token, value) => { if (value) uncertain.add(token); else uncertain.delete(token) }} />)
  fireEvent.click(await screen.findByRole('button', { name: 'フォローする' }))
  await screen.findByRole('button', { name: 'フォローの状態を確認' })
  expect(uncertain.size).toBe(1)
})

it('follows from a profile then freshly reads the home first page with the new member post', async () => {
  location.hash = '#search'
  const post = { viewer_id: actor.id, id: '55555555-5555-4555-8555-555555555555', author: { ...other, avatar: null }, image: null, is_owner: false, performed_on: '2026-01-01', note: 'Bobの新着記録', created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z', exercises: [{ name: 'Squat', sets: [{ weight_kg: '60.00', reps: 10 }] }], energy: null, energy_input: {}, comment_count: 0, like_count: 0, is_liked: false }
  const calls = setup({ timeline: (_url, following) => reply({ viewer_id: actor.id, items: following ? [post] : [], next_cursor: null }) }); render(<App />)
  fireEvent.click(await screen.findByRole('link', { name: 'Bob' }))
  fireEvent.click(await screen.findByRole('button', { name: 'フォローする' }))
  await screen.findByRole('button', { name: 'フォローを解除' })
  fireEvent.click(screen.getByRole('link', { name: 'ホーム' }))
  expect(await screen.findByText('Bobの新着記録')).toBeVisible()
  expect(calls.filter(url => url.startsWith('/api/timeline/following'))).toEqual(['/api/timeline/following'])
})

it('retains search items and retries exactly the failed continuation cursor', async () => {
  location.hash = '#search'; let nextReads = 0
  const calls = setup({ search: url => {
    if (!url.includes('cursor=')) return reply({ viewer_id: actor.id, items: [user()], next_cursor: 'same-cursor' })
    nextReads++
    return nextReads === 1 ? reply({ code: 'INTERNAL_ERROR', message: '続きを取得できません。' }, 500) : reply({ viewer_id: actor.id, items: [], next_cursor: null })
  } }); render(<App />)
  await screen.findByRole('link', { name: 'Bob' }); fireEvent.click(screen.getByRole('button', { name: 'もっと見る' }))
  await screen.findByRole('button', { name: '検索を再試行' })
  expect(screen.getByRole('link', { name: 'Bob' })).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: '検索を再試行' }))
  await waitFor(() => { expect(nextReads).toBe(2) })
  expect(calls.filter(url => url.includes('cursor='))).toEqual(['/api/users/search?q=&cursor=same-cursor', '/api/users/search?q=&cursor=same-cursor'])
  expect(screen.getByRole('link', { name: 'Bob' })).toBeVisible()
})

it.each([401, 409])('clears search pagination data on identity failure %s without resending', async status => {
  location.hash = '#search'
  const calls = setup({ search: url => url.includes('cursor=') ? reply({ code: status === 401 ? 'AUTH_REQUIRED' : 'SOCIAL_OWNER_CHANGED', message: '本人を確認してください。' }, status) : reply({ viewer_id: actor.id, items: [user()], next_cursor: 'more' }) }); render(<App />)
  await screen.findByRole('link', { name: 'Bob' }); fireEvent.click(screen.getByRole('button', { name: 'もっと見る' }))
  await waitFor(() => { expect(screen.queryByRole('link', { name: 'Bob' })).not.toBeInTheDocument() })
  expect(calls.filter(url => url.includes('cursor='))).toHaveLength(1)
})
