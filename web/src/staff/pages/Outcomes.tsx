import { useState } from 'react'

import { api, errorText, post } from '../api'
import { useAuth } from '../auth'
import { Btn, ErrorLine, Notice, Page, Panel, Table, Td, Th, useLoad } from '../ui'

type Cell = number | string
interface Cohort {
  cohort: string
  residents: Cell
  share_promoted?: number
  mean_tier_change?: number
  share_completed_a_course?: number
  mean_courses_completed?: number
  contacts_per_week?: number | null
  sanctions_per_100_weeks?: number | null
  outcomes?: Record<string, Record<string, Cell>>
}
interface Data {
  minimum_group_size: number
  cohorts: Cohort[]
  note: string
}

const pct = (n?: number) => (n === undefined ? '—' : `${Math.round(n * 100)}%`)
const num = (n?: number | null) => (n === undefined || n === null ? '—' : String(n))

export default function Outcomes() {
  const { user } = useAuth()
  const { data, error, reload } = useLoad<Data>('/staff/outcomes')
  const canEnter = user?.role === 'admin'
  const canExport = !!user && ['admin', 'auditor'].includes(user.role)
  const [code, setCode] = useState('')
  const [window, setWindow] = useState(6)
  const [outcome, setOutcome] = useState('no_return')
  const [source, setSource] = useState('')
  const [reason, setReason] = useState('')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  async function enter() {
    try {
      await post('/staff/outcomes', { resident_code: code, window_months: window, outcome, source })
      setMsg({
        kind: 'ok',
        text: 'Outcome recorded. A later entry for the same window corrects this one.',
      })
      setCode('')
      await reload()
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  async function download() {
    try {
      const out = await api<{ rows: unknown[] }>(
        `/staff/outcomes/export?reason=${encodeURIComponent(reason)}`,
      )
      const blob = new Blob([JSON.stringify(out, null, 2)], { type: 'application/json' })
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = 'researcher-export.json'
      a.click()
      setMsg({
        kind: 'ok',
        text: `Exported ${out.rows.length} pseudonymized rows. This was logged.`,
      })
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  return (
    <Page title="Outcomes">
      <ErrorLine error={error} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      <p className="text-sm text-ink-soft" data-testid="outcomes-note">
        {data?.note} Groups smaller than {data?.minimum_group_size ?? 5} are not shown. There are no
        individual scores.
      </p>
      <Panel title="Cohorts (by quarter admitted)">
        <Table data-testid="cohort-table">
          <thead>
            <tr>
              <Th>Cohort</Th>
              <Th>Residents</Th>
              <Th>Moved up a tier</Th>
              <Th>Mean tier change</Th>
              <Th>Finished a course</Th>
              <Th>Contacts / week</Th>
              <Th>Sanctions / 100 weeks</Th>
            </tr>
          </thead>
          <tbody>
            {(data?.cohorts ?? []).map((c) => (
              <tr key={c.cohort} data-testid={`cohort-${c.cohort}`}>
                <Td>{c.cohort}</Td>
                <Td>{c.residents}</Td>
                <Td>{pct(c.share_promoted)}</Td>
                <Td>{num(c.mean_tier_change)}</Td>
                <Td>{pct(c.share_completed_a_course)}</Td>
                <Td>{num(c.contacts_per_week)}</Td>
                <Td>{num(c.sanctions_per_100_weeks)}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Panel>
      {(data?.cohorts ?? [])
        .filter((c) => c.outcomes)
        .map((c) => (
          <Panel key={c.cohort} title={`Outcomes entered later: ${c.cohort}`}>
            <Table>
              <thead>
                <tr>
                  <Th>Months</Th>
                  <Th>No return</Th>
                  <Th>Returned</Th>
                  <Th>Unknown</Th>
                  <Th>Not entered</Th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(c.outcomes ?? {}).map(([w, t]) => (
                  <tr key={w}>
                    <Td>{w}</Td>
                    <Td>{t.no_return}</Td>
                    <Td>{t.returned}</Td>
                    <Td>{t.unknown}</Td>
                    <Td>{t.not_entered}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Panel>
        ))}
      {canEnter && (
        <Panel title="Enter an outcome from customer records">
          <div className="flex flex-wrap gap-2">
            <input
              aria-label="Resident code"
              placeholder="Resident code"
              className="rounded-ctl border px-2 py-1"
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
            <select
              aria-label="Months after release"
              className="rounded-ctl border px-2 py-1"
              value={window}
              onChange={(e) => setWindow(Number(e.target.value))}
            >
              <option value={6}>6 months</option>
              <option value={12}>12 months</option>
              <option value={24}>24 months</option>
            </select>
            <select
              aria-label="Outcome"
              className="rounded-ctl border px-2 py-1"
              value={outcome}
              onChange={(e) => setOutcome(e.target.value)}
            >
              <option value="no_return">No return</option>
              <option value="returned">Returned</option>
              <option value="unknown">Unknown</option>
            </select>
            <input
              aria-label="Source record"
              placeholder="Source record"
              className="rounded-ctl border px-2 py-1"
              value={source}
              onChange={(e) => setSource(e.target.value)}
            />
            <Btn disabled={!code || !source} onClick={() => void enter()}>
              Record
            </Btn>
          </div>
        </Panel>
      )}
      {canExport && (
        <Panel title="Researcher export">
          <p className="mb-2 text-sm">
            Pseudonymized rows with bands instead of exact counts and no dates. Off unless an
            operator turns it on; every export needs a reason and is logged.
          </p>
          <div className="flex flex-wrap gap-2">
            <input
              aria-label="Reason for export"
              placeholder="Reason"
              className="rounded-ctl border px-2 py-1"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
            <Btn disabled={reason.trim().length < 3} onClick={() => void download()}>
              Export
            </Btn>
          </div>
        </Panel>
      )}
    </Page>
  )
}
