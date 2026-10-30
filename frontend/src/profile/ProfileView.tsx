import Photo from '../upload/Photo'
import { activities, energyKeys, formulas, healthKeys, labels } from './types'
import type { Energy, Profile, Visibility } from './types'

export function MethodHelp() {
  return <details className="calorie-method"><summary>計算方法と対象について</summary>
    <p>すべて推定値です。対象はこのアプリでは19〜59歳。基礎代謝の目安はMifflin–St Jeor式による安静時代謝の推定で、実測値ではありません。</p>
    <p>1日の消費量は仕事・日常・運動を含めた普段の活動量の参考係数1.5 / 1.75 / 2.1を使います。摂取目安は体重維持の参考値で、1日の消費量と同じです。記録の運動カロリーを日次へ追加しません。</p>
    <a href="https://pubmed.ncbi.nlm.nih.gov/2305711/" target="_blank" rel="noreferrer">代謝推定式の原著</a>
  </details>
}
export function EnergyCards({ energy, visibility, owner }: { energy: Partial<Energy>; visibility?: Visibility; owner: boolean }) {
  return <div className="energy-grid">{energyKeys.filter(key => Object.hasOwn(energy, key)).map(key => <div className="energy-card" key={key}>
    <span>{labels[key]}</span><strong>{energy[key] === null || energy[key] === undefined ? '未計算' : `${energy[key].toLocaleString('ja-JP')} kcal/日`}</strong>
    {owner && visibility?.[key] === 'private' && <small>非公開</small>}
  </div>)}</div>
}
export default function ProfileView({ profile, onImageError }: { profile: Profile; onImageError?: () => void }) {
  const health = profile.health
  const fields = healthKeys.filter(key => Object.hasOwn(health, key))
  function text(key: typeof healthKeys[number]): string {
    const value = health[key]
    if (value === null || value === undefined) return '未入力'
    if (key === 'formula') return formulas[String(value)] ?? ''
    if (key === 'activity') return activities[String(value)] ?? ''
    return `${String(value)} ${key === 'height' ? 'cm' : key === 'weight' ? 'kg' : '歳'}`
  }
  return <>
    <section className="profile-card"><div className="profile-heading"><Photo image={profile.avatar} avatar alt={profile.display_name} onError={onImageError} /><div><h1>{profile.display_name}</h1><p className="muted">@{profile.username}</p></div>
      {profile.is_owner && <a className="button-link" href="#profile-edit">プロフィールを編集</a>}</div>
      <p className="bio">{profile.bio || '自己紹介はまだありません。'}</p>
    </section>
    {(fields.length > 0 || Object.keys(profile.energy).length > 0) && <section className="profile-card" aria-label="カロリーと身体情報">
      {Object.keys(profile.energy).length > 0 && <><h2>カロリーの目安</h2><EnergyCards energy={profile.energy} visibility={profile.visibility} owner={profile.is_owner} /></>}
      {profile.is_owner && <p className="muted">自分には非公開の項目も表示されます。</p>}
      <dl className="health-list">{fields.map(key => <div key={key}><dt>{labels[key]} {profile.is_owner && profile.visibility?.[key] === 'private' && <small>非公開</small>}</dt><dd>{text(key)}</dd></div>)}</dl>
      {Object.keys(profile.energy).length > 0 && <MethodHelp />}
    </section>}
  </>
}
