import { isDeepStrictEqual } from 'node:util'

/** Stable record state; signed media capabilities naturally change with time. */
export function captureAllowed(aws, failed) { return !aws || !failed }

export function unchangedRecord(value) {
  const copy = structuredClone(value)
  const strip = item => {
    if (item && typeof item === 'object') {
      delete item.url; delete item.expires_at
      for (const nested of Object.values(item)) strip(nested)
    }
  }
  strip(copy)
  return copy
}

/** The sender owns the fixed origin, shared session, guard and send budget. */
export async function originContrast(send, { origin, owner, post, payload, marker }) {
  const check = condition => { if (!condition) throw Error('ORIGIN_CONTRAST_FAILED') }
  const read = async (path, options, status) => {
    const response = await send(path, options)
    try { check(response.status() === status); return await response.json() }
    finally { await response.dispose() }
  }
  try {
    const path = '/api/posts/' + post
    const before = await read(path, undefined, 200)
    check(typeof marker === 'string' && marker.length > 0 && marker.length <= 500 && marker !== before.note)
    const csrf = await read('/api/auth/csrf', undefined, 200)
    check(typeof csrf.csrf_token === 'string' && csrf.csrf_token.length > 0)
    const headers = { Origin: origin, 'X-CSRFToken': csrf.csrf_token, 'X-Record-Owner': owner, 'Content-Type': 'application/json' }
    // recalculate is a write-only required field; restore current writable facts.
    const restore = Object.fromEntries(Object.keys(payload).filter(key => key !== 'recalculate').map(key => [key, before[key]]))
    const positive = { ...restore, note: marker }
    const body = JSON.stringify({ ...positive, recalculate: false })
    const put = (data, originHeader = origin) => ({ method: 'PUT', headers: { ...headers, Origin: originHeader }, data })
    await read(path, put(body), 200)
    const changed = await read(path, undefined, 200)
    const projection = value => Object.fromEntries(Object.keys(restore).map(key => [key, value[key]]))
    check(isDeepStrictEqual(projection(changed), positive))
    await read(path, put(JSON.stringify({ ...restore, recalculate: false })), 200)
    const restored = await read(path, undefined, 200)
    check(isDeepStrictEqual(projection(restored), restore))
    const denied = await read(path, put(body, 'https://origin-probe.invalid'), 403)
    check(denied.code === 'CSRF_FAILED')
    const after = await read(path, undefined, 200)
    check(isDeepStrictEqual(unchangedRecord(after), unchangedRecord(restored)))
    return { positive: 200, restored: 200, negative: 403, unchanged: true }
  } catch { throw Error('ORIGIN_CONTRAST_FAILED') }
}
