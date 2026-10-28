import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

function response(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status, headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('readyの状態表示（FL01-AC3）', () => {
  it('初期表示は単独のstatusに確認中を表示する', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})))
    render(<App />)
    expect(screen.getAllByRole('status')).toHaveLength(1)
    expect(screen.getByRole('status')).toHaveTextContent(/^確認中$/)
  })

  it.each([
    [200, { status: 'ok' }, '利用可能'],
    [503, { status: 'unavailable' }, '準備未完了'],
    [200, { status: 'unavailable' }, '応答を確認できません'],
    [503, { status: 'ok' }, '応答を確認できません'],
    [500, { status: 'ok' }, '応答を確認できません'],
    [201, { status: 'ok' }, '応答を確認できません'],
    [200, {}, '応答を確認できません'],
    [200, null, '応答を確認できません'],
    [200, { status: 'ok', secret: 'unexpected' }, '応答を確認できません'],
  ])('HTTP %s / %j → %s', async (status, body, text) => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockResolvedValue(response(status, body)))
    render(<App />)
    expect(await screen.findByRole('status')).toBeInTheDocument()
    await screen.findByText(text)
    expect(screen.getByRole('status')).toHaveTextContent(text)
  })

  it('不正JSONは不正応答として表示する', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockResolvedValue(new Response('{', { status: 200 })))
    render(<App />)
    await screen.findByText('応答を確認できません')
    expect(screen.getByRole('status')).toHaveTextContent('応答を確認できません')
  })

  it('通信失敗を表示する', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockRejectedValue(new TypeError('network')))
    render(<App />)
    await screen.findByText('接続できません')
    expect(screen.getByRole('status')).toHaveTextContent('接続できません')
  })

  it('5秒でabortし、遅れて成功しても表示を戻さない', async () => {
    vi.useFakeTimers()
    let signal: AbortSignal | null | undefined
    let finish: ((value: Response) => void) | undefined
    vi.stubGlobal('fetch', vi.fn((_url: string, init: RequestInit) => {
      signal = init.signal
      return new Promise<Response>((resolve) => { finish = resolve })
    }))
    render(<App />)
    await act(async () => { await vi.advanceTimersByTimeAsync(4999) })
    expect(screen.getByRole('status')).toHaveTextContent('確認中')
    await act(async () => { await vi.advanceTimersByTimeAsync(1) })
    expect(screen.getByRole('status')).toHaveTextContent('接続できません')
    expect(signal?.aborted).toBe(true)
    await act(async () => {
      finish?.(response(200, { status: 'ok' }))
      await Promise.resolve()
    })
    expect(screen.getByRole('status')).toHaveTextContent('接続できません')
  })

  it('unmountでabortしてtimerを解放する', async () => {
    vi.useFakeTimers()
    let signal: AbortSignal | null | undefined
    let finish: ((value: Response) => void) | undefined
    vi.stubGlobal('fetch', vi.fn((_url: string, init: RequestInit) => {
      signal = init.signal
      return new Promise<Response>((resolve) => { finish = resolve })
    }))
    const { unmount } = render(<App />)
    unmount()
    expect(signal?.aborted).toBe(true)
    expect(vi.getTimerCount()).toBe(0)
    await act(async () => {
      finish?.(response(200, { status: 'ok' }))
      await Promise.resolve()
    })
  })
})
