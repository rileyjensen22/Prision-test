import { useState } from 'react'
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
