import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { HttpError, NetworkError, callApi, fetchView, resolveDeviceToken, sendEvent } from './api'
import { beat } from './heartbeat'
import { enqueue, flushQueue, loadQueue, newClientId } from './queue'
import type { QueuedEvent } from './queue'
import { effectiveFeatures, isStale } from './snapshot'
import type { Feature, ResidentView } from './types'
import { useNow } from './useNow'

const SNAPSHOT_KEY = 'isd.snapshot'
const OFFSET_KEY = 'isd.clockOffset'
const POLL_MS = 30_000
const HEARTBEAT_MS = 60_000

type Status = 'loading' | 'ready' | 'no-device' | 'unassigned'

export interface Ctx {
  status: Status
  view: ResidentView | null
  features: Record<string, Feature>
  online: boolean
  stale: boolean
  now: number
  pending: number
  refresh: () => Promise<void>
  /** Calls a device endpoint. Throws NetworkError when offline, HttpError for 4xx/5xx. */
  request: <T>(path: string, init?: RequestInit) => Promise<T>
  /** Returns 'sent' when delivered now, 'queued' when saved for later, 'duplicate' if already open. */
  submit: (
    ev: Omit<QueuedEvent, 'client_id'> & { client_id?: string },
  ) => Promise<'sent' | 'queued' | 'duplicate'>
}

export const ResidentCtx = createContext<Ctx | null>(null)

/** Server time minus device time, measured at the last successful fetch. */
function readOffset(): number {
  return Number(localStorage.getItem(OFFSET_KEY) ?? 0) || 0
}

function readSnapshot(): ResidentView | null {
  try {
    return JSON.parse(localStorage.getItem(SNAPSHOT_KEY) ?? 'null') as ResidentView | null
  } catch {
    return null
  }
}

export function ResidentProvider({ children }: { children: ReactNode }) {
  const { i18n } = useTranslation()
  const token = useRef<string | null>(resolveDeviceToken())
  const [view, setView] = useState<ResidentView | null>(readSnapshot)
  const [status, setStatus] = useState<Status>(token.current ? 'loading' : 'no-device')
  const [online, setOnline] = useState(true)
  const [pending, setPending] = useState(() => loadQueue().length)
  const [offset, setOffset] = useState(readOffset)
  const now = useNow() + offset // device clock corrected to the server's, so drift cannot extend a cache

  const flush = useCallback(async () => {
    if (!token.current) return
    const t = token.current
    const left = await flushQueue(async (ev) => {
      try {
        await sendEvent(t, ev)
        return true
      } catch (e) {
        if (e instanceof HttpError && e.status === 409) return true // already filed
        if (e instanceof HttpError && e.status >= 400 && e.status < 500) return true // unsendable; drop
        throw e
      }
    })
    setPending(left.length)
  }, [])

  const refresh = useCallback(async () => {
    if (!token.current) return
    try {
      const fresh = await fetchView(token.current)
      localStorage.setItem(SNAPSHOT_KEY, JSON.stringify(fresh))
      const off = Date.parse(fresh.generated_at) - Date.now()
      localStorage.setItem(OFFSET_KEY, String(off))
      setOffset(off)
      setView(fresh)
      setStatus('ready')
      setOnline(true)
      await flush()
    } catch (e) {
      if (e instanceof NetworkError) {
        setOnline(false)
        setStatus((s) => (s === 'loading' ? (readSnapshot() ? 'ready' : 'loading') : s))
      } else if (e instanceof HttpError && e.status === 401) setStatus('no-device')
      else if (e instanceof HttpError && e.status === 409) setStatus('unassigned')
    }
  }, [flush])

  useEffect(() => {
    void refresh()
    const id = setInterval(() => void refresh(), POLL_MS)
    const onUp = () => void refresh()
    const onDown = () => setOnline(false)
    window.addEventListener('online', onUp)
    window.addEventListener('offline', onDown)
    return () => {
      clearInterval(id)
      window.removeEventListener('online', onUp)
      window.removeEventListener('offline', onDown)
    }
  }, [refresh])

  useEffect(() => {
    // Health report every minute, for ready and not-yet-assigned devices alike. Best effort.
    if (!token.current || (status !== 'ready' && status !== 'unassigned')) return
    const run = () =>
      void beat(
        token.current as string,
        navigator,
        loadQueue().length,
        () => window.location.reload(),
        import.meta.env.VITE_APP_VERSION,
      ).catch(() => {})
    run()
    const id = setInterval(run, HEARTBEAT_MS)
    return () => clearInterval(id)
  }, [status])

  useEffect(() => {
    if (view) void i18n.changeLanguage(view.settings.language)
  }, [view, i18n])

  const stale = view ? isStale(view, now) : false
  useEffect(() => {
    if (stale) void refresh() // expired while online: fetch a fresh snapshot straight away
  }, [stale, refresh])

  const submit: Ctx['submit'] = useCallback(
    async (partial) => {
      const ev = { ...partial, client_id: partial.client_id ?? newClientId() } as QueuedEvent
      try {
        if (!token.current) throw new NetworkError('no token')
        await sendEvent(token.current, ev)
        void refresh()
        return 'sent'
      } catch (e) {
        if (e instanceof HttpError && e.status === 409) return 'duplicate'
        if (e instanceof NetworkError) {
          setPending(enqueue(ev).length)
          setOnline(false)
          return 'queued'
        }
        throw e
      }
    },
    [refresh],
  )

  const request = useCallback(async <T,>(path: string, init?: RequestInit) => {
    if (!token.current) throw new NetworkError('no token')
    return (await callApi(token.current, path, init)) as T
  }, [])

  const value = useMemo<Ctx>(
    () => ({
      status,
      view,
      features: view ? effectiveFeatures(view, now) : {},
      online,
      stale,
      now,
      pending,
      refresh,
      request,
      submit,
    }),
    [status, view, online, stale, now, pending, refresh, request, submit],
  )
  return <ResidentCtx.Provider value={value}>{children}</ResidentCtx.Provider>
}

export function useResident(): Ctx {
  const ctx = useContext(ResidentCtx)
  if (!ctx) throw new Error('useResident outside provider')
  return ctx
}

export class SimulationBlocked extends Error {
  constructor() {
    super('This is a simulation: nothing is sent or saved.')
  }
}

/** Feeds the resident screens a fixed ResidentView (sandbox and live mirror). No network, no writes. */
export function StaticResidentProvider({
  view,
  children,
}: {
  view: ResidentView
  children: ReactNode
}) {
  const value = useMemo<Ctx>(
    () => ({
      status: 'ready',
      view,
      features: view.features,
      online: true,
      stale: false,
      now: Date.parse(view.generated_at), // time travel: "now" is the simulated moment
      pending: 0,
      refresh: async () => {},
      request: async () => {
        throw new SimulationBlocked()
      },
      submit: async () => 'sent', // shows what the resident would see; nothing is delivered
    }),
    [view],
  )
  return <ResidentCtx.Provider value={value}>{children}</ResidentCtx.Provider>
}
