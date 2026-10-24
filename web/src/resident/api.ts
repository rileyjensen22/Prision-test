import type { QueuedEvent } from './queue'
import type { ResidentView } from './types'

export class NetworkError extends Error {}
export class HttpError extends Error {
  status: number
  body: unknown
  constructor(status: number, body: unknown) {
    super(`HTTP ${status}`)
    this.status = status
    this.body = body
  }
}

export const TOKEN_KEY = 'isd.deviceToken'

/**
 * The device token arrives once, in the URL *fragment* (`/resident#device=...`). A fragment is never
 * sent to the web server, so the token cannot end up in its access logs. It is saved on the device
 * and removed from the address. A `?device=` query value is ignored (and removed) for the same reason.
 */
export function resolveDeviceToken(): string | null {
  const url = new URL(window.location.href)
  const fromHash = new URLSearchParams(url.hash.replace(/^#/, '')).get('device')
  const hadQuery = url.searchParams.has('device')
  if (fromHash || hadQuery) {
    url.searchParams.delete('device')
    window.history.replaceState(null, '', url.pathname + url.search)
  }
  if (fromHash) {
    localStorage.setItem(TOKEN_KEY, fromHash)
    return fromHash
  }
  return localStorage.getItem(TOKEN_KEY)
}

export async function callApi(
  token: string,
  path: string,
  init: RequestInit = {},
): Promise<unknown> {
  let res: Response
  try {
    res = await fetch(`/api${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', 'X-Device-Token': token },
    })
  } catch {
    throw new NetworkError('offline')
  }
  const body = await res.json().catch(() => null)
  if (!res.ok) throw new HttpError(res.status, body)
  return body
}

export const fetchView = (token: string) => callApi(token, '/device/view') as Promise<ResidentView>

export function sendEvent(token: string, ev: QueuedEvent): Promise<unknown> {
  if (ev.type === 'request')
    return callApi(token, '/device/requests', {
      method: 'POST',
      body: JSON.stringify({ client_id: ev.client_id, ...ev.payload }),
    })
  if (ev.type === 'lesson_complete')
    return callApi(
      token,
      `/device/courses/${ev.payload.code}/lessons/${ev.payload.lesson_id}/complete`,
      { method: 'POST' },
    )
  if (ev.type === 'reading_progress')
    return callApi(token, `/device/reading/${ev.payload.item_id}/progress`, {
      method: 'PUT',
      body: JSON.stringify({ page: ev.payload.page }),
    })
  if (ev.type === 'reading_bookmark')
    return callApi(token, `/device/reading/${ev.payload.item_id}/bookmarks/${ev.payload.page}`, {
      method: 'PUT',
      body: JSON.stringify({ on: ev.payload.on }),
    })
  return callApi(token, '/device/appeals', { method: 'POST', body: JSON.stringify(ev.payload) })
}

export const newOrderId = (): string => crypto.randomUUID()
