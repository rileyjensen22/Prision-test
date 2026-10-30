import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'

import { api, errorText, fmt, post, put } from '../api'
import { useAuth } from '../auth'
import {
  Badge,
  Btn,
  DataTable,
  ErrorLine,
  Notice,
  Page,
  Panel,
  Table,
  Td,
  Th,
  useLoad,
} from '../ui'
import { LifecyclePanel } from './LifecyclePanel'
import ReentryPanel from './ReentryPanel'

interface Detail {
  resident_id: number
  code: string
  display_name: string
  settings: { language: string; text_size: string; reading_level: string; captions: boolean }
  prior_returns: number
  released_at: string | null
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
  const { t: tr } = useTranslation()

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
    <Panel title={tr('staff.pages.ResidentDetail.recordAnInfraction')} data-testid="issue-panel">
      <form onSubmit={submit} className="space-y-3">
        <label className="block text-sm">
          {tr('staff.pages.ResidentDetail.infraction')}
          <select
            value={code}
            onChange={(e) => setCode(e.target.value)}
            className="mt-1 block w-full rounded-ctl border px-2 py-2"
          >
            <option value="">{tr('staff.pages.ResidentDetail.choose')}</option>
            {(infractions.data ?? []).map((i) => (
              <option key={i.code} value={i.code}>
                {i.code} — {i.label}
              </option>
            ))}
          </select>
        </label>
        {inf && (
          <p className="text-sm text-ink-soft" data-testid="infraction-help">
            {tr('staff.msg.locks', {
              scope: inf.scope.replace(/_/g, ' '),
              hours: inf.duration_hours,
            })}{' '}
            {needsSupervisor(inf) ? tr('staff.msg.needsSupervisor') : tr('staff.msg.appliesNow')}
          </p>
        )}
        {inf && needsSupervisor(inf) && (
          <fieldset className="space-y-2 rounded-ctl border p-3">
            <legend className="px-1 text-sm font-medium">
              {tr('staff.pages.ResidentDetail.evidence')}
            </legend>
            <label className="mr-4 text-sm">
              <input
                type="radio"
                checked={evType === 'second_staff_report'}
                onChange={() => setEvType('second_staff_report')}
              />{' '}
              {tr('staff.msg.secondReport')}
            </label>
            <label className="text-sm">
              <input
                type="radio"
                checked={evType === 'system_event'}
                onChange={() => setEvType('system_event')}
              />{' '}
              {tr('staff.msg.systemEvent')}
            </label>
            {evType === 'second_staff_report' ? (
              <label className="block text-sm">
                {tr('staff.pages.ResidentDetail.reportedBy')}
                <select
                  value={reporter}
                  onChange={(e) => setReporter(e.target.value)}
                  className="mt-1 block w-full rounded-ctl border px-2 py-2"
                  aria-label={tr('staff.pages.ResidentDetail.reportedBy')}
                >
                  <option value="">{tr('staff.pages.ResidentDetail.chooseAColleague')}</option>
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
                {tr('staff.pages.ResidentDetail.eventReference')}
                <input
                  value={ref}
                  onChange={(e) => setRef(e.target.value)}
                  className="mt-1 block w-full rounded-ctl border px-2 py-2"
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
          {tr('staff.pages.ResidentDetail.submit')}
        </Btn>
        {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      </form>
    </Panel>
  )
}

function CommendationForm({ residentId, onDone }: { residentId: number; onDone: () => void }) {
  const [reason, setReason] = useState('')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setMsg(null)
    try {
      const r = await post<{ points: number; weekly_remaining: number }>(
        `/staff/residents/${residentId}/points`,
        { kind: 'commendation', reason },
      )
      setMsg({ kind: 'ok', text: `+${r.points} points. ${r.weekly_remaining} commendation(s) remaining this week.` })
      setReason('')
      onDone()
    } catch (err) {
      setMsg({ kind: 'err', text: errorText(err) })
    }
  }

  return (
    <Panel title="Staff Commendation" data-testid="commendation-panel">
      <form onSubmit={submit} className="space-y-3">
        <label className="block text-sm">
          Reason (required)
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Describe the commendable behavior"
            className="mt-1 block w-full rounded-ctl border px-2 py-2"
          />
        </label>
        <p className="text-sm text-ink-soft">+10 points. Max 3 commendations per officer per rolling week.</p>
        <Btn type="submit" disabled={reason.trim().length < 5}>
          Issue Commendation
        </Btn>
        {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      </form>
    </Panel>
  )
}

function MaxTierOverride({ d, onDone }: { d: Detail; onDone: () => void }) {
  const [maxTier, setMaxTier] = useState(String(d.tier.ceiling))
  const [reason, setReason] = useState('')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setMsg(null)
    try {
      await put(`/staff/residents/${d.resident_id}`, {
        max_tier_override: Number(maxTier),
        reason,
      })
      setMsg({ kind: 'ok', text: `Tier ceiling set to ${maxTier}.` })
      setReason('')
      onDone()
    } catch (err) {
      setMsg({ kind: 'err', text: errorText(err) })
    }
  }

  return (
    <Panel title="Tier Ceiling Override" data-testid="tier-override-panel">
      <p className="mb-2 text-sm text-ink-soft">
        This overrides the repeat-return formula ceiling. The resident can still earn up to this tier through points. Requires supervisor or admin role. Audit-logged.
      </p>
      <form onSubmit={submit} className="space-y-3">
        <label className="block text-sm">
          Maximum tier (1–10)
          <input
            type="number"
            min={1}
            max={10}
            value={maxTier}
            onChange={(e) => setMaxTier(e.target.value)}
            className="mt-1 block w-24 rounded-ctl border px-2 py-2"
          />
        </label>
        <label className="block text-sm">
          Reason for override
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="mt-1 block w-full rounded-ctl border px-2 py-2"
          />
        </label>
        <Btn type="submit" disabled={reason.trim().length < 5}>
          Set Ceiling
        </Btn>
        {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      </form>
    </Panel>
  )
}

function SettingsForm({ d, onDone }: { d: Detail; onDone: () => void }) {
  const { t: tr } = useTranslation()

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
        className="mt-1 block w-full rounded-ctl border px-2 py-2"
      >
        {opts.map((o) => (
          <option key={o}>{o}</option>
        ))}
      </select>
    </label>
  )
  return (
    <Panel
      title={tr('staff.pages.ResidentDetail.residentSettingsStaffOnly')}
      data-testid="settings-panel"
    >
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
          {tr('staff.msg.captions')}
        </label>
        <label className="block text-sm md:col-span-2">
          {tr('staff.pages.ResidentDetail.reasonForChange')}
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="mt-1 block w-full rounded-ctl border px-2 py-2"
          />
        </label>
        <div className="md:col-span-2">
          <Btn type="submit" disabled={reason.trim().length < 3}>
            {tr('staff.pages.ResidentDetail.saveSettings')}
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

function OutOfCell({ residentId, canEdit }: { residentId: number; canEdit: boolean }) {
  const { t: tr } = useTranslation()

  const { data, reload } = useLoad<{ day: string; minutes: number | null }[]>(
    `/staff/residents/${residentId}/out-of-cell?days=14`,
  )
  const [day, setDay] = useState(new Date().toISOString().slice(0, 10))
  const [minutes, setMinutes] = useState('')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)
  async function save(e: FormEvent) {
    e.preventDefault()
    try {
      await post('/staff/out-of-cell', { resident_id: residentId, day, minutes: Number(minutes) })
      setMsg({ kind: 'ok', text: 'Recorded.' })
      setMinutes('')
      await reload()
    } catch (err) {
      setMsg({ kind: 'err', text: errorText(err) })
    }
  }
  return (
    <Panel title={tr('staff.pages.ResidentDetail.outOfCellTime')} data-testid="ooc-panel">
      <div className="flex flex-wrap gap-1" data-testid="ooc-days">
        {(data ?? []).map((d) => (
          <span
            key={d.day}
            title={d.day}
            className={`rounded-ctl px-2 py-1 text-sm ${d.minutes === null ? 'bg-surface-2 text-ink-soft' : d.minutes < 60 ? 'bg-danger-soft text-ink' : 'bg-ok-soft text-ink'}`}
          >
            {d.day.slice(5)}: {d.minutes ?? '—'}
          </span>
        ))}
      </div>
      {canEdit && (
        <form onSubmit={save} className="mt-3 flex flex-wrap items-end gap-2">
          <label className="text-sm">
            {tr('staff.pages.ResidentDetail.day')}
            <input
              aria-label={tr('staff.pages.ResidentDetail.outOfCellDay')}
              type="date"
              value={day}
              onChange={(e) => setDay(e.target.value)}
              className="mt-1 block rounded-ctl border px-2 py-1"
            />
          </label>
          <label className="text-sm">
            {tr('staff.pages.ResidentDetail.minutesOutOfCell')}
            <input
              aria-label={tr('staff.pages.ResidentDetail.minutesOutOfCell')}
              type="number"
              min={0}
              max={1440}
              value={minutes}
              onChange={(e) => setMinutes(e.target.value)}
              className="mt-1 block w-28 rounded-ctl border px-2 py-1"
            />
          </label>
          <Btn type="submit" disabled={minutes === ''}>
            {tr('staff.pages.ResidentDetail.record')}
          </Btn>
          <span className="text-sm text-ink-soft">
            {tr('staff.pages.ResidentDetail.entriesAreNeverEdited')}
          </span>
        </form>
      )}
      {msg && (
        <div className="mt-2">
          <Notice kind={msg.kind}>{msg.text}</Notice>
        </div>
      )}
    </Panel>
  )
}

interface TimelineEvent {
  at: string
  kind: string
  detail: Record<string, unknown>
}

function Activity({ residentId }: { residentId: number }) {
  const { t: tr } = useTranslation()

  const [reason, setReason] = useState('')
  const [events, setEvents] = useState<TimelineEvent[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  async function open(e: FormEvent) {
    e.preventDefault()
    setErr(null)
    try {
      setEvents(
        await api<TimelineEvent[]>(
          `/staff/residents/${residentId}/timeline?reason=${encodeURIComponent(reason)}`,
        ),
      )
    } catch (x) {
      setErr(errorText(x))
    }
  }
  const text = (e: TimelineEvent) =>
    Object.entries(e.detail)
      .filter(([, v]) => v !== null && v !== undefined)
      .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${String(v)}`)
      .join(', ')
  return (
    <Panel
      title={tr('staff.pages.ResidentDetail.activityMetadataOnly')}
      data-testid="activity-panel"
    >
      <p className="mb-2 text-sm text-ink-soft">
        {tr('staff.pages.ResidentDetail.showsThatThingsHappened')}
      </p>
      {events === null ? (
        <form onSubmit={open} className="flex flex-wrap items-end gap-2">
          <label className="flex-1 text-sm">
            {tr('staff.pages.ResidentDetail.whyAreYouViewing')}
            <input
              aria-label={tr('staff.pages.ResidentDetail.reasonForViewingActivity')}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="mt-1 block w-full rounded-ctl border px-2 py-2"
            />
          </label>
          <Btn type="submit" disabled={reason.trim().length < 5}>
            {tr('staff.pages.ResidentDetail.viewActivity')}
          </Btn>
        </form>
      ) : (
        <DataTable
          testId="timeline"
          rows={events}
          rowKey={(e) => `${e.at}-${e.kind}-${text(e)}`}
          columns={[
            { key: 'when', header: 'When', sort: (e) => e.at, cell: (e) => fmt(e.at) },
            {
              key: 'what',
              header: 'What',
              sort: (e) => e.kind,
              text: (e) => e.kind,
              cell: (e) => e.kind,
            },
            { key: 'details', header: 'Details', text, cell: text },
          ]}
        />
      )}
      <ErrorLine error={err} />
    </Panel>
  )
}

export default function ResidentDetail() {
  const { t: tr } = useTranslation()

  const { id } = useParams()
  const { user } = useAuth()
  const { data: d, error, reload } = useLoad<Detail>(`/staff/residents/${id}`)
  const canRecord = user && ['officer', 'supervisor'].includes(user.role)
  const canEdit = user && ['officer', 'supervisor', 'admin'].includes(user.role)
  if (!d)
    return (
      <Page title={tr('staff.pages.ResidentDetail.resident')}>
        <ErrorLine error={error} />
      </Page>
    )
  return (
    <Page title={d.code}>
      <ErrorLine error={error} />
      <Panel>
        <ul data-testid="resident-summary" className="flex flex-wrap gap-x-8 gap-y-3">
          {[
            ['tier', `${d.tier.effective} (earned ${d.tier.earned}, ceiling ${d.tier.ceiling})`],
            ['points', String(d.points)],
            ['cell', d.cell ?? '—'],
            ['device', d.device ?? '—'],
            ['prior returns', String(d.prior_returns)],
          ].map(([label, value]) => (
            <li key={label}>
              <span className="text-ink-soft">{label}</span>{' '}
              <strong className="text-h3">{value}</strong>
            </li>
          ))}
        </ul>
      </Panel>
      <ReentryPanel
        residentId={d.resident_id}
        canRecord={!!canRecord || user?.role === 'admin'}
        canSetDate={!!user && ['supervisor', 'admin'].includes(user.role)}
      />
      <p>
        <Link to={`/staff/residents/${d.resident_id}/certificates`} className="underline">
          {tr('staff.pages.ResidentDetail.certificates')}
        </Link>
      </p>
      {canEdit && (
        <CommendationForm residentId={d.resident_id} onDone={() => void reload()} />
      )}
      {user && ['supervisor', 'admin'].includes(user.role) && (
        <MaxTierOverride d={d} onDone={() => void reload()} />
      )}
      {canRecord && <IssueSanction residentId={d.resident_id} onDone={() => void reload()} />}
      <Panel title={tr('staff.pages.ResidentDetail.sanctions')}>
        <DataTable
          testId="sanction-history"
          rows={d.sanctions}
          rowKey={(x) => x.id}
          rowTestId={(x) => `sanction-${x.id}`}
          columns={[
            { key: 'id', header: '#', sort: (x) => x.id, cell: (x) => x.id },
            {
              key: 'code',
              header: 'Code',
              sort: (x) => x.code,
              text: (x) => x.code,
              cell: (x) => x.code,
            },
            {
              key: 'status',
              header: 'Status',
              sort: (x) => (x.active ? 'active' : x.status),
              text: (x) => (x.active ? 'active' : x.status),
              cell: (x) => (
                <Badge tone={x.active ? 'amber' : x.status === 'pending' ? 'red' : 'gray'}>
                  {x.active ? 'active' : x.status}
                </Badge>
              ),
            },
            {
              key: 'issued',
              header: 'Issued',
              sort: (x) => x.issued_at,
              cell: (x) => fmt(x.issued_at),
            },
            {
              key: 'by',
              header: 'By',
              text: (x) => x.issued_by?.username ?? 'system',
              cell: (x) => x.issued_by?.username ?? 'system',
            },
            { key: 'conf', header: 'Confirmed by', cell: (x) => x.confirmed_by?.username ?? '' },
            {
              key: 'ends',
              header: 'Ends',
              sort: (x) => x.ends_at ?? '',
              cell: (x) => fmt(x.ends_at),
            },
          ]}
        />
      </Panel>
      <div className="grid gap-4 md:grid-cols-2">
        <Panel title={tr('staff.pages.ResidentDetail.points')}>
          <Table>
            <thead>
              <tr>
                <Th>{tr('staff.pages.ResidentDetail.when')}</Th>
                <Th>{tr('staff.pages.ResidentDetail.event')}</Th>
                <Th>{tr('staff.pages.ResidentDetail.points')}</Th>
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
        <Panel title={tr('staff.pages.ResidentDetail.tierHistory')}>
          <Table>
            <thead>
              <tr>
                <Th>{tr('staff.pages.ResidentDetail.when')}</Th>
                <Th>{tr('staff.pages.ResidentDetail.change')}</Th>
                <Th>{tr('staff.pages.ResidentDetail.points')}</Th>
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
      <OutOfCell residentId={d.resident_id} canEdit={!!canEdit} />
      {user && ['supervisor', 'admin', 'auditor'].includes(user.role) && (
        <Activity residentId={d.resident_id} />
      )}
      {user && ['supervisor', 'admin'].includes(user.role) && (
        <LifecyclePanel
          residentId={d.resident_id}
          released={Boolean(d.released_at)}
          onDone={() => void reload()}
        />
      )}
      {canEdit && <SettingsForm d={d} onDone={() => void reload()} />}
    </Page>
  )
}
