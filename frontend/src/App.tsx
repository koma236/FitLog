import { useEffect, useState } from 'react'

type ReadyMessage = '確認中' | '利用可能' | '準備未完了' | '接続できません' | '応答を確認できません'

function validHealth(body: unknown): body is { status: string } {
  return typeof body === 'object' && body !== null && 'status' in body
    && typeof body.status === 'string' && Object.keys(body).length === 1
}

export default function App() {
  const [message, setMessage] = useState<ReadyMessage>('確認中')

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    let timedOut = false
    const timeout = window.setTimeout(() => {
      timedOut = true
      controller.abort()
      if (active) setMessage('接続できません')
    }, 5000)

    async function loadReady(): Promise<void> {
      try {
        const response = await fetch('/api/health/ready', {
          signal: controller.signal, headers: { Accept: 'application/json' },
        })
        let body: unknown
        try {
          body = await response.json()
        } catch {
          if (active && !timedOut) setMessage('応答を確認できません')
          return
        }
        if (!active || timedOut) return
        if (validHealth(body) && response.status === 200 && body.status === 'ok') {
          setMessage('利用可能')
        } else if (validHealth(body) && response.status === 503 && body.status === 'unavailable') {
          setMessage('準備未完了')
        } else {
          setMessage('応答を確認できません')
        }
      } catch {
        if (active) setMessage('接続できません')
      } finally {
        window.clearTimeout(timeout)
      }
    }

    void loadReady()
    return () => {
      active = false
      controller.abort()
      window.clearTimeout(timeout)
    }
  }, [])

  return (
    <main>
      <p className="eyebrow">FITLOG / LOCAL DEVELOPMENT</p>
      <h1>ローカル基盤</h1>
      <p>API・データベースの準備状態</p>
      <p role="status" aria-live="polite" className="readiness">{message}</p>
    </main>
  )
}
