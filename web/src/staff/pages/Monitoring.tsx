import { useState } from 'react'

import { errorText, fmt, post } from '../api'
import { useAuth } from '../auth'
import { Badge, Btn, ErrorLine, Notice, Page, Panel, Table, Td, Th, useLoad } from '../ui'

interface Flag {
  id: number
  label: string
  status: 'open' | 'reviewed' | 'referred'
  rule_id: string
}
interface Row {
  message_id: number
  resident_id: number
  resident: string
  direction: 'out' | 'in'
  contact_type: string
  at: string
  flags: Flag[]
}
interface Opened {
  message_id: number
  body: string
  direction: string
  at: string
}

export default function Monitoring() {
  const { user } = useAuth()
  const [flaggedOnly, setFlaggedOnly] = useState(true)
  const { data, error, reload } = useLoad<Row[]>(
    `/staff/monitoring/messages?flagged=${flaggedOnly}`,
  )
  const [reason, setReason] = useState('')
  const [opened, setOpened] = useState<Opened | null>(null)
  const [outcomeReason, setOutcomeReason] = useState('')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)
  const canReview = !!user && ['supervisor', 'admin'].includes(user.role)

  async function read(r: Row) {
    setMsg(null)
    try {
      setOpened(await post<Opened>(`/staff/monitoring/messages/${r.message_id}/read`, { reason }))
    } catch (e) {
      setOpened(null)
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  async function review(f: Flag, outcome: 'no_action' | 'referred') {
    try {
      await post(`/staff/monitoring/flags/${f.id}/review`, { outcome, reason: outcomeReason })
      setMsg({
        kind: 'ok',
        text: outcome === 'referred' ? 'Referred to a supervisor.' : 'Recorded.',
      })
      setOutcomeReason('')
      await reload()
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  return (
    <Page title="Message monitoring">
      <p className="text-sm text-ink-soft">
        This list shows who, when and which keyword rule matched, never the text. To read a message
        you must state a reason, and every read is logged. A keyword match is only a prompt to look:
        it never creates a sanction. Attorney messages are private and do not appear here.
      </p>
      <ErrorLine error={error} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      <Panel>
        <div className="mb-3 flex flex-wrap items-end gap-3">
          <label className="text-sm">
            <input
              type="checkbox"
              checked={flaggedOnly}
              onChange={(e) => setFlaggedOnly(e.target.checked)}
            />{' '}
            Only messages with open flags
          </label>
          <label className="text-sm">
            Reason for reading
            <input
              aria-label="Reason for reading"
              className="ml-2 w-72 rounded-ctl border px-2 py-1"
              placeholder="Why do you need to read this?"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
        </div>
        {data?.length === 0 && <p data-testid="no-monitored">Nothing to review.</p>}
        {!!data?.length && (
          <Table data-testid="monitored-messages">
            <thead>
              <tr>
                <Th>When</Th>
                <Th>Resident</Th>
                <Th>Direction</Th>
                <Th>Contact</Th>
                <Th>Flags</Th>
                <Th></Th>
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.message_id} data-testid={`monitored-${r.message_id}`}>
                  <Td>{fmt(r.at)}</Td>
                  <Td>{r.resident}</Td>
                  <Td>{r.direction === 'out' ? 'from resident' : 'to resident'}</Td>
                  <Td>{r.contact_type}</Td>
                  <Td>
                    {r.flags.map((f) => (
                      <div key={f.id}>
                        <Badge tone={f.status === 'open' ? 'amber' : 'gray'}>{f.status}</Badge>{' '}
                        {f.label}
                      </div>
                    ))}
                  </Td>
                  <Td>
                    <Btn kind="plain" onClick={() => void read(r)}>
                      Read
                    </Btn>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>
      {opened && (
        <Panel title={`Message ${opened.message_id}`} data-testid="opened-message">
          <p className="rounded-ctl bg-surface-2 p-3" data-testid="opened-body">
            {opened.body}
          </p>
          <p className="mt-1 text-sm text-ink-soft">
            This read was logged with your reason. Do not copy or share the text.
          </p>
          {canReview &&
            data
              ?.find((r) => r.message_id === opened.message_id)
              ?.flags.filter((f) => f.status === 'open')
              .map((f) => (
                <div key={f.id} className="mt-3 flex flex-wrap items-center gap-2">
                  <span className="text-sm">{f.label}:</span>
                  <input
                    aria-label="Reason for outcome"
                    className="w-64 rounded-ctl border px-2 py-1"
                    placeholder="Reason for this outcome"
                    value={outcomeReason}
                    onChange={(e) => setOutcomeReason(e.target.value)}
                  />
                  <Btn onClick={() => void review(f, 'no_action')}>No action needed</Btn>
                  <Btn kind="plain" onClick={() => void review(f, 'referred')}>
                    Refer to a supervisor
                  </Btn>
                </div>
              ))}
        </Panel>
      )}
    </Page>
  )
}
