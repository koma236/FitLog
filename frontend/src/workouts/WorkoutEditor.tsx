import PhotoPicker from '../upload/PhotoPicker'
import { useState } from 'react'
import type { FieldErrors } from '../auth/api'
import { workoutEnergy } from './calories'
import { kinds } from './types'
import type { Workout } from './types'

type DraftExercise = { name: string; sets: { weight_kg: string; reps: string }[] }
function today() { return new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Tokyo' }).format(new Date()) }
export default function WorkoutEditor({ post, busy, fields, health, onSave, photo, onPhoto }: { post: Workout | null; busy: boolean; fields: FieldErrors; health: { weight: string | null; age: number | null }; onSave: (v: Record<string, unknown>) => void; photo: File | null; onPhoto: (v: File | null) => void }) {
  const [id] = useState(() => post?.id ?? crypto.randomUUID())
  const [day, setDay] = useState(post?.performed_on ?? today())
  const [note, setNote] = useState(post?.note ?? '')
  const [exercises, setExercises] = useState<DraftExercise[]>(post?.exercises.map(ex => ({ name: ex.name, sets: ex.sets.map(row => ({ weight_kg: String(Number(row.weight_kg)), reps: String(row.reps) })) })) ?? [{ name: '', sets: [{ weight_kg: '', reps: '' }] }])
  const [minutes, setMinutes] = useState(post?.energy_input.minutes == null ? '' : String(post.energy_input.minutes))
  const [kind, setKind] = useState(post?.energy_input.kind ?? '')
  const [visibility, setVisibility] = useState(post?.visibility ?? { minutes: 'private', kind: 'private' })
  const [recalculate, setRecalculate] = useState(false)
  const preview = workoutEnergy(health.weight, health.age, minutes === '' ? null : Number(minutes), kind || null)
  const changed = (post?.energy_input.minutes ?? null) !== (minutes === '' ? null : Number(minutes)) || (post?.energy_input.kind ?? null) !== (kind || null)
  const result = post && !changed && !(recalculate && preview !== null) ? post.energy?.kcal ?? null : preview
  const error = (path: string) => fields[path] ? <span className="field-error" id={'workout-' + path}>{fields[path].join(' ')}</span> : null
  const described = (path: string) => fields[path] ? 'workout-' + path : undefined
  function changeExercise(i: number, next: DraftExercise) { setExercises(old => old.map((ex, index) => i === index ? next : ex)) }
  return <form noValidate className="workout-editor" aria-label="記録フォーム" onSubmit={event => {
    event.preventDefault()
    if (busy) return
    onSave({ ...(post ? { recalculate: recalculate && preview !== null } : { id }), performed_on: day, note, exercises: exercises.map(ex => ({ name: ex.name, sets: ex.sets.map(row => ({ weight_kg: row.weight_kg, reps: row.reps === '' ? null : Number(row.reps) })) })), energy_input: { minutes: minutes === '' ? null : Number(minutes), kind: kind || null }, visibility })
  }}><h1>{post ? '記録を編集' : 'トレーニングを記録'}</h1><p>種目・セット・メモ・消費カロリーは会員間に公開されます。</p>
    <fieldset disabled={busy}><legend className="sr-only">記録の入力</legend>
      <label className="field">トレーニング日<input type="date" value={day} max={today()} aria-describedby={described('performed_on')} onChange={e => { setDay(e.target.value) }} />{error('performed_on')}</label>
      <section className="calorie-section"><h2>運動中の消費カロリー</h2><p>入力は任意。体重・年齢はプロフィールから使います。</p>
        <label className="field">運動した時間（分）<input aria-label="運動した時間（分）" type="number" min="1" max="240" step="1" value={minutes} aria-describedby={described('energy_input.minutes')} onChange={e => { setMinutes(e.target.value) }} />{error('energy_input.minutes')}<small>この種類で運動した時間。長い休憩は除きます。</small></label>
        <label className="field">運動時間の公開範囲<select value={visibility.minutes} aria-describedby={described('visibility.minutes')} onChange={e => { setVisibility(v => ({ ...v, minutes: e.target.value === 'public' ? 'public' : 'private' })) }}><option value="private">非公開</option><option value="public">公開</option></select>{error('visibility.minutes')}</label>
        <label className="field">トレーニングの種類<select value={kind} aria-describedby={described('energy_input.kind')} onChange={e => { setKind(e.target.value) }}><option value="">未選択</option>{Object.entries(kinds).map(([key, value]) => <option key={key} value={key}>{value}</option>)}</select>{error('energy_input.kind')}</label>
        <label className="field">トレーニングの種類の公開範囲<select value={visibility.kind} aria-describedby={described('visibility.kind')} onChange={e => { setVisibility(v => ({ ...v, kind: e.target.value === 'public' ? 'public' : 'private' })) }}><option value="private">非公開</option><option value="public">公開</option></select>{error('visibility.kind')}</label>
        {post && <label><input type="checkbox" checked={recalculate && preview !== null} disabled={preview === null} onChange={e => { setRecalculate(e.target.checked) }} />現在の身体情報で再計算</label>}
        <p aria-live="polite">消費カロリー（保存前の目安） <strong>{result === null ? '未計算' : `${result.toLocaleString('ja-JP')} kcal`}</strong></p>
        {post && !changed && !recalculate && <p>保存済みの結果を維持します。</p>}{post && changed && result === null && <p>変更後は消費カロリーが未計算になります。</p>}
        {preview === null && <p>再計算には体重・対象年齢（19〜59歳）・運動時間・種類が必要です。<a href="#profile-edit">プロフィールを編集</a></p>}
        <p className="privacy-note">消費カロリーは会員間に公開されます。運動時間と種類を公開すると、カロリーとの組合せから非公開の体重が推測される場合があります。計算結果の有無から、計算時に体重を登録していたことや年齢が対象範囲（19〜59歳）だったことなどが推測される場合もあります。</p>
        <details className="calorie-method"><summary>計算方法と対象について</summary><p>運動中の消費カロリーは MET × 体重kg × 分 ÷ 60 の概算です。安静時分を含みます。対象は19〜59歳。長い休憩は除き、記録の運動カロリーを1日の消費量へ追加しません。</p><p>一般的な筋トレ3.5 MET（02054）、スクワット・デッドリフト中心5.0 MET（02052）、高強度の筋トレ6.0 MET（02050）。<a href="https://pacompendium.com/conditioning-exercise/" target="_blank" rel="noreferrer">2024 Compendium</a></p></details>
      </section>
      {error('exercises')}
      {exercises.map((ex, i) => <fieldset key={i} className="exercise-fields"><legend>種目 {i + 1}</legend><label className="field">種目名<input value={ex.name} maxLength={160} aria-describedby={described(`exercises.${String(i)}.name`)} onChange={e => { changeExercise(i, { ...ex, name: e.target.value }) }} />{error(`exercises.${String(i)}.name`)}</label>{error(`exercises.${String(i)}.sets`)}
        {ex.sets.map((row, j) => <div className="set-fields" key={j}><span>{j + 1}</span><label>重量（kg）<input type="number" min="0" max="999.99" step="0.01" value={row.weight_kg} aria-label={`種目${String(i + 1)} セット${String(j + 1)} 重量（kg）`} aria-describedby={described(`exercises.${String(i)}.sets.${String(j)}.weight_kg`)} onChange={e => { changeExercise(i, { ...ex, sets: ex.sets.map((r, index) => index === j ? { ...r, weight_kg: e.target.value } : r) }) }} />{error(`exercises.${String(i)}.sets.${String(j)}.weight_kg`)}</label><label>回数<input type="number" min="1" max="999" step="1" value={row.reps} aria-label={`種目${String(i + 1)} セット${String(j + 1)} 回数`} aria-describedby={described(`exercises.${String(i)}.sets.${String(j)}.reps`)} onChange={e => { changeExercise(i, { ...ex, sets: ex.sets.map((r, index) => index === j ? { ...r, reps: e.target.value } : r) }) }} />{error(`exercises.${String(i)}.sets.${String(j)}.reps`)}</label><button type="button" disabled={ex.sets.length === 1} onClick={() => { changeExercise(i, { ...ex, sets: ex.sets.filter((_, index) => index !== j) }) }}>セット{j + 1}を削除</button></div>)}
        <button type="button" disabled={ex.sets.length >= 20} onClick={() => { changeExercise(i, { ...ex, sets: [...ex.sets, { weight_kg: '', reps: '' }] }) }}>＋ セットを追加（{ex.sets.length}/20）</button><button type="button" disabled={exercises.length === 1} onClick={() => { setExercises(old => old.filter((_, index) => index !== i)) }}>種目{i + 1}を削除</button>
      </fieldset>)}
      <button type="button" disabled={exercises.length >= 10} onClick={() => { setExercises(old => [...old, { name: '', sets: [{ weight_kg: '', reps: '' }] }]) }}>＋ 種目を追加（{exercises.length}/10）</button>
      {!post && <PhotoPicker file={photo} onFile={onPhoto} />}
      <label className="field">メモ<textarea aria-label="メモ" value={note} aria-describedby={described('note')} onChange={e => { setNote(e.target.value) }} />{error('note')}</label><div className="row"><a href={post ? '#record/' + post.id : '#profile'}>キャンセル</a><button type="submit">{busy ? '保存中…' : post ? '変更を保存' : '記録する'}</button></div>
    </fieldset>
  </form>
}
