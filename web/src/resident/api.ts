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

const TOKEN_KEY = 'isd.deviceToken'

/** The device token arrives once as ?device=...; it is stored and removed from the address. */
export function resolveDeviceToken(): string | null {
  const url = new URL(window.location.href)
  const fromUrl = url.searchParams.get('device')
  if (fromUrl) {
    localStorage.setItem(TOKEN_KEY, fromUrl)
    url.searchParams.delete('device')
    window.history.replaceState(null, '', url.pathname + url.search + url.hash)
    return fromUrl
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
  return callApi(token, '/device/appeals', { method: 'POST', body: JSON.stringify(ev.payload) })
}

export const newOrderId = (): string => crypto.randomUUID()
