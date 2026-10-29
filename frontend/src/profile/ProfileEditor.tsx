import { useState } from 'react'
import type { SyntheticEvent } from 'react'
import type { FieldErrors } from '../auth/api'
import { calculate } from './calories'
import { EnergyCards, MethodHelp } from './ProfileView'
import { activities, energyKeys, formulas, healthKeys, labels, privateFlags } from './types'
import type { Health, Profile, ProfileKey } from './types'

type Props = { profile: Profile; busy: boolean; fields: FieldErrors; onSave: (body: Record<string, unknown>) => Promise<void> }
export default function ProfileEditor({ profile, busy, fields, onSave }: Props) {
  const [name, setName] = useState(profile.display_name)
  const [bio, setBio] = useState(profile.bio)
  const [values, setValues] = useState<Record<typeof healthKeys[number], string>>({ height: profile.health.height ?? '', weight: profile.health.weight ?? '', age: profile.health.age === null || profile.health.age === undefined ? '' : String(profile.health.age), formula: profile.health.formula ?? '', activity: profile.health.activity ?? '' })
  const [visibility, setVisibility] = useState(profile.visibility ?? privateFlags())
  const age = /^(0|[1-9][0-9]{0,2})$/.test(values.age) ? Number(values.age) : null
  const health: Health = { height: values.height || null, weight: values.weight || null, age, formula: values.formula || null, activity: values.activity || null }
  const preview = calculate(health)
  function submit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault()
    const ageValue = values.age === '' ? null : /^(0|[1-9][0-9]{0,2})$/.test(values.age) ? Number(values.age) : values.age
    void onSave({ display_name: name, bio, health: { ...health, age: ageValue }, visibility })
  }
  function privacy(key: ProfileKey) {
    const messages = fields[`visibility.${key}`]
    return <label className="privacy-control"><span>{labels[key]}の公開範囲</span><select disabled={busy} value={visibility[key]} onChange={event => { setVisibility({ ...visibility, [key]: event.target.value === 'public' ? 'public' : 'private' }) }}>
      <option value="private">非公開</option><option value="public">公開</option></select>
      {messages && <span role="alert">{messages.join(' ')}</span>}
    </label>
  }
  function error(key: string) { return fields[key] && <p id={`${key}-error`} className="field-error">{fields[key].join(' ')}</p> }
  return <form className="profile-card" onSubmit={submit}>
    <h1>プロフィールを編集</h1>
    {['_form', 'health._form', 'visibility._form'].map(key => fields[key] && <p key={key} className="field-error" role="alert">{fields[key].join(' ')}</p>)}
    <label className="field">表示名<input required disabled={busy} value={name} aria-invalid={Boolean(fields.display_name)} aria-describedby={fields.display_name ? 'display_name-error' : undefined} onChange={event => { setName(event.target.value) }} /></label>{error('display_name')}
    <div className="field"><label htmlFor="profile-bio">自己紹介</label><textarea id="profile-bio" disabled={busy} value={bio} aria-invalid={Boolean(fields.bio)} aria-describedby={fields.bio ? 'bio-error profile-bio-count' : 'profile-bio-count'} onChange={event => { setBio(event.target.value) }} /><span id="profile-bio-count" className="muted">{String(Array.from(bio.replace(/\r\n?/g, '\n')).length)} / 160文字</span></div>{error('bio')}
    <section className="calorie-section"><h2>カロリー計算の設定</h2>
      <p className="muted">入力は任意です。対象は19〜59歳。項目ごとに公開を選べます（初期値は非公開）。</p>
      <p className="privacy-note">公開したカロリー結果や他の公開項目から、非公開の値を推測できる場合があります。</p>
      {healthKeys.map(key => <div className="setting-row" key={key}><div><label className="field">{labels[key]}{key === 'height' ? '（cm）' : key === 'weight' ? '（kg）' : key === 'age' ? '（歳）' : ''}
        {key === 'formula' || key === 'activity' ? <select disabled={busy} value={values[key]} aria-invalid={Boolean(fields[`health.${key}`])} onChange={event => { setValues({ ...values, [key]: event.target.value }) }}>
          <option value="">未選択</option>{Object.entries(key === 'formula' ? formulas : activities).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
          : <input disabled={busy} type="text" inputMode={key === 'age' ? 'numeric' : 'decimal'} value={values[key]} aria-invalid={Boolean(fields[`health.${key}`])} onChange={event => { setValues({ ...values, [key]: event.target.value }) }} />}
      </label>{error(`health.${key}`)}</div>{privacy(key)}</div>)}
      <h2>計算結果の公開範囲</h2><p className="muted">1日の消費量と体重維持の摂取目安は同じ数値です。</p>
      <div className="result-settings">{energyKeys.map(key => <div key={key}>{privacy(key)}</div>)}</div>
      <div aria-live="polite"><EnergyCards energy={preview} visibility={visibility} owner /></div>
      {preview.bmr === null && <p role="status">計算に必要な身長・体重・19〜59歳の年齢・計算式の区分を入力してください。</p>}
      {preview.bmr !== null && preview.tdee === null && <p role="status">普段の活動量を選ぶと1日の目安を計算します。</p>}
      <MethodHelp />
    </section>
    <div className="form-actions"><a href="#profile" aria-disabled={busy} onClick={event => { if (busy) event.preventDefault() }}>キャンセル</a><button disabled={busy} type="submit">{busy ? '保存中…' : '変更を保存'}</button></div>
  </form>
}
