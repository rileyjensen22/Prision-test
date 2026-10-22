import { useState } from 'react'

import { errorText, fmt, post } from '../api'
import { useAuth } from '../auth'
import { Badge, Btn, ErrorLine, Notice, Page, Panel, Table, Td, Th, useLoad } from '../ui'

interface Partner {
  listing_id: number
  code: string
  title: string
  partner: string | null
  pay_per_task_cents: number
  participants: number
  tasks_accepted: number
  tasks_rejected: number
  payouts_owed_cents: number
  facility_share_cents: number
  deductions_cents: number
}
interface Run {
  id: number
  at: string
  ok: boolean
  checked: { trust_entries: number; earnings_entries: number; checks: number }
  problems: { check: string; resident_id: number; ref: number }[]
}

const usd = (cents: number) => `$${(cents / 100).toFixed(2)}`

export default function Finance() {
  const { user } = useAuth()
  const partners = useLoad<Partner[]>('/staff/jobs/partners')
  const runs = useLoad<Run[]>('/staff/finance/reconciliation')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  async function runNow() {
    try {
      const r = await post<{ ok: boolean; problems: unknown[] }>('/staff/finance/reconcile')
      setMsg(
        r.ok
          ? { kind: 'ok', text: 'Reconciled: every balance matches its ledger.' }
          : { kind: 'err', text: `Mismatch found: ${r.problems.length} problem(s). See below.` },
      )
      await runs.reload()
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  const latest = runs.data?.[0]
  return (
    <Page title="Finance">
      <ErrorLine error={partners.error ?? runs.error} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      <Panel title="Nightly reconciliation">
        <p className="mb-3 text-sm text-gray-600">
          Each night the system checks that every trust-account balance equals its append-only
          ledger, and that work earnings, payouts and trust deposits match. Any mismatch is an alert
          here and in the audit log. It never changes a balance; people investigate and add a
          correcting entry.
        </p>
        <div className="mb-3 flex items-center gap-3">
          {latest ? (
            <Badge data-testid="ledger-status" tone={latest.ok ? 'green' : 'red'}>
              {latest.ok ? 'Last run: all balances match' : 'Last run: MISMATCH'}
            </Badge>
          ) : (
            <span data-testid="ledger-status">No run yet.</span>
          )}
          {user?.role === 'admin' && <Btn onClick={() => void runNow()}>Run now</Btn>}
        </div>
        <Table data-testid="reconciliation-runs">
          <thead>
            <tr>
              <Th>When</Th>
              <Th>Result</Th>
              <Th>Entries checked</Th>
              <Th>Problems</Th>
            </tr>
          </thead>
          <tbody>
            {(runs.data ?? []).map((r) => (
              <tr key={r.id}>
                <Td>{fmt(r.at)}</Td>
                <Td>
                  <Badge tone={r.ok ? 'green' : 'red'}>{r.ok ? 'ok' : 'mismatch'}</Badge>
                </Td>
                <Td>
                  {r.checked.trust_entries} trust, {r.checked.earnings_entries} earnings
                </Td>
                <Td>
                  {r.problems.length === 0
                    ? '—'
                    : r.problems.map((p, i) => (
                        <div key={i}>
                          {p.check} (resident #{p.resident_id}, entry {p.ref})
                        </div>
                      ))}
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Panel>
      <Panel title="Work partner dashboard (demo partner)">
        <p className="mb-3 text-sm text-gray-600">
          Totals only. Individual participation is never shown, so work never becomes part of a
          behaviour record.
        </p>
        <Table data-testid="partner-dashboard">
          <thead>
            <tr>
              <Th>Job</Th>
              <Th>Partner</Th>
              <Th>Pay per task</Th>
              <Th>Participants</Th>
              <Th>Accepted</Th>
              <Th>Not accepted</Th>
              <Th>Partner owes</Th>
              <Th>Facility share</Th>
              <Th>Deductions</Th>
            </tr>
          </thead>
          <tbody>
            {(partners.data ?? []).map((p) => (
              <tr key={p.listing_id} data-testid={`partner-${p.code}`}>
                <Td>{p.title}</Td>
                <Td>{p.partner ?? '—'}</Td>
                <Td>{usd(p.pay_per_task_cents)}</Td>
                <Td>{p.participants}</Td>
                <Td>{p.tasks_accepted}</Td>
                <Td>{p.tasks_rejected}</Td>
                <Td>{usd(p.payouts_owed_cents)}</Td>
                <Td>{usd(p.facility_share_cents)}</Td>
                <Td>{usd(p.deductions_cents)}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Panel>
    </Page>
  )
}
