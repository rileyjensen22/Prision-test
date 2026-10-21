import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { api, getToken, setToken } from './api'

beforeEach(() => sessionStorage.clear())
afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

function stubFetch() {
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? 'GET'} ${url}`)
      const body = url.endsWith('/auth/refresh') ? { token: 'fresh-token' } : { ok: true }
      return new Response(JSON.stringify(body), { status: 200 })
    }),
  )
  return calls
}

test('a recent token is used as is', async () => {
  const calls = stubFetch()
  setToken('old-token')
  await api('/staff/summary')
  expect(calls).toEqual(['GET /api/staff/summary'])
  expect(getToken()).toBe('old-token')
})

test('after ten minutes of activity the token is swapped for a fresh one', async () => {
  vi.useFakeTimers()
  const calls = stubFetch()
  setToken('old-token')
  vi.advanceTimersByTime(11 * 60 * 1000)
  await api('/staff/summary')
  expect(calls).toEqual(['POST /api/auth/refresh', 'GET /api/staff/summary'])
  expect(getToken()).toBe('fresh-token')
})

test('a 401 signs the user out', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response('{"detail":"no"}', { status: 401 })),
  )
  setToken('expired')
  const out = vi.fn()
  window.addEventListener('isd-staff-logout', out)
  await expect(api('/staff/summary')).rejects.toThrow()
  expect(getToken()).toBeNull()
  expect(out).toHaveBeenCalled()
})
