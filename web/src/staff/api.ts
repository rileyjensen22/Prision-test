const KEY = 'isd.staffToken'
const AT_KEY = 'isd.staffTokenAt'
const REFRESH_AFTER_MS = 10 * 60 * 1000

// sessionStorage: the token disappears when the browser window closes.
export const getToken = (): string | null => sessionStorage.getItem(KEY)
export const setToken = (t: string | null) => {
  if (t) {
    sessionStorage.setItem(KEY, t)
    sessionStorage.setItem(AT_KEY, String(Date.now()))
  } else {
    sessionStorage.removeItem(KEY)
    sessionStorage.removeItem(AT_KEY)
  }
}

/**
 * Tokens expire after a short idle period on the server. While staff keep working, swap in a fresh
 * one every ten minutes; if they stop, the token simply runs out and they are signed out.
 */
let refreshing: Promise<void> | null = null
async function refreshIfDue(path: string): Promise<void> {
  const token = getToken()
  if (!token || path.startsWith('/auth/')) return
  if (Date.now() - Number(sessionStorage.getItem(AT_KEY) ?? 0) < REFRESH_AFTER_MS) return
  refreshing ??= (async () => {
    try {
      const res = await fetch('/api/auth/refresh', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      })
      if (res.ok) setToken(((await res.json()) as { token: string }).token)
    } catch {
      /* the real request below will report any problem */
    } finally {
      refreshing = null
    }
  })()
  await refreshing
}

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
  await refreshIfDue(path)
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
