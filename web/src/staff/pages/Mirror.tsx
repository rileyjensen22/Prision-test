import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SimulatedResident } from '../../resident/SimulatedResident'
import type { ResidentView } from '../../resident/types'
import { ApiError, api, errorText, fmt, post } from '../api'
import { useAuth } from '../auth'
import { Btn, ErrorLine, Notice, Page, Panel, Table, Td, Th, useLoad } from '../ui'

interface RosterRow {
  resident_id: number
  code: string
  device: string | null
}
interface Frame {
  session_id: number
  resident_code: string
  started_at: string
  expires_at: string
  redacted: 'PRIVILEGED_CALL' | 'PRIVATE_SCREEN' | null
  screen: { path: string | null; age_seconds: number | null } | null
  view: ResidentView | null
}
interface Hist {
  id: number
  staff: string
  resident_code: string
  reason: string
  started_at: string
  ended_at: string | null
  end_reason: string | null
  seconds: number
  frames: number
}

const POLL_MS = 2000

export default function Mirror() {
  const { t } = useTranslation()

  const { user } = useAuth()
  const canStart = user?.role === 'supervisor' || user?.role === 'admin'
  const roster = useLoad<RosterRow[]>('/staff/residents/lookup?limit=500')
  const history = useLoad<Hist[]>('/staff/mirror/sessions')
  const [residentId, setResidentId] = useState('')
  const [reason, setReason] = useState('')
  const [sessionId, setSessionId] = useState<number | null>(null)
  const [frame, setFrame] = useState<Frame | null>(null)
  const [message, setMessage] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  async function start() {
    setMessage(null)
    try {
      const r = await post<{ session_id: number }>('/staff/mirror/sessions', {
        resident_id: Number(residentId),
        reason,
      })
      setSessionId(r.session_id)
    } catch (e) {
      setMessage({ kind: 'err', text: errorText(e) })
    }
  }

  const stop = useCallback(
    async (why?: string) => {
      if (sessionId !== null && !why)
        await post(`/staff/mirror/sessions/${sessionId}/end`).catch(() => {})
      setSessionId(null)
      setFrame(null)
      if (why) setMessage({ kind: 'err', text: why })
      await history.reload()
    },
    [sessionId, history],
  )

  useEffect(() => {
    if (sessionId === null) return
    let cancelled = false
    const tick = async () => {
      try {
        const f = await api<Frame>(`/staff/mirror/sessions/${sessionId}/frame`)
        if (!cancelled) setFrame(f)
      } catch (e) {
        if (cancelled) return
        if (e instanceof ApiError && e.status === 410)
          void stop('The mirror session ended (time limit or inactivity).')
        else setMessage({ kind: 'err', text: errorText(e) })
      }
    }
    void tick()
    const id = setInterval(() => void tick(), POLL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [sessionId, stop])

  return (
    <Page title={t('staff.pages.Mirror.liveMirror')}>
      <p className="text-sm text-ink-soft">{t('staff.pages.Mirror.aReadOnlyView')}</p>
      {message && <Notice kind={message.kind}>{message.text}</Notice>}

      {sessionId === null && canStart && (
        <Panel title={t('staff.pages.Mirror.startASession')}>
          <div className="grid gap-3 md:grid-cols-[1fr_2fr_auto] md:items-end">
            <label className="text-sm">
              {t('staff.pages.Mirror.resident')}
              <select
                aria-label={t('staff.pages.Mirror.resident')}
                value={residentId}
                onChange={(e) => setResidentId(e.target.value)}
                className="mt-1 block w-full rounded-ctl border px-2 py-2"
              >
                <option value="">{t('staff.pages.Mirror.choose')}</option>
                {(roster.data ?? [])
                  .filter((r) => r.device)
                  .map((r) => (
                    <option key={r.resident_id} value={r.resident_id}>
                      {r.code}
                    </option>
                  ))}
              </select>
            </label>
            <label className="text-sm">
              {t('staff.pages.Mirror.whyAreYouWatching')}
              <input
                aria-label={t('staff.pages.Mirror.reasonForMirroring')}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="mt-1 block w-full rounded-ctl border px-2 py-2"
              />
            </label>
            <Btn onClick={() => void start()} disabled={!residentId || reason.trim().length < 5}>
              {t('staff.pages.Mirror.startMirror')}
            </Btn>
          </div>
        </Panel>
      )}

      {sessionId !== null && (
        <div className="space-y-3" data-testid="mirror-live">
          <div
            className="flex flex-wrap items-center gap-3 rounded-ctl bg-notice-soft px-3 py-2 text-ink"
            role="status"
          >
            <strong>{t('staff.pages.Mirror.liveMirrorReadOnly')}</strong>
            <span data-testid="mirror-target">{frame?.resident_code ?? '…'}</span>
            {frame && <span>until {fmt(frame.expires_at)}</span>}
            <span className="ml-auto">
              <Btn kind="danger" onClick={() => void stop()}>
                {t('staff.pages.Mirror.endMirror')}
              </Btn>
            </span>
          </div>
          {frame?.redacted && (
            <Panel data-testid="mirror-redacted">
              <p className="font-medium">{t('staff.pages.Mirror.privateScreen')}</p>
              <p className="text-sm text-ink-soft">
                {frame.redacted === 'PRIVILEGED_CALL'
                  ? 'A private attorney call is in progress.'
                  : 'The resident is on a private service (legal, grievance or health).'}{' '}
                Its contents are never shown.
              </p>
            </Panel>
          )}
          {frame?.view && (
            <div className="max-w-xl">
              <p className="mb-1 text-sm text-ink-soft" data-testid="mirror-screen">
                Screen: {frame.screen?.path ?? 'unknown'}
                {frame.screen?.age_seconds != null && ` (updated ${frame.screen.age_seconds}s ago)`}
              </p>
              <SimulatedResident
                view={{ ...frame.view, simulation: false }}
                mode="mirror"
                path={frame.screen?.path ?? '/resident'}
              />
            </div>
          )}
        </div>
      )}

      <Panel title={t('staff.pages.Mirror.sessionHistory')}>
        <ErrorLine error={history.error} />
        <Table data-testid="mirror-history">
          <thead>
            <tr>
              <Th>{t('staff.pages.Mirror.started')}</Th>
              <Th>{t('staff.pages.Mirror.staff')}</Th>
              <Th>{t('staff.pages.Mirror.resident')}</Th>
              <Th>{t('staff.pages.Mirror.reason')}</Th>
              <Th>{t('staff.pages.Mirror.length')}</Th>
              <Th>{t('staff.pages.Mirror.ended')}</Th>
            </tr>
          </thead>
          <tbody>
            {(history.data ?? []).map((h) => (
              <tr key={h.id} data-testid={`mirror-${h.id}`}>
                <Td>{fmt(h.started_at)}</Td>
                <Td>{h.staff}</Td>
                <Td>{h.resident_code}</Td>
                <Td>{h.reason}</Td>
                <Td>
                  {Math.floor(h.seconds / 60)}m {h.seconds % 60}s
                </Td>
                <Td>{h.ended_at ? h.end_reason : 'in progress'}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Panel>
    </Page>
  )
}
