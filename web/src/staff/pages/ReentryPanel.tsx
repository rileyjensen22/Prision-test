import { useState } from 'react'

import { errorText, fmt, post, put } from '../api'
import { Badge, Btn, ErrorLine, Notice, Panel, Table, Td, Th, useLoad } from '../ui'

interface View {
  release_date: string | null
  checklist: { code: string; title: string; status: string; note?: string; at?: string }[]
  progress: { done: number; resolved: number; total: number }
}

const STATUSES = ['todo', 'in_progress', 'done', 'not_needed']

export default function ReentryPanel({
  residentId,
  canRecord,
  canSetDate,
}: {
  residentId: number
  canRecord: boolean
  canSetDate: boolean
}) {
  const path = `/staff/residents/${residentId}/reentry`
  const { data, error, reload } = useLoad<View>(path)
  const [date, setDate] = useState('')
  const [reason, setReason] = useState('')
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  async function saveDate(clear = false) {
    try {
      await put(`/staff/residents/${residentId}/release-date`, {
        release_date: clear ? null : date,
        reason,
      })
      setMsg({ kind: 'ok', text: clear ? 'Release date cleared.' : 'Release date saved.' })
      await reload()
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  async function setStatus(code: string, status: string) {
    try {
      await post(`/staff/residents/${residentId}/reentry-items`, {
        item_code: code,
        status,
        note: notes[code] || null,
      })
      setNotes({ ...notes, [code]: '' })
      await reload()
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  return (
    <Panel title="Release and reentry" data-testid="reentry-panel">
      <ErrorLine error={error} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      {data && (
        <>
          <p data-testid="release-date">Release date: {data.release_date ?? 'not set'}</p>
          {canSetDate && (
            <div className="my-2 flex flex-wrap items-center gap-2">
              <input
                aria-label="Release date"
                type="date"
                className="rounded-ctl border px-2 py-1"
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
              <input
                aria-label="Reason for the date"
                placeholder="Reason"
                className="rounded-ctl border px-2 py-1"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
              <Btn disabled={!date} onClick={() => void saveDate()}>
                Save date
              </Btn>
              <Btn kind="plain" onClick={() => void saveDate(true)}>
                Clear
              </Btn>
            </div>
          )}
          <p className="text-sm">
            Checklist: {data.progress.resolved} of {data.progress.total} resolved
          </p>
          <Table>
            <thead>
              <tr>
                <Th>Item</Th>
                <Th>Status</Th>
                <Th>Last note</Th>
                {canRecord && <Th>Update</Th>}
              </tr>
            </thead>
            <tbody>
              {data.checklist.map((i) => (
                <tr key={i.code} data-testid={`staff-item-${i.code}`}>
                  <Td>{i.title}</Td>
                  <Td>
                    <Badge tone={i.status === 'done' ? 'green' : 'gray'}>{i.status}</Badge>
                  </Td>
                  <Td>{i.note ? `${i.note} (${fmt(i.at)})` : '—'}</Td>
                  {canRecord && (
                    <Td>
                      <input
                        aria-label={`Note for ${i.code}`}
                        placeholder="Note"
                        className="mr-2 rounded-ctl border px-2 py-1"
                        value={notes[i.code] ?? ''}
                        onChange={(e) => setNotes({ ...notes, [i.code]: e.target.value })}
                      />
                      <select
                        aria-label={`Status for ${i.code}`}
                        className="rounded-ctl border px-2 py-1"
                        value={i.status}
                        onChange={(e) => void setStatus(i.code, e.target.value)}
                      >
                        {STATUSES.map((s) => (
                          <option key={s}>{s}</option>
                        ))}
                      </select>
                    </Td>
                  )}
                </tr>
              ))}
            </tbody>
          </Table>
        </>
      )}
    </Panel>
  )
}
