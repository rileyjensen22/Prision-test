import { Link } from 'react-router-dom'

import { fmt } from '../api'
import { ErrorLine, Page, Panel, Table, Td, Th, useLoad } from '../ui'

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
      className={`rounded-card border bg-surface p-4  ${warn && value > 0 ? 'border-notice' : ''}`}
    >
      <div className="text-h1 font-semibold">{value}</div>
      <div className="text-sm text-ink-soft">{label}</div>
    </Link>
  )
}

export default function Dashboard() {
  const summary = useLoad<Summary>('/staff/summary')
  const events = useLoad<Ev[]>('/staff/events?limit=25')
  const s = summary.data
  return (
    <Page title="Dashboard">
      <ErrorLine error={summary.error} />
      {s?.ledger_ok === false && (
        <p
          role="alert"
          data-testid="ledger-alert"
          className="rounded-ctl border border-danger bg-danger-soft px-3 py-2 text-ink"
        >
          The last nightly reconciliation found a mismatch between a balance and its ledger.{' '}
          <Link className="underline" to="/staff/finance">
            Open Finance
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
        </div>
      )}
      {s && s.overdue_appeals > 0 && (
        <p role="alert" className="rounded-ctl bg-danger-soft px-3 py-2 text-ink">
          {s.overdue_appeals} appeal(s) are past their review deadline.
        </p>
      )}
      <Panel title="Recent events">
        <ErrorLine error={events.error} />
        <Table data-testid="event-feed">
          <thead>
            <tr>
              <Th>When</Th>
              <Th>Who</Th>
              <Th>What</Th>
              <Th>About</Th>
              <Th>Reason</Th>
            </tr>
          </thead>
          <tbody>
            {(events.data ?? []).map((e) => (
              <tr key={e.seq}>
                <Td>{fmt(e.ts)}</Td>
                <Td>{e.actor}</Td>
                <Td>{e.action.replace(/_/g, ' ')}</Td>
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
