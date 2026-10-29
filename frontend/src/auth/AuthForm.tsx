import { useState } from 'react'
import type { SyntheticEvent } from 'react'
import type { FieldErrors } from './api'

type Props = {
  busy: boolean
  fields: FieldErrors
  onSubmit: (action: 'login' | 'signup', data: Record<string, string>) => Promise<void>
  onSwitch: () => void
}

export default function AuthForm({ busy, fields, onSubmit, onSwitch }: Props) {
  const [signup, setSignup] = useState(false)
  const [values, setValues] = useState({ username: '', display_name: '', email: '', password: '' })
  function submit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = signup ? values : { email: values.email, password: values.password }
    void onSubmit(signup ? 'signup' : 'login', data)
  }
  const inputs = [
    ...(signup ? [
      { name: 'username' as const, label: 'ユーザー名', type: 'text', autoComplete: 'username', maxLength: 30 },
      { name: 'display_name' as const, label: '表示名', type: 'text', autoComplete: 'nickname', maxLength: 50 },
    ] : []),
    { name: 'email' as const, label: 'メールアドレス', type: 'email', autoComplete: 'email', maxLength: 254 },
    { name: 'password' as const, label: 'パスワード', type: 'password', autoComplete: signup ? 'new-password' : 'current-password', maxLength: 128 },
  ]
  return (
    <form className="auth-form" onSubmit={submit}>
      <p className="eyebrow">{signup ? 'START YOUR JOURNAL' : 'WELCOME BACK'}</p>
      <h1>{signup ? 'FitLogをはじめよう。' : 'おかえりなさい。'}</h1>
      {inputs.map(input => (
        <div className="field" key={input.name}>
          <label htmlFor={input.name}>{input.label}</label>
          <input name={input.name} type={input.type} autoComplete={input.autoComplete} maxLength={input.maxLength} id={input.name} required disabled={busy} value={values[input.name]}
            aria-invalid={Boolean(fields[input.name])} aria-describedby={fields[input.name] ? `${input.name}-error` : undefined}
            onChange={event => { setValues({ ...values, [input.name]: event.target.value }) }} />
          {fields[input.name] && <p className="field-error" id={`${input.name}-error`}>{fields[input.name]?.join(' ')}</p>}
        </div>
      ))}
      {signup && <p className="muted">パスワードは12〜128文字で、推測されにくいものを設定してください。</p>}
      <button className="primary" type="submit" disabled={busy}>{busy ? '送信中…' : signup ? '登録する' : 'ログイン'}</button>
      <button className="text-button" type="button" disabled={busy} onClick={() => {
        setSignup(!signup); setValues({ ...values, password: '' }); onSwitch()
      }}>{signup ? 'ログイン画面へ' : '新規登録'}</button>
    </form>
  )
}
