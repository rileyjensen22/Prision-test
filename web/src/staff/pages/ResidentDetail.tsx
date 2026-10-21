import { useState } from 'react'
import type { FormEvent } from 'react'
import { useParams } from 'react-router-dom'

import { errorText, fmt, post, put } from '../api'
import { useAuth } from '../auth'
import { Badge, Btn, ErrorLine, Notice, Page, Panel, Table, Td, Th, useLoad } from '../ui'

interface Detail {
  resident_id: number
  code: string
  display_name: string
  settings: { language: string; text_size: string; reading_level: string; captions: boolean }
  prior_returns: number
  device: string | null
  cell: string | null
  tier: { earned: number; ceiling: number; effective: number }
  points: number
  sanctions: {
    id: number
    code: string
    status: string
    issued_at: string
    issued_by: { id: number; username: string } | null
    confirmed_by: { id: number; username: string } | null
    ends_at: string | null
    active: boolean
  }[]
  point_events: { kind: string; points: number; at: string; reason: string | null }[]
  tier_history: { at: string; from: number; to: number; points: number }[]
}
interface Infraction {
  code: string
  label: string
  scope: string
  duration_hours: number
  confirmation: string
  severity: string
}
interface Colleague {
  id: number
  username: string
  role: string
}

const needsSupervisor = (i: Infraction) =>
  i.confirmation !== 'officer_immediate' || i.duration_hours > 24

function IssueSanction({ residentId, onDone }: { residentId: number; onDone: () => void }) {
  const { user } = useAuth()
  const infractions = useLoad<Infraction[]>('/staff/infractions')
  const colleagues = useLoad<Colleague[]>('/staff/colleagues')
  const [code, setCode] = useState('')
  const [evType, setEvType] = useState<'second_staff_report' | 'system_event'>(
    'second_staff_report',
  )
  const [reporter, setReporter] = useState('')
  const [ref, setRef] = useState('')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)
  const inf = infractions.data?.find((i) => i.code === code)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setMsg(null)
    const evidence =
      inf && needsSupervisor(inf)
        ? evType === 'system_event'
          ? { type: evType, ref }
          : { type: evType, reporter_id: Number(reporter) }
        : undefined
    try {
      const r = await post<{ id: number; status: string }>('/staff/sanctions', {
        resident_id: residentId,
        infraction_code: code,
        evidence,
      })
      setMsg({
        kind: 'ok',
        text:
          r.status === 'active'
            ? `Sanction ${r.id} applied now.`
            : `Sanction ${r.id} sent for supervisor confirmation.`,
      })
      onDone()
    } catch (err) {
      setMsg({ kind: 'err', text: errorText(err) })
    }
  }

  return (
    <Panel title="Record an infraction" data-testid="issue-panel">
      <form onSubmit={submit} className="space-y-3">
        <label className="block text-sm">
          Infraction
          <select
            value={code}
            onChange={(e) => setCode(e.target.value)}
            className="mt-1 block w-full rounded border px-2 py-2"
          >
            <option value="">Choose…</option>
            {(infractions.data ?? []).map((i) => (
              <option key={i.code} value={i.code}>
                {i.code} — {i.label}
              </option>
            ))}
          </select>
        </label>
        {inf && (
          <p className="text-sm text-gray-700" data-testid="infraction-help">
            Locks {inf.scope.replace(/_/g, ' ')} for {inf.duration_hours} hours.{' '}
            {needsSupervisor(inf)
              ? 'Needs evidence and a supervisor’s confirmation.'
              : 'Applies immediately (weekly cap applies).'}
          </p>
        )}
        {inf && needsSupervisor(inf) && (
          <fieldset className="space-y-2 rounded border p-3">
            <legend className="px-1 text-sm font-medium">Evidence</legend>
            <label className="mr-4 text-sm">
              <input
                type="radio"
                checked={evType === 'second_staff_report'}
                onChange={() => setEvType('second_staff_report')}
              />{' '}
              Report from a second staff member
            </label>
            <label className="text-sm">
              <input
                type="radio"
                checked={evType === 'system_event'}
                onChange={() => setEvType('system_event')}
              />{' '}
              System-detected event
            </label>
            {evType === 'second_staff_report' ? (
              <label className="block text-sm">
                Reported by
                <select
                  value={reporter}
                  onChange={(e) => setReporter(e.target.value)}
                  className="mt-1 block w-full rounded border px-2 py-2"
                  aria-label="Reported by"
                >
                  <option value="">Choose a colleague…</option>
                  {(colleagues.data ?? [])
                    .filter((c) => c.id !== user?.id)
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.username} ({c.role})
                      </option>
                    ))}
                </select>
              </label>
            ) : (
              <label className="block text-sm">
                Event reference
                <input
                  value={ref}
                  onChange={(e) => setRef(e.target.value)}
                  className="mt-1 block w-full rounded border px-2 py-2"
                />
              </label>
            )}
          </fieldset>
        )}
        <Btn
          type="submit"
          disabled={
            !code ||
            (!!inf &&
              needsSupervisor(inf) &&
              (evType === 'second_staff_report' ? !reporter : !ref.trim()))
          }
        >
          Submit
        </Btn>
        {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      </form>
    </Panel>
  )
}

function SettingsForm({ d, onDone }: { d: Detail; onDone: () => void }) {
  const [s, setS] = useState(d.settings)
  const [reason, setReason] = useState('')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)
  async function save(e: FormEvent) {
    e.preventDefault()
    try {
      const r = await put<{ changed: string[] }>(`/staff/residents/${d.resident_id}/settings`, {
        ...s,
        reason,
      })
      setMsg({
        kind: 'ok',
        text: r.changed.length ? `Saved: ${r.changed.join(', ')}` : 'No changes.',
      })
      onDone()
    } catch (err) {
      setMsg({ kind: 'err', text: errorText(err) })
    }
  }
  const sel = (label: string, key: 'language' | 'text_size' | 'reading_level', opts: string[]) => (
    <label className="block text-sm">
      {label}
      <select
        value={s[key]}
        onChange={(e) => setS({ ...s, [key]: e.target.value })}
        className="mt-1 block w-full rounded border px-2 py-2"
      >
        {opts.map((o) => (
          <option key={o}>{o}</option>
        ))}
      </select>
    </label>
  )
  return (
    <Panel title="Resident settings (staff only)" data-testid="settings-panel">
      <form onSubmit={save} className="grid gap-3 md:grid-cols-2">
        {sel('Language', 'language', ['en', 'es'])}
        {sel('Text size', 'text_size', ['normal', 'large', 'xlarge'])}
        {sel('Reading level', 'reading_level', ['simple', 'standard'])}
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={s.captions}
            onChange={(e) => setS({ ...s, captions: e.target.checked })}
          />{' '}
          Captions
        </label>
        <label className="block text-sm md:col-span-2">
          Reason for change
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="mt-1 block w-full rounded border px-2 py-2"
          />
        </label>
        <div className="md:col-span-2">
          <Btn type="submit" disabled={reason.trim().length < 3}>
            Save settings
          </Btn>
        </div>
        {msg && (
          <div className="md:col-span-2">
            <Notice kind={msg.kind}>{msg.text}</Notice>
          </div>
        )}
      </form>
    </Panel>
  )
}

export default function ResidentDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const { data: d, error, reload } = useLoad<Detail>(`/staff/residents/${id}`)
  const canRecord = user && ['officer', 'supervisor'].includes(user.role)
  const canEdit = user && ['officer', 'supervisor', 'admin'].includes(user.role)
  if (!d)
    return (
      <Page title="Resident">
        <ErrorLine error={error} />
      </Page>
    )
  return (
    <Page title={d.code}>
      <ErrorLine error={error} />
      <Panel>
        <p data-testid="resident-summary">
          Tier {d.tier.effective} (earned {d.tier.earned}, ceiling {d.tier.ceiling}) · {d.points}{' '}
          points · cell {d.cell ?? '—'} · device {d.device ?? '—'} · prior returns {d.prior_returns}
        </p>
      </Panel>
      {canRecord && <IssueSanction residentId={d.resident_id} onDone={() => void reload()} />}
      <Panel title="Sanctions">
        <Table data-testid="sanction-history">
          <thead>
            <tr>
              <Th>#</Th>
              <Th>Code</Th>
              <Th>Status</Th>
              <Th>Issued</Th>
              <Th>By</Th>
              <Th>Confirmed by</Th>
              <Th>Ends</Th>
            </tr>
          </thead>
          <tbody>
            {d.sanctions.map((s) => (
              <tr key={s.id} data-testid={`sanction-${s.id}`}>
                <Td>{s.id}</Td>
                <Td>{s.code}</Td>
                <Td>
                  <Badge tone={s.active ? 'amber' : s.status === 'pending' ? 'red' : 'gray'}>
                    {s.active ? 'active' : s.status}
                  </Badge>
                </Td>
                <Td>{fmt(s.issued_at)}</Td>
                <Td>{s.issued_by?.username ?? 'system'}</Td>
                <Td>{s.confirmed_by?.username ?? ''}</Td>
                <Td>{fmt(s.ends_at)}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Panel>
      <div className="grid gap-4 md:grid-cols-2">
        <Panel title="Points">
          <Table>
            <thead>
              <tr>
                <Th>When</Th>
                <Th>Event</Th>
                <Th>Points</Th>
              </tr>
            </thead>
            <tbody>
              {d.point_events.map((p, i) => (
                <tr key={i}>
                  <Td>{fmt(p.at)}</Td>
                  <Td>{p.kind.replace(/_/g, ' ')}</Td>
                  <Td>{p.points}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Panel>
        <Panel title="Tier history">
          <Table>
            <thead>
              <tr>
                <Th>When</Th>
                <Th>Change</Th>
                <Th>Points</Th>
              </tr>
            </thead>
            <tbody>
              {d.tier_history.map((t, i) => (
                <tr key={i}>
                  <Td>{fmt(t.at)}</Td>
                  <Td>
                    {t.from} → {t.to}
                  </Td>
                  <Td>{t.points}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Panel>
      </div>
      {canEdit && <SettingsForm d={d} onDone={() => void reload()} />}
    </Page>
  )
}
