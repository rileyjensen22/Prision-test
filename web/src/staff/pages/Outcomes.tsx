import { useState } from 'react'
import { useTranslation } from 'react-i18next'

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
  const { t: tr } = useTranslation()

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
    <Page title={tr('staff.pages.Outcomes.outcomes')}>
      <ErrorLine error={error} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      <p className="text-sm text-ink-soft" data-testid="outcomes-note">
        {data?.note} Groups smaller than {data?.minimum_group_size ?? 5} are not shown. There are no
        individual scores.
      </p>
      <Panel title={tr('staff.pages.Outcomes.cohortsByQuarterAdmitted')}>
        <Table data-testid="cohort-table">
          <thead>
            <tr>
              <Th>{tr('staff.pages.Outcomes.cohort')}</Th>
              <Th>{tr('staff.pages.Outcomes.residents')}</Th>
              <Th>{tr('staff.pages.Outcomes.movedUpATier')}</Th>
              <Th>{tr('staff.pages.Outcomes.meanTierChange')}</Th>
              <Th>{tr('staff.pages.Outcomes.finishedACourse')}</Th>
              <Th>{tr('staff.pages.Outcomes.contactsWeek')}</Th>
              <Th>{tr('staff.pages.Outcomes.sanctions100Weeks')}</Th>
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
                  <Th>{tr('staff.pages.Outcomes.months')}</Th>
                  <Th>{tr('staff.pages.Outcomes.noReturn')}</Th>
                  <Th>{tr('staff.pages.Outcomes.returned')}</Th>
                  <Th>{tr('staff.pages.Outcomes.unknown')}</Th>
                  <Th>{tr('staff.pages.Outcomes.notEntered')}</Th>
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
        <Panel title={tr('staff.pages.Outcomes.enterAnOutcomeFrom')}>
          <div className="flex flex-wrap gap-2">
            <input
              aria-label={tr('staff.pages.Outcomes.residentCode')}
              placeholder={tr('staff.pages.Outcomes.residentCode')}
              className="rounded-ctl border px-2 py-1"
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
            <select
              aria-label={tr('staff.pages.Outcomes.monthsAfterRelease')}
              className="rounded-ctl border px-2 py-1"
              value={window}
              onChange={(e) => setWindow(Number(e.target.value))}
            >
              <option value={6}>{tr('staff.pages.Outcomes.6Months')}</option>
              <option value={12}>{tr('staff.pages.Outcomes.12Months')}</option>
              <option value={24}>{tr('staff.pages.Outcomes.24Months')}</option>
            </select>
            <select
              aria-label={tr('staff.pages.Outcomes.outcome')}
              className="rounded-ctl border px-2 py-1"
              value={outcome}
              onChange={(e) => setOutcome(e.target.value)}
            >
              <option value="no_return">{tr('staff.pages.Outcomes.noReturn')}</option>
              <option value="returned">{tr('staff.pages.Outcomes.returned')}</option>
              <option value="unknown">{tr('staff.pages.Outcomes.unknown')}</option>
            </select>
            <input
              aria-label={tr('staff.pages.Outcomes.sourceRecord')}
              placeholder={tr('staff.pages.Outcomes.sourceRecord')}
              className="rounded-ctl border px-2 py-1"
              value={source}
              onChange={(e) => setSource(e.target.value)}
            />
            <Btn disabled={!code || !source} onClick={() => void enter()}>
              {tr('staff.pages.Outcomes.record')}
            </Btn>
          </div>
        </Panel>
      )}
      {canExport && (
        <Panel title={tr('staff.pages.Outcomes.researcherExport')}>
          <p className="mb-2 text-sm">{tr('staff.pages.Outcomes.pseudonymizedRowsWithBands')}</p>
          <div className="flex flex-wrap gap-2">
            <input
              aria-label={tr('staff.pages.Outcomes.reasonForExport')}
              placeholder={tr('staff.pages.Outcomes.reason')}
              className="rounded-ctl border px-2 py-1"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
            <Btn disabled={reason.trim().length < 3} onClick={() => void download()}>
              {tr('staff.pages.Outcomes.export')}
            </Btn>
          </div>
        </Panel>
      )}
    </Page>
  )
}
