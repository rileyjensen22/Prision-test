import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import { Notice } from '../../ui/Notice'
import { EmptyState } from '../../ui/States'
import { NetworkError } from '../api'
import { BackLink, Card } from '../components'
import { useResident } from '../ResidentContext'
import { clock, errorCode, remainingSeconds } from './helpers'
import { startLoopback } from './loopback'
import type { Loopback } from './loopback'
import { SAMPLE_MS, TamperDetector, sampleVideo } from './tamper'

interface Contact {
  id: number
  name: string
  type: 'family' | 'friend' | 'attorney'
  available: boolean
}
interface VideoCall {
  call_id: number
  privileged: boolean
  monitored: boolean
  max_seconds: number
  started_at: string
  status: string
  duration_seconds: number | null
}
interface Booking {
  id: number
  contact_id: number
  starts_at: string
  minutes: number
  status: string
}
type Notice = { kind: 'ok' | 'error' | 'tamper'; text: string }

export function Video() {
  const { t } = useTranslation()
  const { request, refresh, view, features } = useResident()
  const navigate = useNavigate()
  const [tab, setTab] = useState<'now' | 'schedule'>('now')
  const [contacts, setContacts] = useState<Contact[] | null>(null)
  const [bookings, setBookings] = useState<Booking[]>([])
  const [active, setActive] = useState<VideoCall | null>(null)
  const [notice, setNotice] = useState<Notice | null>(null)

  const f = features['video']
  useEffect(() => {
    if (f && !f.allowed) navigate('/resident/locks?feature=video', { replace: true })
  }, [f, navigate])

  const load = useCallback(() => {
    request<Contact[]>('/device/contacts')
      .then(setContacts)
      .catch(() => setNotice({ kind: 'error', text: t('calls.needsConnection') }))
    request<Booking[]>('/device/video-bookings')
      .then(setBookings)
      .catch(() => {})
  }, [request, t])
  useEffect(load, [load])

  const fail = useCallback(
    (e: unknown) =>
      setNotice({
        kind: 'error',
        text:
          e instanceof NetworkError
            ? t('calls.needsConnection')
            : t(`video.err.${errorCode(e)}`, { defaultValue: t('video.err.ERROR') }),
      }),
    [t],
  )

  async function begin(path: string, body?: unknown) {
    setNotice(null)
    try {
      setActive(
        await request<VideoCall>(path, {
          method: 'POST',
          ...(body ? { body: JSON.stringify(body) } : {}),
        }),
      )
    } catch (e) {
      fail(e)
    }
  }

  const done = useCallback(
    (n: Notice | null) => {
      setActive(null)
      setNotice(n)
      load()
      void refresh()
    },
    [load, refresh],
  )

  if (active) return <InCall call={active} onDone={done} />

  const allowance = view?.allowances.find((a) => a.feature === 'video')
  const nameOf = (id: number) => contacts?.find((c) => c.id === id)?.name ?? ''

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6">
      <BackLink />
      <h1 className="text-h1 font-bold">{t('video.title')}</h1>
      {allowance && (
        <p data-testid="video-left">
          {t('video.left', { n: Math.max(0, allowance.limit - allowance.used) })}
        </p>
      )}
      {notice && (
        <Notice
          tone={notice.kind === 'ok' ? 'ok' : notice.kind === 'tamper' ? 'notice' : 'danger'}
          role={notice.kind === 'ok' ? 'status' : 'alert'}
          data-testid={notice.kind === 'tamper' ? 'video-tamper' : 'video-notice'}
        >
          {notice.text}
        </Notice>
      )}
      <div className="flex gap-3" role="tablist">
        {(['now', 'schedule'] as const).map((k) => (
          <button
            key={k}
            role="tab"
            aria-selected={tab === k}
            onClick={() => setTab(k)}
            className={`min-h-touch rounded-ctl border-2 px-6 py-3 text-label font-bold ${
              tab === k ? 'border-primary bg-primary-soft' : 'border-line bg-surface'
            }`}
          >
            {t(`video.tab.${k}`)}
          </button>
        ))}
      </div>

      {tab === 'now' ? (
        <>
          <ul className="space-y-3">
            {(contacts ?? []).map((c) => (
              <li key={c.id}>
                <Card data-testid={`video-contact-${c.type}`}>
                  <p className="text-label font-bold">{c.name}</p>
                  <p>{t(`calls.type.${c.type}`)}</p>
                  <button
                    disabled={!c.available}
                    onClick={() => void begin('/device/video-calls', { contact_id: c.id })}
                    className="mt-2 min-h-touch rounded-ctl bg-primary px-6 py-3 text-label font-bold text-primary-ink hover:brightness-110 disabled:opacity-40"
                  >
                    {c.available ? t('video.start') : t('calls.unavailable')}
                  </button>
                </Card>
              </li>
            ))}
          </ul>
          {contacts?.length === 0 && <EmptyState title={t('calls.none')} />}
        </>
      ) : (
        <Schedule
          contacts={contacts ?? []}
          bookings={bookings}
          nameOf={nameOf}
          onChanged={load}
          onStart={(id) => void begin(`/device/video-bookings/${id}/start`)}
          onError={fail}
        />
      )}
    </div>
  )
}

function InCall({ call, onDone }: { call: VideoCall; onDone: (n: Notice | null) => void }) {
  const { t } = useTranslation()
  const { request, now } = useResident()
  const localRef = useRef<HTMLVideoElement>(null)
  const remoteRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const loopRef = useRef<Loopback | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const finished = useRef(false)

  /** Turns the camera and microphone off. Safe to call more than once. */
  const stopMedia = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current)
    timerRef.current = null
    loopRef.current?.close()
    loopRef.current = null
    streamRef.current?.getTracks().forEach((tr) => tr.stop())
    streamRef.current = null
  }, [])

  const finish = useCallback(
    async (how: 'end' | 'tamper' | 'denied', signal?: string, coveredMs?: number) => {
      if (finished.current) return
      finished.current = true
      stopMedia() // the camera goes off before anything else happens
      try {
        if (how === 'tamper')
          await request(`/device/video-calls/${call.call_id}/tamper`, {
            method: 'POST',
            body: JSON.stringify({ signal, covered_ms: coveredMs }),
          })
        else await request(`/device/calls/${call.call_id}/end`, { method: 'POST' })
      } catch {
        // the server closes calls the device never ended
      }
      onDone(
        how === 'tamper'
          ? { kind: 'tamper', text: t('video.tamperEnded') }
          : how === 'denied'
            ? { kind: 'error', text: t('video.cameraDenied') }
            : { kind: 'ok', text: t('video.ended') },
      )
    },
    [call.call_id, onDone, request, stopMedia, t],
  )

  useEffect(() => {
    let cancelled = false
    const canvas = document.createElement('canvas')
    const detector = new TamperDetector()
    ;(async () => {
      let stream: MediaStream
      try {
        // The camera is only ever opened here, after the server has started this call.
        stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true })
      } catch {
        if (!cancelled) void finish('denied')
        return
      }
      if (cancelled || finished.current) {
        stream.getTracks().forEach((tr) => tr.stop())
        return
      }
      streamRef.current = stream
      if (localRef.current) {
        localRef.current.srcObject = stream
        void localRef.current.play().catch(() => {})
      }
      try {
        const loop = await startLoopback(stream)
        if (cancelled || finished.current) return loop.close()
        loopRef.current = loop
        if (remoteRef.current) {
          remoteRef.current.srcObject = loop.remote
          void remoteRef.current.play().catch(() => {})
        }
      } catch {
        // the demo link failed; the self-view still works
      }
      timerRef.current = setInterval(() => {
        if (!localRef.current) return
        const stats = sampleVideo(localRef.current, canvas)
        if (!stats) return
        const verdict = detector.push(stats) // only two numbers, never the picture
        if (verdict.covered && verdict.signal)
          void finish('tamper', verdict.signal, verdict.coveredMs)
      }, SAMPLE_MS)
    })()
    return () => {
      cancelled = true
      stopMedia()
      if (!finished.current) {
        finished.current = true
        void request(`/device/calls/${call.call_id}/end`, { method: 'POST' }).catch(() => {})
      }
    }
  }, [])

  const left = remainingSeconds(call.started_at, call.max_seconds, now)
  useEffect(() => {
    if (left === 0) void finish('end') // the allowance ran out
  }, [left, finish])

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6">
      <h1 className="text-h1 font-bold">{t('video.inCall')}</h1>
      <Card data-testid="in-video-call">
        <p data-testid="video-call-notice" className="text-h3 font-bold">
          {call.privileged ? t('video.privileged') : t('video.monitored')}
        </p>
        <p data-testid="video-timer" className="mt-3 text-display tabular-nums">
          {t('calls.timeLeft', { time: clock(left) })}
        </p>
      </Card>
      <div className="relative">
        <video
          ref={remoteRef}
          data-testid="video-remote"
          autoPlay
          playsInline
          muted
          className="w-full rounded-xl bg-black"
        />
        <video
          ref={localRef}
          data-testid="video-local"
          autoPlay
          playsInline
          muted
          className="absolute bottom-3 right-3 w-1/4 rounded-lg border-2 border-surface bg-black"
        />
      </div>
      <p>{t('video.keepCameraClear')}</p>
      <button
        onClick={() => void finish('end')}
        className="min-h-touch w-full rounded-ctl bg-danger px-6 py-4 text-label font-bold text-primary-ink"
      >
        {t('calls.end')}
      </button>
    </div>
  )
}

const pad = (n: number) => String(n).padStart(2, '0')
const TIMES = Array.from({ length: 49 }, (_, i) => {
  const mins = 8 * 60 + i * 15
  return `${pad(Math.floor(mins / 60))}:${pad(mins % 60)}`
})

function Schedule({
  contacts,
  bookings,
  nameOf,
  onChanged,
  onStart,
  onError,
}: {
  contacts: Contact[]
  bookings: Booking[]
  nameOf: (id: number) => string
  onChanged: () => void
  onStart: (id: number) => void
  onError: (e: unknown) => void
}) {
  const { t, i18n } = useTranslation()
  const { request, now } = useResident()
  const [who, setWho] = useState('')
  const [day, setDay] = useState(1)
  const [time, setTime] = useState('10:00')
  const [minutes, setMinutes] = useState(15)

  const days = Array.from({ length: 7 }, (_, i) => new Date(now + (i + 1) * 86_400_000))
  const chosen = days[day - 1]
  const startsAt = new Date(
    `${chosen.getFullYear()}-${pad(chosen.getMonth() + 1)}-${pad(chosen.getDate())}T${time}:00`,
  )

  async function book() {
    try {
      await request('/device/video-bookings', {
        method: 'POST',
        body: JSON.stringify({
          contact_id: Number(who || contacts[0]?.id),
          starts_at: startsAt.toISOString(),
          minutes,
        }),
      })
      onChanged()
    } catch (e) {
      onError(e)
    }
  }

  async function cancel(id: number) {
    try {
      await request(`/device/video-bookings/${id}/cancel`, { method: 'POST' })
      onChanged()
    } catch (e) {
      onError(e)
    }
  }

  const field = 'min-h-touch w-full rounded-ctl border-2 border-ink bg-surface px-3 text-body'
  return (
    <div className="mx-auto w-full max-w-5xl space-y-6">
      <Card data-testid="booking-form">
        <h2 className="mb-3 text-h2 font-bold">{t('video.schedule')}</h2>
        <label className="block">
          {t('video.with')}
          <select className={field} value={who} onChange={(e) => setWho(e.target.value)}>
            {contacts.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label className="mt-3 block">
          {t('video.day')}
          <select className={field} value={day} onChange={(e) => setDay(Number(e.target.value))}>
            {days.map((d, i) => (
              <option key={i} value={i + 1}>
                {d.toLocaleDateString(i18n.language, {
                  weekday: 'long',
                  month: 'short',
                  day: 'numeric',
                })}
              </option>
            ))}
          </select>
        </label>
        <label className="mt-3 block">
          {t('video.time')}
          <select className={field} value={time} onChange={(e) => setTime(e.target.value)}>
            {TIMES.map((x) => (
              <option key={x}>{x}</option>
            ))}
          </select>
        </label>
        <label className="mt-3 block">
          {t('video.length')}
          <select
            className={field}
            value={minutes}
            onChange={(e) => setMinutes(Number(e.target.value))}
          >
            <option value={15}>{t('video.minutes', { n: 15 })}</option>
            <option value={30}>{t('video.minutes', { n: 30 })}</option>
          </select>
        </label>
        <button
          disabled={contacts.length === 0}
          onClick={() => void book()}
          className="mt-4 min-h-touch rounded-ctl bg-primary px-6 py-3 text-label font-bold text-primary-ink hover:brightness-110 disabled:opacity-40"
        >
          {t('video.book')}
        </button>
      </Card>
      <h2 className="text-h2 font-bold">{t('video.upcoming')}</h2>
      {bookings.length === 0 && (
        <div data-testid="no-bookings">
          <EmptyState title={t('video.noneBooked')} />
        </div>
      )}
      <ul className="space-y-3">
        {bookings.map((b) => (
          <li key={b.id}>
            <Card data-testid={`booking-${b.id}`}>
              <p className="text-label font-bold">{nameOf(b.contact_id)}</p>
              <p>
                {new Date(b.starts_at).toLocaleString(i18n.language, {
                  dateStyle: 'medium',
                  timeStyle: 'short',
                })}{' '}
                · {t('video.minutes', { n: b.minutes })}
              </p>
              <div className="mt-2 flex gap-3">
                <button
                  onClick={() => onStart(b.id)}
                  className="min-h-touch rounded-ctl bg-primary px-6 py-3 text-label font-bold text-primary-ink hover:brightness-110"
                >
                  {t('video.start')}
                </button>
                <button
                  onClick={() => void cancel(b.id)}
                  className="min-h-touch rounded-ctl border-2 border-ink bg-surface px-6 py-3 text-label font-bold text-ink hover:bg-surface-2"
                >
                  {t('video.cancelBooking')}
                </button>
              </div>
            </Card>
          </li>
        ))}
      </ul>
    </div>
  )
}
