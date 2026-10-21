const KEY = 'isd.staffToken'

// sessionStorage: the token disappears when the browser window closes.
export const getToken = (): string | null => sessionStorage.getItem(KEY)
export const setToken = (t: string | null) =>
  t ? sessionStorage.setItem(KEY, t) : sessionStorage.removeItem(KEY)

export class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, detail: unknown) {
    super(`HTTP ${status}`)
    this.status = status
    this.detail = detail
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken()
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  })
  const body = await res.json().catch(() => null)
  if (res.status === 401 && token) {
    setToken(null)
    window.dispatchEvent(new Event('isd-staff-logout'))
  }
  if (!res.ok) throw new ApiError(res.status, body?.detail ?? body)
  return body as T
}

export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

export const put = <T>(path: string, body: unknown) =>
  api<T>(path, { method: 'PUT', body: JSON.stringify(body) })

/** A readable message from an API error. */
export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const d = e.detail as { code?: string; message?: string } | string | null
    if (typeof d === 'string') return d
    if (d && typeof d === 'object' && 'message' in d) return `${d.message} (${d.code ?? e.status})`
    if (Array.isArray(d)) return 'Please check the form fields.'
    return `Request failed (${e.status})`
  }
  return 'Could not reach the server.'
}

export const fmt = (iso: string | null | undefined): string =>
  iso ? new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—'
