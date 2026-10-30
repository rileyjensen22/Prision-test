import { AlertTriangle } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { fmt } from '../api'
import { ErrorLine, Page, Panel, Table, Td, Th, useLoad } from '../ui'
import { FacilityOverview } from './FacilityOverview'

interface Summary {
  residents: number
  pending_confirmations: number
  open_appeals: number
  overdue_appeals: number
  offline_devices: number
  outlier_flags: number | null
  welfare_flags: number
  welfare_escalated: number
  below_minimum: number
  ledger_ok: boolean | null
  open_health_requests: number
  open_grievances: number
  pending_attorney_calls: number
  commissary_orders_waiting: number
  deposit_imports_pending: number
}
interface Ev {
  seq: number
  ts: string
  actor: string
  action: string
  target: string
  reason_code: string | null
}

const EVENT_LABEL: Record<string, string> = {
  clean_day: 'Clean day',
  course_completed: 'Course completed',
  commendation: 'Staff commendation',
  infraction_confirmed: 'Infraction recorded',
  sanction_applied: 'Sanction applied',
  appeal_filed: 'Appeal filed',
  appeal_resolved: 'Appeal resolved',
  tier_changed: 'Tier changed',
  assignment_changed: 'Assignment changed',
  contact_added: 'Contact added',
}

const SYSTEM_PREFIXES = ['seed_', 'system_', 'daily_', 'sync_', 'heartbeat_']

function humanAction(action: string): string {
  return EVENT_LABEL[action] ?? action.replace(/_/g, ' ')
}

export default function Dashboard() {
  const { t } = useTranslation()
  const [hideSystem, setHideSystem] = useState(true)

  const summary = useLoad<Summary>('/staff/summary')
  const events = useLoad<Ev[]>('/staff/events?limit=10')
  const s = summary.data
  const shownEvents = (events.data ?? []).filter(
    (e) => !hideSystem || !SYSTEM_PREFIXES.some((p) => e.action.startsWith(p)),
  )

  const openRequests = s
    ? (s.open_health_requests ?? 0) +
      (s.open_grievances ?? 0) +
      (s.open_appeals ?? 0) +
      (s.pending_confirmations ?? 0) +
      (s.pending_attorney_calls ?? 0)
    : 0

  return (
    <Page title={t('staff.pages.Dashboard.dashboard')}>
      <ErrorLine error={summary.error} />
      {s?.ledger_ok === false && (
        <p
          role="alert"
          data-testid="ledger-alert"
          className="rounded-ctl border border-danger bg-danger-soft px-3 py-2 text-ink"
        >
          {t('staff.msg.reconcileMismatch')}{' '}
          <Link className="underline" to="/staff/finance">
            {t('staff.pages.Dashboard.openFinance')}
          </Link>
        </p>
      )}
      {s && (s.overdue_appeals ?? 0) > 0 && (
        <p role="alert" className="rounded-ctl bg-danger-soft px-3 py-2 text-ink">
          {t('staff.msg.overdueAppeals', { count: s.overdue_appeals })}
        </p>
      )}
      {s && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Link
            to="/staff/roster"
            data-testid="stat-residents"
            className="block rounded-card border bg-surface p-4 hover:border-primary"
          >
            <div className="text-display font-bold tabular-nums">{s.residents}</div>
            <div className="text-ink-soft">Residents</div>
          </Link>

          <Link
            to="/staff/requests"
            data-testid="stat-requests"
            className={`block rounded-card border bg-surface p-4 hover:border-primary ${openRequests > 0 ? 'border-2 border-notice' : ''}`}
          >
            <div className="flex items-center justify-between">
              <span className="text-display font-bold tabular-nums">{openRequests}</span>
              {openRequests > 0 && <AlertTriangle aria-hidden="true" className="size-6 text-notice" />}
            </div>
            <div className="text-ink-soft">Open requests</div>
          </Link>

          <Link
            to="/staff/welfare"
            data-testid="stat-welfare"
            className={`block rounded-card border bg-surface p-4 hover:border-primary ${(s.welfare_flags ?? 0) > 0 ? 'border-2 border-notice' : ''}`}
          >
            <div className="flex items-center justify-between">
              <span className="text-display font-bold tabular-nums">{s.welfare_flags ?? 0}</span>
              {(s.welfare_flags ?? 0) > 0 && <AlertTriangle aria-hidden="true" className="size-6 text-notice" />}
            </div>
            <div className="text-ink-soft">Welfare flags</div>
          </Link>

          <Link
            to="/staff/roster"
            data-testid="stat-offline"
            className={`block rounded-card border bg-surface p-4 hover:border-primary ${(s.offline_devices ?? 0) > 0 ? 'border-2 border-notice' : ''}`}
          >
            <div className="flex items-center justify-between">
              <span className="text-display font-bold tabular-nums">{s.offline_devices ?? 0}</span>
              {(s.offline_devices ?? 0) > 0 && <AlertTriangle aria-hidden="true" className="size-6 text-notice" />}
            </div>
            <div className="text-ink-soft">Devices offline</div>
          </Link>
        </div>
      )}

      <FacilityOverview />

      <Panel title={t('staff.pages.Dashboard.recentEvents')}>
        <ErrorLine error={events.error} />
        <label className="flex cursor-pointer items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={hideSystem}
            onChange={(e) => setHideSystem(e.target.checked)}
            className="size-4"
          />
          Hide automated system events
        </label>
        <Table data-testid="event-feed">
          <thead>
            <tr>
              <Th>{t('staff.pages.Dashboard.when')}</Th>
              <Th>{t('staff.pages.Dashboard.who')}</Th>
              <Th>{t('staff.pages.Dashboard.what')}</Th>
              <Th>{t('staff.pages.Dashboard.about')}</Th>
              <Th>{t('staff.pages.Dashboard.reason')}</Th>
            </tr>
          </thead>
          <tbody>
            {shownEvents.map((e) => (
              <tr key={e.seq}>
                <Td>{fmt(e.ts)}</Td>
                <Td>{e.actor}</Td>
                <Td>{humanAction(e.action)}</Td>
                <Td>{e.target}</Td>
                <Td>{e.reason_code ?? ''}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Panel>
    </Page>
  )
}
