import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { errorText, patch } from '../api'
import { useAuth } from '../auth'
import { Badge, Btn, ErrorLine, Notice, Page, Panel, useLoad } from '../ui'

interface Grievance {
  id: number
  resident_id: number
  category: string
  description: string
  status: string
  assigned_to: number | null
  response: string
  due_at: string | null
  created_at: string
  updated_at: string
}

const STATUS_TABS = ['open', 'under_review', 'resolved', 'closed'] as const

export default function Grievances() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const canWrite = !!user && ['supervisor', 'admin'].includes(user.role)

  const [tab, setTab] = useState<string>('open')
  const { data, error, reload } = useLoad<Grievance[]>(`/staff/grievances?status=${tab}`)
  const [editing, setEditing] = useState<number | null>(null)
  const [response, setResponse] = useState('')
  const [newStatus, setNewStatus] = useState('')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  async function save(id: number) {
    try {
      await patch(`/staff/grievances/${id}`, {
        status: newStatus || undefined,
        response: response || undefined,
      })
      setMsg({ kind: 'ok', text: 'Updated.' })
      setEditing(null)
      await reload()
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  return (
    <Page title={t('staff.pages.Grievances.title', 'Grievances')}>
      <p className="text-sm text-ink-soft">
        Supervisor and admin only. A grievance cannot be decided by the staff member it names.
      </p>
      <div className="flex gap-2 flex-wrap">
        {STATUS_TABS.map((s) => (
          <button
            key={s}
            onClick={() => { setTab(s); setMsg(null) }}
            className={`rounded-ctl px-4 py-1.5 text-sm font-medium border ${tab === s ? 'bg-primary text-primary-ink border-primary' : 'border-line hover:bg-surface-2'}`}
          >
            {s.replace('_', ' ')}
          </button>
        ))}
      </div>
      <ErrorLine error={error} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      {data?.length === 0 && <Panel><p>No {tab.replace('_', ' ')} grievances.</p></Panel>}
      {(data ?? []).map((g) => (
        <Panel key={g.id} data-testid={`grievance-${g.id}`}>
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1">
              <p className="font-semibold">
                <Link className="text-primary underline" to={`/staff/residents/${g.resident_id}`}>
                  Resident #{g.resident_id}
                </Link>
                {' · '}
                <span className="text-sm capitalize">{g.category}</span>
              </p>
              {g.description && <p className="text-sm">{g.description}</p>}
              {g.response && <p className="text-sm text-ink-soft">Response: {g.response}</p>}
              {g.due_at && (
                <p className="text-xs text-ink-soft">
                  Due: {new Date(g.due_at).toLocaleDateString()}
                </p>
              )}
              <p className="text-xs text-ink-soft">{new Date(g.created_at).toLocaleString()}</p>
            </div>
            <Badge tone="gray">{g.status.replace('_', ' ')}</Badge>
          </div>
          {canWrite && editing === g.id ? (
            <div className="mt-3 space-y-2">
              <select
                aria-label="New status"
                value={newStatus}
                onChange={(e) => setNewStatus(e.target.value)}
                className="w-full rounded-ctl border px-2 py-1 text-sm"
              >
                <option value="">— keep status —</option>
                {STATUS_TABS.map((s) => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
              </select>
              <textarea
                aria-label="Response"
                placeholder="Response (optional)"
                value={response}
                onChange={(e) => setResponse(e.target.value)}
                rows={3}
                className="w-full rounded-ctl border px-2 py-1 text-sm"
              />
              <div className="flex gap-2">
                <Btn onClick={() => void save(g.id)}>Save</Btn>
                <Btn kind="plain" onClick={() => setEditing(null)}>Cancel</Btn>
              </div>
            </div>
          ) : canWrite ? (
            <Btn kind="plain" className="mt-2" onClick={() => { setEditing(g.id); setResponse(g.response); setNewStatus(g.status) }}>
              Respond
            </Btn>
          ) : null}
        </Panel>
      ))}
    </Page>
  )
}
