import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'

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

interface DepositRow {
  resident_code: string
  amount_cents: number
  source: string
  note: string | null
}

function DepositImport() {
  const [rows, setRows] = useState<DepositRow[] | null>(null)
  const [parseErr, setParseErr] = useState<string | null>(null)
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  function parseCsv(text: string): DepositRow[] {
    const lines = text.trim().split('\n').filter(Boolean)
    if (!lines.length) throw new Error('File is empty')
    // skip header if present
    const start = lines[0].toLowerCase().includes('resident') ? 1 : 0
    return lines.slice(start).map((line, i) => {
      const cols = line.split(',').map((c) => c.trim().replace(/^"|"$/g, ''))
      if (cols.length < 3) throw new Error(`Row ${i + start + 1}: need at least 3 columns (resident_code, amount, source)`)
      const amount_cents = Math.round(parseFloat(cols[1]) * 100)
      if (isNaN(amount_cents) || amount_cents <= 0) throw new Error(`Row ${i + start + 1}: invalid amount "${cols[1]}"`)
      return { resident_code: cols[0], amount_cents, source: cols[2], note: cols[3] ?? null }
    })
  }

  function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    setParseErr(null)
    setRows(null)
    setMsg(null)
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      try {
        setRows(parseCsv(ev.target?.result as string))
      } catch (err) {
        setParseErr(err instanceof Error ? err.message : 'Parse error')
      }
    }
    reader.readAsText(file)
  }

  async function confirm() {
    if (!rows) return
    setBusy(true)
    setMsg(null)
    try {
      const r = await post<{ imported: number }>('/staff/finance/deposit-import', { rows })
      setMsg({ kind: 'ok', text: `${r.imported} deposit(s) imported. All entries are append-only.` })
      setRows(null)
    } catch (err) {
      setMsg({ kind: 'err', text: errorText(err) })
    } finally {
      setBusy(false)
    }
  }

  const usdCents = (c: number) => `$${(c / 100).toFixed(2)}`

  return (
    <Panel title="Deposit Import (CSV)" data-testid="deposit-import-panel">
      <p className="mb-2 text-sm text-ink-soft">
        CSV columns: <code>resident_code, amount (dollars), source, note (optional)</code>. Each row creates an append-only ledger entry.
      </p>
      <input
        type="file"
        accept=".csv,text/csv"
        onChange={onFile}
        className="block text-sm"
        data-testid="deposit-import-file"
      />
      {parseErr && <Notice kind="err">{parseErr}</Notice>}
      {rows && rows.length > 0 && (
        <div className="mt-3 space-y-2">
          <p className="text-sm font-medium">{rows.length} row(s) to import — review before confirming:</p>
          <Table>
            <thead>
              <tr>
                <Th>Resident</Th>
                <Th>Amount</Th>
                <Th>Source</Th>
                <Th>Note</Th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 20).map((r, i) => (
                <tr key={i}>
                  <Td>{r.resident_code}</Td>
                  <Td>{usdCents(r.amount_cents)}</Td>
                  <Td>{r.source}</Td>
                  <Td>{r.note ?? ''}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
          {rows.length > 20 && <p className="text-sm text-ink-soft">…and {rows.length - 20} more</p>}
          <Btn onClick={() => void confirm()} disabled={busy}>
            {busy ? 'Importing…' : `Confirm and import ${rows.length} deposit(s)`}
          </Btn>
        </div>
      )}
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
    </Panel>
  )
}

export default function Finance() {
  const { t } = useTranslation()

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
    <Page title={t('staff.pages.Finance.finance')}>
      <ErrorLine error={partners.error ?? runs.error} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      <Panel title={t('staff.pages.Finance.nightlyReconciliation')}>
        <p className="mb-3 text-sm text-ink-soft">{t('staff.pages.Finance.eachNightTheSystem')}</p>
        <div className="mb-3 flex items-center gap-3">
          {latest ? (
            <Badge data-testid="ledger-status" tone={latest.ok ? 'green' : 'red'}>
              {latest.ok ? 'Last run: all balances match' : 'Last run: MISMATCH'}
            </Badge>
          ) : (
            <span data-testid="ledger-status">{t('staff.pages.Finance.noRunYet')}</span>
          )}
          {user?.role === 'admin' && (
            <Btn onClick={() => void runNow()}>{t('staff.pages.Finance.runNow')}</Btn>
          )}
        </div>
        <Table data-testid="reconciliation-runs">
          <thead>
            <tr>
              <Th>{t('staff.pages.Finance.when')}</Th>
              <Th>{t('staff.pages.Finance.result')}</Th>
              <Th>{t('staff.pages.Finance.entriesChecked')}</Th>
              <Th>{t('staff.pages.Finance.problems')}</Th>
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
                  {t('staff.msg.financeCounts', {
                    trust: r.checked.trust_entries,
                    earnings: r.checked.earnings_entries,
                  })}
                </Td>
                <Td>
                  {r.problems.length === 0
                    ? '—'
                    : r.problems.map((p, i) => (
                        <div key={i}>
                          {t('staff.msg.financeProblem', {
                            check: p.check,
                            resident: p.resident_id,
                            ref: p.ref,
                          })}
                        </div>
                      ))}
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Panel>
      {user && ['supervisor', 'admin'].includes(user.role) && <DepositImport />}
      <Panel title={t('staff.pages.Finance.workPartnerDashboardDemo')}>
        <p className="mb-3 text-sm text-ink-soft">
          {t('staff.pages.Finance.totalsOnlyIndividualParticipation')}
        </p>
        <Table data-testid="partner-dashboard">
          <thead>
            <tr>
              <Th>{t('staff.pages.Finance.job')}</Th>
              <Th>{t('staff.pages.Finance.partner')}</Th>
              <Th>{t('staff.pages.Finance.payPerTask')}</Th>
              <Th>{t('staff.pages.Finance.participants')}</Th>
              <Th>{t('staff.pages.Finance.accepted')}</Th>
              <Th>{t('staff.pages.Finance.notAccepted')}</Th>
              <Th>{t('staff.pages.Finance.partnerOwes')}</Th>
              <Th>{t('staff.pages.Finance.facilityShare')}</Th>
              <Th>{t('staff.pages.Finance.deductions')}</Th>
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
