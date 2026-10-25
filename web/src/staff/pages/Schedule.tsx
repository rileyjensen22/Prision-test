import { useState } from 'react'

import { errorText, post } from '../api'
import { useAuth } from '../auth'
import { Badge, Btn, ErrorLine, Notice, Page, Panel, Table, Td, Th, useLoad } from '../ui'

interface Block {
  id: number | null
  kind: 'indoor' | 'outdoor' | 'program' | 'visit'
  start: string
  minutes: number
  capacity: number
  title: string | null
  required_feature: string | null
  status: string
  booked: number
}
interface Day {
  unit: string
  day: string
  explicit: boolean
  blocks: Block[]
}

const today = () => new Date().toISOString().slice(0, 10)

export default function Schedule() {
  const { user } = useAuth()
  const units = useLoad<string[]>('/staff/schedule/units')
  const [unit, setUnit] = useState('A')
  const [day, setDay] = useState(today())
  const view = useLoad<Day>(`/staff/schedule?unit=${encodeURIComponent(unit)}&day=${day}`)
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)
  const [form, setForm] = useState({
    kind: 'program',
    start: '19:00',
    minutes: 45,
    capacity: 6,
    title: '',
    reason: '',
  })
  const [cancelReason, setCancelReason] = useState('')
  const canEdit = !!user && ['supervisor', 'admin'].includes(user.role)

  async function run(fn: () => Promise<unknown>, ok: string) {
    try {
      await fn()
      setMsg({ kind: 'ok', text: ok })
      await view.reload()
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  const field = 'rounded-ctl border px-2 py-1'
  return (
    <Page title="Unit schedule">
      <p className="text-sm text-ink-soft">
        Each unit has its own day: indoor and outdoor recreation, programs and visits. A day with no
        changes uses the default template. Who can sign up comes from the entitlement rules (for
        example outdoor time at tiers 9 and 10), not from this page.
      </p>
      <ErrorLine error={units.error ?? view.error} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      <Panel>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm">
            Unit
            <select
              aria-label="Unit"
              className={`${field} ml-2`}
              value={unit}
              onChange={(e) => setUnit(e.target.value)}
            >
              {(units.data ?? ['A']).map((u) => (
                <option key={u}>{u}</option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            Day
            <input
              aria-label="Day"
              type="date"
              className={`${field} ml-2`}
              value={day}
              onChange={(e) => setDay(e.target.value)}
            />
          </label>
          {view.data && (
            <Badge tone={view.data.explicit ? 'green' : 'gray'}>
              {view.data.explicit ? 'saved for this day' : 'default template'}
            </Badge>
          )}
          {user?.role === 'admin' && (
            <Btn
              kind="plain"
              onClick={() =>
                void run(() => post('/staff/schedule/generate?days=7'), 'Next week made.')
              }
            >
              Make the next week
            </Btn>
          )}
        </div>
      </Panel>
      <Panel title={`Unit ${unit}, ${day}`}>
        <Table data-testid="schedule-blocks">
          <thead>
            <tr>
              <Th>Start</Th>
              <Th>What</Th>
              <Th>Length</Th>
              <Th>Signed up</Th>
              <Th>Who can sign up</Th>
              <Th></Th>
            </tr>
          </thead>
          <tbody>
            {(view.data?.blocks ?? []).map((b) => (
              <tr key={`${b.start}-${b.kind}`} data-testid={`block-${b.start}-${b.kind}`}>
                <Td>{b.start}</Td>
                <Td>
                  {b.title ?? b.kind}{' '}
                  <Badge tone={b.kind === 'visit' ? 'amber' : 'gray'}>{b.kind}</Badge>
                  {b.status === 'cancelled' && <Badge tone="red">cancelled</Badge>}
                </Td>
                <Td>{b.minutes} min</Td>
                <Td>
                  {b.booked} / {b.capacity}
                </Td>
                <Td>{b.required_feature ?? 'anyone'}</Td>
                <Td>
                  {canEdit && b.id && b.status === 'scheduled' && (
                    <Btn
                      kind="plain"
                      disabled={cancelReason.trim().length < 5}
                      onClick={() =>
                        void run(
                          () =>
                            post(`/staff/schedule/blocks/${b.id}/cancel`, { reason: cancelReason }),
                          'Block cancelled.',
                        )
                      }
                    >
                      Cancel
                    </Btn>
                  )}
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
        {canEdit && (
          <label className="mt-3 block text-sm">
            Reason for cancelling
            <input
              aria-label="Reason for cancelling"
              className={`${field} ml-2 w-72`}
              value={cancelReason}
              onChange={(e) => setCancelReason(e.target.value)}
            />
          </label>
        )}
      </Panel>
      {canEdit && (
        <Panel title="Add a block">
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-sm">
              Kind
              <select
                aria-label="Kind"
                className={`${field} ml-2`}
                value={form.kind}
                onChange={(e) => setForm({ ...form, kind: e.target.value })}
              >
                {['indoor', 'outdoor', 'program', 'visit'].map((k) => (
                  <option key={k}>{k}</option>
                ))}
              </select>
            </label>
            <label className="text-sm">
              Start
              <input
                aria-label="Start time"
                className={`${field} ml-2 w-20`}
                value={form.start}
                onChange={(e) => setForm({ ...form, start: e.target.value })}
              />
            </label>
            <label className="text-sm">
              Minutes
              <input
                aria-label="Minutes"
                type="number"
                className={`${field} ml-2 w-20`}
                value={form.minutes}
                onChange={(e) => setForm({ ...form, minutes: Number(e.target.value) })}
              />
            </label>
            <label className="text-sm">
              Capacity
              <input
                aria-label="Capacity"
                type="number"
                className={`${field} ml-2 w-20`}
                value={form.capacity}
                onChange={(e) => setForm({ ...form, capacity: Number(e.target.value) })}
              />
            </label>
            <label className="text-sm">
              Title
              <input
                aria-label="Title"
                className={`${field} ml-2 w-48`}
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
              />
            </label>
            <label className="text-sm">
              Reason
              <input
                aria-label="Reason"
                className={`${field} ml-2 w-64`}
                value={form.reason}
                onChange={(e) => setForm({ ...form, reason: e.target.value })}
              />
            </label>
            <Btn
              onClick={() =>
                void run(
                  () =>
                    post('/staff/schedule/blocks', {
                      unit,
                      day,
                      kind: form.kind,
                      start: form.start,
                      minutes: form.minutes,
                      capacity: form.capacity,
                      title: form.title || null,
                      reason: form.reason,
                    }),
                  'Block added.',
                )
              }
            >
              Add block
            </Btn>
          </div>
        </Panel>
      )}
    </Page>
  )
}
