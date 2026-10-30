import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { errorText, patch } from '../api'
import { useAuth } from '../auth'
import { Badge, Btn, ErrorLine, Notice, Page, Panel, useLoad } from '../ui'
// Notice is used for ok/err messages only; Panel used for informational banners

interface AttorneyCallRequest {
  id: number
  resident_id: number
  contact_id: number | null
  attorney_name: string
  attorney_phone: string
  status: string
  staff_id: number | null
  staff_note: string
  requested_at: string
  scheduled_at: string | null
}

const STATUS_TABS = ['pending', 'approved', 'scheduled', 'completed', 'denied'] as const
const TONE: Record<string, 'amber' | 'green' | 'gray' | 'red'> = {
  pending: 'amber',
  approved: 'green',
  scheduled: 'green',
  completed: 'gray',
  denied: 'red',
}

export default function AttorneyCalls() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const canWrite = !!user && ['legal_liaison', 'supervisor', 'admin'].includes(user.role)

  const [tab, setTab] = useState<string>('pending')
  const { data, error, reload } = useLoad<AttorneyCallRequest[]>(
    `/staff/attorney-calls?status=${tab}`,
  )
  const [editing, setEditing] = useState<number | null>(null)
  const [newStatus, setNewStatus] = useState('')
  const [scheduledAt, setScheduledAt] = useState('')
  const [note, setNote] = useState('')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  async function save(id: number) {
    try {
      await patch(`/staff/attorney-calls/${id}`, {
        status: newStatus || undefined,
        scheduled_at: scheduledAt || undefined,
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
    <Page title={t('staff.pages.AttorneyCalls.title', 'Attorney Call Requests')}>
      <Panel className="border-primary bg-primary/5 text-sm">
        Attorney calls are privileged. No content is ever recorded, transcribed, or logged — only
        that a call occurred and its duration.
      </Panel>
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
        <Panel key={r.id} data-testid={`acr-${r.id}`}>
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1">
              <p className="font-semibold">
                <Link className="text-primary underline" to={`/staff/residents/${r.resident_id}`}>
                  Resident #{r.resident_id}
                </Link>
              </p>
              {r.attorney_name && <p className="text-sm">Attorney: {r.attorney_name}</p>}
              {r.attorney_phone && <p className="text-sm">Phone: {r.attorney_phone}</p>}
              {r.scheduled_at && (
                <p className="text-sm">Scheduled: {new Date(r.scheduled_at).toLocaleString()}</p>
              )}
              {r.staff_note && <p className="text-sm text-ink-soft">Note: {r.staff_note}</p>}
              <p className="text-xs text-ink-soft">
                Requested {new Date(r.requested_at).toLocaleString()}
              </p>
            </div>
            <Badge tone={TONE[r.status] ?? 'gray'}>{r.status}</Badge>
          </div>
          {canWrite && editing === r.id ? (
            <div className="mt-3 space-y-2">
              <select
                aria-label="New status"
                value={newStatus}
                onChange={(e) => setNewStatus(e.target.value)}
                className="w-full rounded-ctl border px-2 py-1 text-sm"
              >
                <option value="">— keep status —</option>
                {STATUS_TABS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              <div>
                <label className="text-sm font-medium">Schedule date/time</label>
                <input
                  type="datetime-local"
                  value={scheduledAt}
                  onChange={(e) => setScheduledAt(e.target.value)}
                  className="mt-1 w-full rounded-ctl border px-2 py-1 text-sm"
                />
              </div>
              <input
                aria-label="Note"
                placeholder="Note (optional)"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                className="w-full rounded-ctl border px-2 py-1 text-sm"
              />
              <div className="flex gap-2">
                <Btn onClick={() => void save(r.id)}>Save</Btn>
                <Btn kind="plain" onClick={() => setEditing(null)}>
                  Cancel
                </Btn>
              </div>
            </div>
          ) : canWrite ? (
            <Btn
              kind="plain"
              className="mt-2"
              onClick={() => {
                setEditing(r.id)
                setNewStatus(r.status)
                setNote(r.staff_note)
                setScheduledAt(r.scheduled_at ?? '')
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
