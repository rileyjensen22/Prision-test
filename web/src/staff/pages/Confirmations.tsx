import { useState } from 'react'

import { errorText, fmt, post } from '../api'
import { useAuth } from '../auth'
import { Badge, Btn, ErrorLine, Notice, Page, Table, Td, Th, useLoad } from '../ui'

interface Item {
  id: number
  resident_code: string
  infraction_code: string
  label: string
  severity: string
  duration_hours: number
  issued_at: string
  why_pending: string
  can_confirm: boolean
  issued_by: { id: number; username: string } | null
  evidence: { type: string | null; reporter: { username: string } | null; ref: string | null }
}

export default function Confirmations() {
  const { user } = useAuth()
  const { data, error, reload } = useLoad<Item[]>('/staff/confirmations')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)
  const [rejecting, setRejecting] = useState<number | null>(null)
  const [note, setNote] = useState('')
  const isSupervisor = user?.role === 'supervisor'

  async function act(fn: () => Promise<unknown>, ok: string) {
    setMsg(null)
    try {
      await fn()
      setMsg({ kind: 'ok', text: ok })
      setRejecting(null)
      setNote('')
      await reload()
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  return (
    <Page title="Awaiting confirmation">
      <p className="text-sm text-ink-soft">
        A supervisor other than the person who recorded it must confirm each one. Nothing is locked
        for the resident until then.
      </p>
      <ErrorLine error={error} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      <Table data-testid="confirmation-queue">
        <thead>
          <tr>
            <Th>Resident</Th>
            <Th>Infraction</Th>
            <Th>Recorded by</Th>
            <Th>Evidence</Th>
            <Th>Why waiting</Th>
            <Th>Action</Th>
          </tr>
        </thead>
        <tbody>
          {(data ?? []).length === 0 && (
            <tr>
              <Td>Nothing waiting.</Td>
            </tr>
          )}
          {(data ?? []).map((q) => (
            <tr key={q.id} data-testid={`pending-${q.id}`}>
              <Td>{q.resident_code}</Td>
              <Td>
                {q.infraction_code}{' '}
                <Badge tone={q.severity === 'major' ? 'red' : 'gray'}>{q.severity}</Badge>
                <div className="text-ink-soft">
                  {q.label}, {q.duration_hours}h · {fmt(q.issued_at)}
                </div>
              </Td>
              <Td>{q.issued_by?.username ?? 'system'}</Td>
              <Td>
                {q.evidence.type === 'second_staff_report'
                  ? `Report from ${q.evidence.reporter?.username ?? '?'}`
                  : q.evidence.type === 'system_event'
                    ? `System event ${q.evidence.ref ?? ''}`
                    : 'None needed'}
              </Td>
              <Td>{q.why_pending}</Td>
              <Td>
                {!isSupervisor ? (
                  <span className="text-ink-soft">Supervisors only</span>
                ) : !q.can_confirm ? (
                  <span data-testid="own-sanction" className="text-ink-soft">
                    You recorded this; another supervisor must confirm.
                  </span>
                ) : rejecting === q.id ? (
                  <span className="flex gap-2">
                    <input
                      aria-label="Reason for rejecting"
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      className="rounded-ctl border px-2 py-1"
                    />
                    <Btn
                      kind="danger"
                      disabled={!note.trim()}
                      onClick={() =>
                        void act(
                          () => post(`/staff/sanctions/${q.id}/reject`, { note }),
                          'Rejected.',
                        )
                      }
                    >
                      Reject
                    </Btn>
                    <Btn kind="plain" onClick={() => setRejecting(null)}>
                      Cancel
                    </Btn>
                  </span>
                ) : (
                  <span className="flex gap-2">
                    <Btn
                      onClick={() =>
                        void act(
                          () => post(`/staff/sanctions/${q.id}/confirm`),
                          'Confirmed. The lock is now active.',
                        )
                      }
                    >
                      Confirm
                    </Btn>
                    <Btn kind="plain" onClick={() => setRejecting(q.id)}>
                      Reject…
                    </Btn>
                  </span>
                )}
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Page>
  )
}
