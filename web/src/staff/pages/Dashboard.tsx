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

function Stat({
  label,
  value,
  to,
  warn,
  id,
}: {
  label: string
  value: number | null
  to: string
  warn?: boolean
  id: string
}) {
  if (value === null) return null
  return (
    <Link
      to={to}
      data-testid={id}
      className={`block rounded-card border bg-surface p-4 hover:border-primary ${warn && value > 0 ? 'border-2 border-notice' : ''}`}
    >
      <div className="flex items-center justify-between">
        <span className="text-display font-bold tabular-nums">{value}</span>
        {warn && value > 0 && <AlertTriangle aria-hidden="true" className="size-6 text-notice" />}
      </div>
      <div className="text-ink-soft">{label}</div>
    </Link>
  )
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
  const events = useLoad<Ev[]>('/staff/events?limit=50')
  const s = summary.data
  const shownEvents = (events.data ?? []).filter(
    (e) => !hideSystem || !SYSTEM_PREFIXES.some((p) => e.action.startsWith(p)),
  )
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
      {s && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat id="stat-residents" label="Residents" value={s.residents} to="/staff/roster" />
          <Stat
            id="stat-pending"
            label="Awaiting confirmation"
            value={s.pending_confirmations}
            to="/staff/confirmations"
            warn
          />
          <Stat
            id="stat-appeals"
            label="Open appeals"
            value={s.open_appeals}
            to="/staff/appeals"
            warn
          />
          <Stat
            id="stat-offline"
            label="Devices offline"
            value={s.offline_devices}
            to="/staff/roster"
            warn
          />
          <Stat
            id="stat-escalated"
            label="Escalated welfare flags"
            value={s.welfare_escalated}
            to="/staff/welfare"
            warn
          />
          <Stat
            id="stat-below-minimum"
            label="Below out-of-cell minimum"
            value={s.below_minimum}
            to="/staff/out-of-cell"
            warn
          />
          <Stat
            id="stat-welfare"
            label="Welfare flags"
            value={s.welfare_flags}
            to="/staff/welfare"
            warn
          />
          <Stat
            id="stat-outliers"
            label="Staff outlier flags"
            value={s.outlier_flags}
            to="/staff/outliers"
            warn
          />
          <Stat
            id="stat-health"
            label="Open health requests"
            value={s.open_health_requests}
            to="/staff/health-requests"
            warn
          />
          <Stat
            id="stat-grievances"
            label="Open grievances"
            value={s.open_grievances}
            to="/staff/grievances"
            warn
          />
          <Stat
            id="stat-attorney"
            label="Pending attorney calls"
            value={s.pending_attorney_calls}
            to="/staff/attorney-calls"
            warn
          />
          <Stat
            id="stat-commissary"
            label="Commissary orders waiting"
            value={s.commissary_orders_waiting}
            to="/staff/commissary"
            warn
          />
        </div>
      )}
      {s && s.overdue_appeals > 0 && (
        <p role="alert" className="rounded-ctl bg-danger-soft px-3 py-2 text-ink">
          {t('staff.msg.overdueAppeals', { count: s.overdue_appeals })}
        </p>
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
