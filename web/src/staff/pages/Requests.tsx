import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import { api, fmt } from '../api'
import { ErrorLine, Page } from '../ui'

type RequestType = 'health' | 'grievance' | 'appeal' | 'confirmation' | 'attorney' | 'welfare'

interface RequestRow {
  id: number | string
  type: RequestType
  resident: string
  resident_id?: number
  summary: string
  status: string
  created_at: string
}

const TYPE_META: Record<RequestType, { label: string; bg: string; text: string; to: string }> = {
  health:       { label: 'Health',        bg: 'bg-blue-100',   text: 'text-blue-800',   to: '/staff/health-requests' },
  grievance:    { label: 'Grievance',     bg: 'bg-orange-100', text: 'text-orange-800', to: '/staff/grievances' },
  appeal:       { label: 'Appeal',        bg: 'bg-purple-100', text: 'text-purple-800', to: '/staff/appeals' },
  confirmation: { label: 'Confirmation',  bg: 'bg-red-100',    text: 'text-red-800',    to: '/staff/confirmations' },
  attorney:     { label: 'Attorney Call', bg: 'bg-green-100',  text: 'text-green-800',  to: '/staff/attorney-calls' },
  welfare:      { label: 'Welfare',       bg: 'bg-yellow-100', text: 'text-yellow-800', to: '/staff/welfare' },
}

function TypeBadge({ type }: { type: RequestType }) {
  const m = TYPE_META[type]
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${m.bg} ${m.text}`}>
      {m.label}
    </span>
  )
}

function StatusChip({ status }: { status: string }) {
  return (
    <span className="inline-flex items-center rounded px-2 py-0.5 text-xs font-medium bg-surface-2 text-ink-soft">
      {status}
    </span>
  )
}

async function safeFetch<T>(path: string): Promise<T | null> {
  try {
    return await api<T>(path)
  } catch {
    return null
  }
}

export default function Requests() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [rows, setRows] = useState<RequestRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    async function load() {
      try {
        const [health, grievances, appeals, confirmations, attorney, welfare] = await Promise.all([
          safeFetch<any[]>('/staff/health-requests'),
          safeFetch<any[]>('/staff/grievances'),
          safeFetch<any[]>('/staff/appeals'),
          safeFetch<any[]>('/staff/confirmations'),
          safeFetch<any[]>('/staff/attorney-calls'),
          safeFetch<any[]>('/staff/welfare/flags'),
        ])

        const merged: RequestRow[] = []

        for (const h of health ?? []) {
          merged.push({
            id: h.id,
            type: 'health',
            resident: h.resident_code ?? h.resident ?? String(h.resident_id ?? ''),
            resident_id: h.resident_id,
            summary: h.subject ?? h.category ?? 'Health request',
            status: h.status ?? 'open',
            created_at: h.created_at ?? h.filed_at ?? new Date().toISOString(),
          })
        }
        for (const g of grievances ?? []) {
          merged.push({
            id: g.id,
            type: 'grievance',
            resident: g.resident_code ?? g.resident ?? String(g.resident_id ?? ''),
            resident_id: g.resident_id,
            summary: g.subject ?? g.category ?? 'Grievance',
            status: g.status ?? 'open',
            created_at: g.created_at ?? g.filed_at ?? new Date().toISOString(),
          })
        }
        for (const a of appeals ?? []) {
          merged.push({
            id: a.id,
            type: 'appeal',
            resident: a.resident_code ?? a.resident ?? String(a.resident_id ?? ''),
            resident_id: a.resident_id,
            summary: a.grounds ?? a.sanction_code ?? 'Appeal',
            status: a.status ?? 'open',
            created_at: a.created_at ?? a.filed_at ?? new Date().toISOString(),
          })
        }
        for (const c of confirmations ?? []) {
          merged.push({
            id: c.id,
            type: 'confirmation',
            resident: c.resident_code ?? c.resident ?? String(c.resident_id ?? ''),
            resident_id: c.resident_id,
            summary: c.infraction_code ?? c.code ?? 'Pending confirmation',
            status: c.status ?? 'pending',
            created_at: c.created_at ?? c.issued_at ?? new Date().toISOString(),
          })
        }
        for (const ac of attorney ?? []) {
          merged.push({
            id: ac.id,
            type: 'attorney',
            resident: ac.resident_code ?? ac.resident ?? String(ac.resident_id ?? ''),
            resident_id: ac.resident_id,
            summary: ac.attorney_name ?? ac.subject ?? 'Attorney call request',
            status: ac.status ?? 'pending',
            created_at: ac.created_at ?? ac.requested_at ?? new Date().toISOString(),
          })
        }
        for (const w of welfare ?? []) {
          merged.push({
            id: w.id ?? w.resident_id,
            type: 'welfare',
            resident: w.resident_code ?? w.resident ?? String(w.resident_id ?? ''),
            resident_id: w.resident_id,
            summary: w.reason ?? w.flag_reason ?? 'Welfare flag',
            status: w.status ?? 'open',
            created_at: w.created_at ?? w.flagged_at ?? new Date().toISOString(),
          })
        }

        merged.sort((a, b) => b.created_at.localeCompare(a.created_at))

        if (live) {
          setRows(merged)
          setLoading(false)
        }
      } catch (e) {
        if (live) {
          setError(e instanceof Error ? e.message : String(e))
          setLoading(false)
        }
      }
    }
    void load()
    return () => { live = false }
  }, [])

  return (
    <Page title="Requests">
      {error && <ErrorLine error={error} />}
      {loading ? (
        <div className="space-y-2">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-12 animate-pulse rounded-card bg-surface-2" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <div className="rounded-card border border-line bg-surface p-10 text-center text-ink-soft">
          No open requests right now.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-card border border-line">
          <table className="w-full text-body">
            <thead className="border-b border-line bg-surface-2">
              <tr>
                <th className="px-4 py-3 text-left text-sm font-semibold text-ink-soft">Type</th>
                <th className="px-4 py-3 text-left text-sm font-semibold text-ink-soft">Resident</th>
                <th className="px-4 py-3 text-left text-sm font-semibold text-ink-soft">Subject / Summary</th>
                <th className="px-4 py-3 text-left text-sm font-semibold text-ink-soft">Status</th>
                <th className="px-4 py-3 text-left text-sm font-semibold text-ink-soft">Opened</th>
                <th className="px-4 py-3 text-left text-sm font-semibold text-ink-soft">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line bg-surface">
              {rows.map((row, idx) => (
                <tr
                  key={`${row.type}-${row.id}-${idx}`}
                  className="hover:bg-surface-2 transition-colors"
                >
                  <td className="px-4 py-3">
                    <TypeBadge type={row.type} />
                  </td>
                  <td className="px-4 py-3">
                    {row.resident_id ? (
                      <button
                        onClick={() => navigate(`/staff/residents/${row.resident_id}`)}
                        className="font-medium text-primary underline hover:no-underline"
                      >
                        {row.resident}
                      </button>
                    ) : (
                      <span className="font-medium">{row.resident}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 max-w-xs truncate" title={row.summary}>
                    {row.summary}
                  </td>
                  <td className="px-4 py-3">
                    <StatusChip status={row.status} />
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-ink-soft text-sm">
                    {fmt(row.created_at)}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => navigate(TYPE_META[row.type].to)}
                      className="rounded-ctl border border-line px-3 py-1 text-sm font-medium hover:border-primary hover:text-primary"
                    >
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-sm text-ink-soft">
        {rows.length} open {rows.length === 1 ? 'request' : 'requests'} ·{' '}
        {t('staff.nav.requests')}
      </p>
    </Page>
  )
}
