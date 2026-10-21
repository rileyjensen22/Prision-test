import { useState } from 'react'

import { errorText, fmt, post } from '../api'
import { useAuth } from '../auth'
import { Badge, Btn, ErrorLine, Notice, Page, Table, Td, Th, useLoad } from '../ui'

interface Item {
  appeal_id: number
  sanction_id: number
  resident_code: string
  infraction_code: string
  status: string
  filed_at: string
  due_at: string | null
  overdue: boolean
  issued_by: { username: string } | null
  reviewer: { username: string } | null
  outcome_note: string | null
  can_review: boolean
}

export default function Appeals() {
  const { user } = useAuth()
  const [closed, setClosed] = useState(false)
  const { data, error, reload } = useLoad<Item[]>(`/staff/appeals?include_closed=${closed}`)
  const [open, setOpen] = useState<number | null>(null)
  const [outcome, setOutcome] = useState<'upheld' | 'overturned'>('upheld')
  const [note, setNote] = useState('')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  async function review(id: number) {
    try {
      await post(`/staff/appeals/${id}/review`, { outcome, note })
      setMsg({
        kind: 'ok',
        text: outcome === 'overturned' ? 'Overturned. The lock has been lifted.' : 'Upheld.',
      })
      setOpen(null)
      setNote('')
      await reload()
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  return (
    <Page title="Appeals">
      <p className="text-sm text-gray-600">
        Reviewed by someone other than the person who recorded the infraction, within the review
        window.
      </p>
      <label className="text-sm">
        <input type="checkbox" checked={closed} onChange={(e) => setClosed(e.target.checked)} />{' '}
        Show decided appeals
      </label>
      <ErrorLine error={error} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      <Table data-testid="appeal-queue">
        <thead>
          <tr>
            <Th>Resident</Th>
            <Th>Infraction</Th>
            <Th>Recorded by</Th>
            <Th>Filed</Th>
            <Th>Due</Th>
            <Th>Status</Th>
            <Th>Action</Th>
          </tr>
        </thead>
        <tbody>
          {(data ?? []).length === 0 && (
            <tr>
              <Td>No appeals.</Td>
            </tr>
          )}
          {(data ?? []).map((a) => (
            <tr key={a.appeal_id} data-testid={`appeal-${a.appeal_id}`}>
              <Td>{a.resident_code}</Td>
              <Td>{a.infraction_code}</Td>
              <Td>{a.issued_by?.username ?? 'system'}</Td>
              <Td>{fmt(a.filed_at)}</Td>
              <Td>
                {fmt(a.due_at)} {a.overdue && <Badge tone="red">overdue</Badge>}
              </Td>
              <Td>
                {a.status}
                {a.reviewer && ` by ${a.reviewer.username}`}
                {a.outcome_note && <div className="text-gray-600">{a.outcome_note}</div>}
              </Td>
              <Td>
                {a.status !== 'open' ? (
                  ''
                ) : user?.role !== 'supervisor' ? (
                  <span className="text-gray-500">Supervisors only</span>
                ) : !a.can_review ? (
                  <span data-testid="own-appeal" className="text-gray-600">
                    You recorded this; another supervisor must review.
                  </span>
                ) : open === a.appeal_id ? (
                  <span className="flex flex-wrap gap-2">
                    <select
                      aria-label="Outcome"
                      value={outcome}
                      onChange={(e) => setOutcome(e.target.value as 'upheld' | 'overturned')}
                      className="rounded border px-2 py-1"
                    >
                      <option value="upheld">Uphold</option>
                      <option value="overturned">Overturn</option>
                    </select>
                    <input
                      aria-label="Review note"
                      placeholder="Reason"
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      className="rounded border px-2 py-1"
                    />
                    <Btn disabled={!note.trim()} onClick={() => void review(a.appeal_id)}>
                      Submit decision
                    </Btn>
                    <Btn kind="plain" onClick={() => setOpen(null)}>
                      Cancel
                    </Btn>
                  </span>
                ) : (
                  <Btn onClick={() => setOpen(a.appeal_id)}>Review…</Btn>
                )}
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Page>
  )
}
