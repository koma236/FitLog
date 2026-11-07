/** Bounded GET-only load over the existing actors' guarded in-memory sessions. */
export function assertPerformanceState(actors, posts, following) {
  if (actors.length !== 2 || posts.length !== 2 || new Set(actors.map(a => a.id)).size !== 2 || new Set(posts.map(p => p.id)).size !== 2) throw Error('PERFORMANCE_PRECONDITION')
  for (let i = 0; i < 2; i++) {
    if (posts[i].owner_id !== actors[i].id || JSON.stringify(following[i]) !== JSON.stringify([posts[i].id])) throw Error('PERFORMANCE_PRECONDITION')
  }
}

/** @param {{sleep?: (ms: number) => Promise<unknown>, clock?: () => number, observe?: (rows: object[]) => void}} options */
export async function measure(send, { sleep = ms => new Promise(resolve => setTimeout(resolve, ms)), clock = () => performance.now(), observe = _rows => {} } = {}) {
  const rows = []; const began = clock(); let failed = false
  const jobs = [0, 1].map(async actor => {
    for (let slot = 0; slot < 100; slot++) {
      if (failed) return
      const due = began + slot * 1000
      await sleep(Math.max(0, due - clock()))
      if (failed) return
      if (clock() - due >= 1000) { failed = true; throw Error('MISSED_SLOT') }
      const route = ['all', 'following', 'detail'][(slot - 10 + 12) % 3]
      const start = clock()
      try {
        const result = await send(actor, route)
        if (result.status !== 200) throw Error('STATUS')
        if (slot >= 10) {
          const row = { actor, route, method: 'GET', status: 200, error: null, elapsed_ms: result.elapsed_ms ?? clock() - start }
          rows.push(row); observe(rows)
        }
      } catch { failed = true; throw Error('PERFORMANCE_FAILED') }
    }
  })
  const outcomes = await Promise.allSettled(jobs)
  if (outcomes.some(result => result.status === 'rejected')) throw Error('PERFORMANCE_FAILED')
  return rows
}
