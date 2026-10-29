import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { errorText, patch } from '../api'
import { useAuth } from '../auth'
import { Badge, Btn, ErrorLine, Notice, Page, Panel, useLoad } from '../ui'

interface HealthRequest {
  id: number
  resident_id: number
  kind: 'medical' | 'mental_health'
  description: string
  status: string
  staff_id: number | null
  staff_note: string
  created_at: string
  updated_at: string
}

const STATUS_TABS = ['open', 'triaged', 'scheduled', 'seen', 'closed'] as const
const KIND_LABELS: Record<string, string> = { medical: 'Medical', mental_health: 'Mental Health' }

export default function HealthRequests() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const canWrite = !!user && ['health_staff', 'supervisor', 'admin'].includes(user.role)

  const [tab, setTab] = useState<string>('open')
  const { data, error, reload } = useLoad<HealthRequest[]>(`/staff/health-requests?status=${tab}`)
  const [editing, setEditing] = useState<number | null>(null)
  const [note, setNote] = useState('')
  const [newStatus, setNewStatus] = useState('')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  async function save(id: number) {
    try {
      await patch(`/staff/health-requests/${id}`, {
        status: newStatus || undefined,
        staff_note: note || undefined,
      })
      setMsg({ kind: 'ok', text: 'Updated.' })
      setEditing(null)
      await reload()
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  return (
    <Page title={t('staff.pages.HealthRequests.title', 'Health Requests')}>
      <p className="text-sm text-ink-soft">
        {t('staff.pages.HealthRequests.note', 'These requests are not visible to officers.')}
      </p>
      <div className="flex gap-2 flex-wrap">
        {STATUS_TABS.map((s) => (
          <button
            key={s}
            onClick={() => {
              setTab(s)
              setMsg(null)
            }}
            className={`rounded-ctl px-4 py-1.5 text-sm font-medium border ${tab === s ? 'bg-primary text-primary-ink border-primary' : 'border-line hover:bg-surface-2'}`}
          >
            {s}
          </button>
        ))}
      </div>
      <ErrorLine error={error} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      {data?.length === 0 && (
        <Panel>
          <p>No {tab} requests.</p>
        </Panel>
      )}
      {(data ?? []).map((r) => (
        <Panel key={r.id} data-testid={`hr-${r.id}`}>
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1">
              <p className="font-semibold">
                <Link className="text-primary underline" to={`/staff/residents/${r.resident_id}`}>
                  Resident #{r.resident_id}
                </Link>
                {' · '}
                <Badge tone={r.kind === 'medical' ? 'amber' : 'green'}>
                  {KIND_LABELS[r.kind] ?? r.kind}
                </Badge>
              </p>
              {r.description && <p className="text-sm">{r.description}</p>}
              {r.staff_note && <p className="text-sm text-ink-soft">Note: {r.staff_note}</p>}
              <p className="text-xs text-ink-soft">{new Date(r.created_at).toLocaleString()}</p>
            </div>
            <Badge tone="gray">{r.status}</Badge>
          </div>
          {canWrite && editing === r.id ? (
            <div className="mt-3 flex flex-wrap gap-2">
              <select
                aria-label="New status"
                value={newStatus}
                onChange={(e) => setNewStatus(e.target.value)}
                className="rounded-ctl border px-2 py-1 text-sm"
              >
                <option value="">— keep status —</option>
                {STATUS_TABS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              <input
                aria-label="Staff note"
                placeholder="Note (optional)"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                className="min-w-48 rounded-ctl border px-2 py-1 text-sm"
              />
              <Btn onClick={() => void save(r.id)}>Save</Btn>
              <Btn kind="plain" onClick={() => setEditing(null)}>
                Cancel
              </Btn>
            </div>
          ) : canWrite ? (
            <Btn
              kind="plain"
              className="mt-2"
              onClick={() => {
                setEditing(r.id)
                setNote(r.staff_note)
                setNewStatus(r.status)
              }}
            >
              Update
            </Btn>
          ) : null}
        </Panel>
      ))}
    </Page>
  )
}
