import { afterEach, expect, it, vi } from 'vitest'
import { writeImage } from './api'
import { getWorkout } from '../workouts/api'
import { ApiError } from '../auth/api'

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })
it.each([{ image: true, deadline: 45000 }, { image: false, deadline: 10000 }])('uses the approved timeout for image=$image', async ({ image, deadline }) => {
  vi.useFakeTimers()
  let aborted = false
  vi.stubGlobal('fetch', vi.fn((_input: RequestInfo | URL, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
    init?.signal?.addEventListener('abort', () => { aborted = true; reject(new DOMException('Aborted', 'AbortError')) })
  })))
  const controller = new AbortController()
  const result = image ? writeImage('/api/posts/id/image', 'actor', false, 'csrf', new File(['pixels'], 'photo.png', { type: 'image/png' }), 'operation', controller.signal) : getWorkout('id', 'actor', controller.signal)
  // Observe rejection immediately so the deadline cannot produce an unhandled promise.
  const settled = result.catch((error: unknown) => error)
  await vi.advanceTimersByTimeAsync(deadline - 1); expect(aborted).toBe(false)
  await vi.advanceTimersByTimeAsync(1); expect(aborted).toBe(true)
  expect(await settled).toBeInstanceOf(ApiError)
})
it.each([false, true])('sends exactly one approved multipart field named image for avatar=%s', async avatar => {
  const file = new File(['fixed synthetic image'], 'photo.png', { type: 'image/png' })
  vi.stubGlobal('fetch', vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
    expect(init?.body).toBeInstanceOf(FormData)
    const body = init?.body as FormData
    // Approved FL-05 design §3 and OpenAPI: image is the sole multipart property.
    expect([...body.keys()]).toEqual(['image'])
    expect(body.get('image')).toBe(file)
    expect(new Headers(init?.headers).has('Content-Type')).toBe(false)
    return Promise.resolve(new Response(JSON.stringify({ viewer_id: 'actor' }), { status: 200 }))
  }))
  await writeImage(avatar ? '/api/users/me/avatar' : '/api/posts/id/image', 'actor', avatar, 'csrf', file, 'operation', new AbortController().signal)
})
