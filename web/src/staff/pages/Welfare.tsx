import { useState } from 'react'
import { Link } from 'react-router-dom'

import { errorText, post } from '../api'
import { useAuth } from '../auth'
import { Badge, Btn, ErrorLine, Notice, Page, Panel, useLoad } from '../ui'

interface Flag {
  id: number
  escalated: boolean
  type: string
  severity: string
  message: string
  detail: Record<string, unknown>
}
interface Row {
  resident_id: number
  code: string
  flags: Flag[]
}

function describe(f: Flag): string {
  const d = f.detail
  switch (f.type) {
    case 'no_contact':
      return d.never
        ? `They have never had contact (${d.days} days on the unit).`
        : `${d.days} days since any contact.`
    case 'usage_drop':
    case 'contact_drop':
      return `Usually ${d.usual} a day, lately ${d.recent} a day.`
    case 'out_of_cell_below':
      return `Lowest recent day: ${d.lowest} minutes (minimum ${d.minimum}).`
    case 'out_of_cell_unrecorded':
      return `Nothing recorded for the last ${d.days} days.`
    default:
      return ''
  }
}

export default function Welfare() {
  const { user } = useAuth()
  const { data, error, reload } = useLoad<Row[]>('/staff/welfare')
  const canAck = user && ['officer', 'supervisor', 'admin'].includes(user.role)
  const canHandleEscalated = !!user && ['supervisor', 'admin'].includes(user.role)
  const [open, setOpen] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [action, setAction] = useState('checked_in')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  async function ack(r: Row, f: Flag) {
    try {
      await post('/staff/welfare/ack', {
        resident_id: r.resident_id,
        flag_type: f.type,
        note,
        action,
      })
      setMsg({ kind: 'ok', text: `Recorded. This flag stays quiet for a few days.` })
      setOpen(null)
      setNote('')
      await reload()
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  return (
    <Page title="Welfare">
      <p className="text-sm text-gray-600">
        Each resident is compared with their own usual pattern. A flag means “please check in”, not
        that something is wrong.
      </p>
      <ErrorLine error={error} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      {data?.length === 0 && (
        <Panel>
          <p data-testid="welfare-clear">No welfare flags right now.</p>
        </Panel>
      )}
      {(data ?? []).map((r) => (
        <Panel key={r.resident_id} data-testid={`welfare-${r.code}`}>
          <h2 className="mb-2 text-lg font-semibold">
            <Link className="text-blue-700 underline" to={`/staff/residents/${r.resident_id}`}>
              {r.code}
            </Link>
          </h2>
          <ul className="space-y-3">
            {r.flags.map((f) => (
              <li key={f.type} data-testid={`flag-${f.type}`}>
                <Badge tone={f.severity === 'attention' ? 'amber' : 'gray'}>{f.severity}</Badge>{' '}
                {f.escalated && (
                  <Badge tone="red" data-testid="escalated">
                    escalated to a supervisor
                  </Badge>
                )}{' '}
                <strong>{f.message}</strong>
                <div className="text-sm text-gray-700">{describe(f)}</div>
                {f.escalated && !canHandleEscalated && (
                  <p className="mt-1 text-sm text-gray-600">A supervisor must handle this flag.</p>
                )}
                {canAck &&
                  (f.escalated ? canHandleEscalated : true) &&
                  (open === `${r.code}:${f.type}` ? (
                    <div className="mt-2 flex flex-wrap gap-2">
                      <select
                        aria-label="Action taken"
                        value={action}
                        onChange={(e) => setAction(e.target.value)}
                        className="rounded border px-2 py-1"
                      >
                        <option value="checked_in">Checked in with the resident</option>
                        <option value="referred_medical">Referred to medical</option>
                        <option value="referred_mental_health">Referred to mental health</option>
                        <option value="adjusted_schedule">Adjusted their schedule</option>
                        <option value="no_concern">No concern after looking</option>
                      </select>
                      <input
                        aria-label="What was done"
                        placeholder="What was done?"
                        value={note}
                        onChange={(e) => setNote(e.target.value)}
                        className="min-w-64 rounded border px-2 py-1"
                      />
                      <Btn disabled={note.trim().length < 3} onClick={() => void ack(r, f)}>
                        Record check-in
                      </Btn>
                      <Btn kind="plain" onClick={() => setOpen(null)}>
                        Cancel
                      </Btn>
                    </div>
                  ) : (
                    <Btn kind="plain" onClick={() => setOpen(`${r.code}:${f.type}`)}>
                      I checked in…
                    </Btn>
                  ))}
              </li>
            ))}
          </ul>
        </Panel>
      ))}
    </Page>
  )
}
