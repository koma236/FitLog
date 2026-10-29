import type { Workout } from './types'
import { kinds } from './types'

export default function WorkoutCard({ post }: { post: Workout }) {
  return <article className="workout-card" aria-label={`${post.performed_on} の記録`}>
    <header><a href={'#profile/' + encodeURIComponent(post.author.username)}><strong>{post.author.display_name}</strong> @{post.author.username}</a><span>{post.performed_on} の記録</span></header>
    {post.exercises.map((exercise, i) => <section className="exercise-summary" key={i}><h3>{exercise.name}<small>{exercise.sets.length}セット</small></h3><p>{exercise.sets.map(row => `${String(Number(row.weight_kg))}kg × ${String(row.reps)}回`).join(' / ')}</p></section>)}
    {post.note && <p className="workout-note">{post.note}</p>}
    <div className="post-energy"><strong>消費カロリー {post.energy ? `${post.energy.kcal.toLocaleString('ja-JP')} kcal` : '未計算'}</strong>
      <p>{post.energy_input.minutes != null && <span>運動時間 {post.energy_input.minutes}分{post.is_owner && post.visibility?.minutes === 'private' ? '（非公開）' : ''} </span>}{post.energy_input.kind && <span>{kinds[post.energy_input.kind]}{post.is_owner && post.visibility?.kind === 'private' ? '（非公開）' : ''}</span>}</p>
    </div><a href={'#record/' + post.id}>記録の詳細</a>
  </article>
}
