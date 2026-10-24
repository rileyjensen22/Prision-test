import { afterEach, expect, test, vi } from 'vitest'

import { beat, collectHealth } from './heartbeat'

afterEach(() => vi.restoreAllMocks())

test('health numbers only: storage in MB and whether a camera and microphone exist', async () => {
  const h = await collectHealth(
    {
      onLine: true,
      storage: { estimate: async () => ({ usage: 5 * 1024 * 1024, quota: 200 * 1024 * 1024 }) },
      mediaDevices: { enumerateDevices: async () => [{ kind: 'videoinput' }] },
    },
    3,
    '1.2.3',
  )
  expect(h).toEqual({
    storage_used_mb: 5,
    storage_quota_mb: 200,
    camera: 'ok',
    microphone: 'missing',
    app_version: '1.2.3',
    queue_pending: 3,
    online: true,
  })
})

test('missing browser features give unknown, never an error', async () => {
  const h = await collectHealth({}, 0)
  expect(h.camera).toBe('unknown')
  expect(h.storage_quota_mb).toBe(0)
  const broken = await collectHealth(
    {
      storage: {
        estimate: async () => {
          throw new Error('x')
        },
      },
      mediaDevices: {
        enumerateDevices: async () => {
          throw new Error('x')
        },
      },
    },
    0,
  )
  expect(broken.microphone).toBe('unknown')
})

test('nothing but the allowed fields is ever sent', async () => {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify({ commands: [] })))
  vi.stubGlobal('fetch', fetchMock)
  await beat('tok', {}, 0, () => {})
  const body = JSON.parse(
    (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body as string,
  )
  expect(Object.keys(body).sort()).toEqual(
    [
      'ack',
      'app_version',
      'camera',
      'microphone',
      'online',
      'queue_pending',
      'storage_quota_mb',
      'storage_used_mb',
    ].sort(),
  )
})

test('a restart command is acknowledged first, then the app reloads', async () => {
  const sent: { ack: number[] }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url: string, init: RequestInit) => {
      const body = JSON.parse(init.body as string)
      sent.push(body)
      return new Response(
        JSON.stringify({ commands: body.ack.length ? [] : [{ id: 9, kind: 'restart' }] }),
      )
    }),
  )
  const reload = vi.fn()
  await beat('tok', {}, 0, reload)
  expect(sent.map((b) => b.ack)).toEqual([[], [9]])
  expect(reload).toHaveBeenCalledTimes(1)
})
