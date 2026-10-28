import { Briefcase, PhoneCall, PhoneOff, UserRound, Users, type LucideIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button, LinkButton } from '../../ui/Button'
import { EmptyState } from '../../ui/States'
import { Notice } from '../../ui/Notice'
import { NetworkError } from '../api'
import { Card, ScreenFrame } from '../components'
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

const TYPE_ICON: Record<Contact['type'], LucideIcon> = {
  family: Users,
  friend: UserRound,
  attorney: Briefcase,
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
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 pt-6">
        <h1 className="text-h1 font-bold">{t('calls.inCall')}</h1>
        <Card data-testid="in-call" className="space-y-4 text-center">
          <PhoneCall
            aria-hidden="true"
            className="mx-auto size-14 text-primary"
            strokeWidth={1.5}
          />
          <p data-testid="call-notice" className="text-h3 font-bold">
            {active.privileged ? t('calls.privileged') : t('calls.monitored')}
          </p>
          <p data-testid="call-timer" className="text-display font-bold tabular-nums">
            {t('calls.timeLeft', { time: clock(left) })}
          </p>
        </Card>
        <Button variant="danger" icon={PhoneOff} onClick={() => void end(active)}>
          {t('calls.end')}
        </Button>
      </div>
    )

  return (
    <ScreenFrame title={t('calls.title')}>
      {allowance && (
        <p data-testid="calls-left" className="text-label font-bold">
          {t('calls.left', { n: Math.max(0, allowance.limit - allowance.used) })}
        </p>
      )}
      {summary && (
        <Notice tone="ok" role="status" data-testid="call-summary">
          {summary}
        </Notice>
      )}
      {error && (
        <Notice tone="danger" role="alert" data-testid="call-error">
          {error}
        </Notice>
      )}
      <h2 className="text-h2 font-bold">{t('calls.contacts')}</h2>
      {contacts?.length === 0 && <EmptyState title={t('calls.none')} />}
      <ul className="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(22rem,1fr))]">
        {(contacts ?? []).map((c) => {
          const Icon = TYPE_ICON[c.type]
          return (
            <li key={c.id}>
              <Card data-testid={`contact-${c.type}`} className="flex h-full flex-col gap-4">
                <div className="flex items-center gap-4">
                  <Icon
                    aria-hidden="true"
                    className="size-10 shrink-0 text-primary"
                    strokeWidth={1.75}
                  />
                  <div>
                    <p className="text-label font-bold">{c.name}</p>
                    <p className="text-ink-soft">{t(`calls.type.${c.type}`)}</p>
                  </div>
                </div>
                <Button
                  variant="primary"
                  icon={PhoneCall}
                  disabled={!c.available}
                  onClick={() => void start(c)}
                  className="mt-auto"
                >
                  {c.available ? t('calls.call') : t('calls.unavailable')}
                </Button>
              </Card>
            </li>
          )
        })}
      </ul>
      <LinkButton to="/resident/feature/contact_requests" icon={Users} className="self-start">
        {t('contacts.link')}
      </LinkButton>
    </ScreenFrame>
  )
}
