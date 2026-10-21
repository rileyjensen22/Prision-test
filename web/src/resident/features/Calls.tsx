import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { NetworkError } from '../api'
import { BackLink, Card } from '../components'
import { useResident } from '../ResidentContext'
import { clock, errorCode, remainingSeconds } from './helpers'

interface Contact {
  id: number
  name: string
  type: 'family' | 'friend' | 'attorney'
  available: boolean
}
interface CallInfo {
  call_id: number
  privileged: boolean
  monitored: boolean
  max_seconds: number
  started_at: string
  status: string
  duration_seconds: number | null
}

export function Calls() {
  const { t } = useTranslation()
  const { request, refresh, view, now } = useResident()
  const [contacts, setContacts] = useState<Contact[] | null>(null)
  const [active, setActive] = useState<CallInfo | null>(null)
  const [summary, setSummary] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    request<Contact[]>('/device/contacts')
      .then(setContacts)
      .catch(() => setError(t('calls.needsConnection')))
  }, [request, t])

  async function start(c: Contact) {
    setError(null)
    setSummary(null)
    try {
      setActive(
        await request<CallInfo>('/device/calls', {
          method: 'POST',
          body: JSON.stringify({ contact_id: c.id }),
        }),
      )
    } catch (e) {
      const code = errorCode(e)
      setError(
        e instanceof NetworkError
          ? t('calls.needsConnection')
          : t(`calls.err.${code}`, { defaultValue: code }),
      )
    }
  }

  async function end(c: CallInfo) {
    try {
      const done = await request<CallInfo>(`/device/calls/${c.call_id}/end`, { method: 'POST' })
      setSummary(t('calls.ended', { time: clock(done.duration_seconds ?? 0) }))
    } catch {
      setSummary(null)
    }
    setActive(null)
    void refresh()
  }

  const left = active ? remainingSeconds(active.started_at, active.max_seconds, now) : 0
  useEffect(() => {
    if (active && left === 0) void end(active) // the allowance ran out
  }, [active, left])

  const allowance = view?.allowances.find((a) => a.feature === 'calls')

  if (active)
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">{t('calls.inCall')}</h1>
        <Card data-testid="in-call">
          <p data-testid="call-notice" className="text-2xl font-semibold">
            {active.privileged ? t('calls.privileged') : t('calls.monitored')}
          </p>
          <p data-testid="call-timer" className="mt-3 text-4xl">
            {t('calls.timeLeft', { time: clock(left) })}
          </p>
        </Card>
        <button
          onClick={() => void end(active)}
          className="min-h-16 w-full rounded-xl bg-red-700 px-6 py-4 text-xl font-bold"
        >
          {t('calls.end')}
        </button>
      </div>
    )

  return (
    <div className="space-y-6">
      <BackLink />
      <h1 className="text-3xl font-bold">{t('calls.title')}</h1>
      {allowance && (
        <p data-testid="calls-left">
          {t('calls.left', { n: Math.max(0, allowance.limit - allowance.used) })}
        </p>
      )}
      {summary && (
        <p role="status" data-testid="call-summary">
          {summary}
        </p>
      )}
      {error && (
        <p role="alert" data-testid="call-error">
          {error}
        </p>
      )}
      <h2 className="text-2xl font-bold">{t('calls.contacts')}</h2>
      {contacts?.length === 0 && <p>{t('calls.none')}</p>}
      <ul className="space-y-3">
        {(contacts ?? []).map((c) => (
          <li key={c.id}>
            <Card data-testid={`contact-${c.type}`}>
              <p className="text-xl font-semibold">{c.name}</p>
              <p>{t(`calls.type.${c.type}`)}</p>
              <button
                disabled={!c.available}
                onClick={() => void start(c)}
                className="mt-2 min-h-14 rounded-lg bg-green-700 px-6 py-3 font-semibold disabled:opacity-40"
              >
                {c.available ? t('calls.call') : t('calls.unavailable')}
              </button>
            </Card>
          </li>
        ))}
      </ul>
    </div>
  )
}
