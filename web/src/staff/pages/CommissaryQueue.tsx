import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { errorText, patch } from '../api'
import { useAuth } from '../auth'
import { Badge, Btn, ErrorLine, Notice, Page, Panel, useLoad } from '../ui'

interface Order {
  id: number
  resident_id: number
  total_cents: number
  status: string
  staff_id: number | null
  refund_reason: string
  created_at: string
  updated_at: string | null
}

const STATUS_TABS = ['new', 'packed', 'delivered', 'refunded'] as const
const NEXT_STATUS: Record<string, string> = { new: 'packed', packed: 'delivered' }

function fmt(cents: number) {
  return `$${(cents / 100).toFixed(2)}`
}

export default function CommissaryQueue() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const canWrite = !!user && ['commissary_clerk', 'supervisor', 'admin'].includes(user.role)

  const [tab, setTab] = useState<string>('new')
  const { data, error, reload } = useLoad<Order[]>(`/staff/commissary/orders?status=${tab}`)
  const [refunding, setRefunding] = useState<number | null>(null)
  const [refundReason, setRefundReason] = useState('')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  async function advance(id: number, status: string) {
    try {
      await patch(`/staff/commissary/orders/${id}`, { status })
      setMsg({ kind: 'ok', text: `Order marked ${status}.` })
      await reload()
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  async function refund(id: number) {
    if (!refundReason.trim()) return
    try {
      await patch(`/staff/commissary/orders/${id}`, { status: 'refunded', refund_reason: refundReason })
      setMsg({ kind: 'ok', text: 'Refund posted to resident ledger.' })
      setRefunding(null)
      setRefundReason('')
      await reload()
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  return (
    <Page title={t('staff.pages.CommissaryQueue.title', 'Commissary Orders')}>
      <div className="flex gap-2 flex-wrap">
        {STATUS_TABS.map((s) => (
          <button
            key={s}
            onClick={() => { setTab(s); setMsg(null) }}
            className={`rounded-ctl px-4 py-1.5 text-sm font-medium border ${tab === s ? 'bg-primary text-primary-ink border-primary' : 'border-line hover:bg-surface-2'}`}
          >
            {s}
          </button>
        ))}
      </div>
      <ErrorLine error={error} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      {data?.length === 0 && <Panel><p>No {tab} orders.</p></Panel>}
      {(data ?? []).map((o) => (
        <Panel key={o.id} data-testid={`order-${o.id}`}>
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1">
              <p className="font-semibold">
                Order #{o.id} ·{' '}
                <Link className="text-primary underline" to={`/staff/residents/${o.resident_id}`}>
                  Resident #{o.resident_id}
                </Link>
              </p>
              <p className="text-sm font-medium">{fmt(o.total_cents)}</p>
              {o.refund_reason && <p className="text-sm text-ink-soft">Refund reason: {o.refund_reason}</p>}
              <p className="text-xs text-ink-soft">{new Date(o.created_at).toLocaleString()}</p>
            </div>
            <Badge tone="gray">{o.status}</Badge>
          </div>
          {canWrite && (
            <div className="mt-3 flex flex-wrap gap-2">
              {NEXT_STATUS[o.status] && (
                <Btn onClick={() => void advance(o.id, NEXT_STATUS[o.status])}>
                  Mark {NEXT_STATUS[o.status]}
                </Btn>
              )}
              {o.status !== 'refunded' && o.status !== 'delivered' && (
                refunding === o.id ? (
                  <div className="flex flex-wrap gap-2">
                    <input
                      aria-label="Refund reason"
                      placeholder="Reason for refund (required)"
                      value={refundReason}
                      onChange={(e) => setRefundReason(e.target.value)}
                      className="min-w-48 rounded-ctl border px-2 py-1 text-sm"
                    />
                    <Btn disabled={!refundReason.trim()} onClick={() => void refund(o.id)}>
                      Confirm refund
                    </Btn>
                    <Btn kind="plain" onClick={() => { setRefunding(null); setRefundReason('') }}>Cancel</Btn>
                  </div>
                ) : (
                  <Btn kind="plain" onClick={() => setRefunding(o.id)}>Refund</Btn>
                )
              )}
            </div>
          )}
        </Panel>
      ))}
    </Page>
  )
}
