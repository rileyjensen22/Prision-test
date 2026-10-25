import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { api, errorText, fmt, getToken, post } from '../api'
import { useAuth } from '../auth'
import { Badge, Btn, ErrorLine, Notice, Page, Panel, Table, Td, Th, useLoad } from '../ui'

interface Roster {
  resident_id: number
  code: string
  cell: string | null
}
interface OutNow {
  resident_id: number
  resident: string
  unit: string
  activity: string
  since: string
  minutes: number
}
interface Report {
  day: string
  minimum: number
  blocks: {
    block_id: number
    unit: string
    kind: string
    start: string
    title: string | null
    booked: number
    attended: number
    partial: number
    missed: number
    missed_residents: string[]
  }[]
  residents: {
    resident_id: number
    resident: string
    unit: string
    scheduled_minutes: number
    actual_minutes: number
    below_minimum: boolean
    short_of_schedule: boolean
  }[]
}
interface Below {
  resident_id: number
  resident: string
  day: string
  minutes: number
  minimum: number
}

const yesterday = () => new Date(Date.now() - 86_400_000).toISOString().slice(0, 10)

export default function OutOfCell() {
  const { t } = useTranslation()

  const { user } = useAuth()
  const roster = useLoad<Roster[]>('/staff/roster')
  const out = useLoad<OutNow[]>('/staff/movement/now')
  const below = useLoad<Below[]>('/staff/out-of-cell/below-minimum')
  const [day, setDay] = useState(yesterday())
  const report = useLoad<Report>(`/staff/movement/discrepancies?day=${day}`)
  const [picked, setPicked] = useState<number[]>([])
  const [activity, setActivity] = useState('indoor')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)
  const canLog = !!user && ['officer', 'supervisor', 'admin'].includes(user.role)
  const canExport = !!user && ['supervisor', 'admin', 'auditor'].includes(user.role)
  const outIds = new Set((out.data ?? []).map((o) => o.resident_id))

  async function move(kind: 'out' | 'in', ids: number[]) {
    try {
      const body = kind === 'out' ? { resident_ids: ids, activity } : { resident_ids: ids }
      const res = await post<{ ok: boolean; code: string | null }[]>(
        `/staff/movement/${kind}`,
        body,
      )
      const failed = res.filter((r) => !r.ok)
      setMsg({
        kind: failed.length ? 'err' : 'ok',
        text: failed.length
          ? `${res.length - failed.length} done, ${failed.length} not (${[...new Set(failed.map((f) => f.code))].join(', ')}).`
          : `${res.length} resident(s) ${kind === 'out' ? 'tapped out' : 'tapped in'}.`,
      })
      setPicked([])
      await Promise.all([out.reload(), report.reload(), below.reload()])
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  async function download(format: 'csv' | 'json') {
    try {
      const res = await fetch(`/api/staff/movement/export?day=${day}&format=${format}`, {
        headers: { Authorization: `Bearer ${getToken() ?? ''}` },
      })
      if (!res.ok) throw new Error(String(res.status))
      const url = URL.createObjectURL(await res.blob())
      const a = document.createElement('a')
      a.href = url
      a.download = `out-of-cell-${day}.${format}`
      a.click()
      URL.revokeObjectURL(url)
      setMsg({ kind: 'ok', text: 'Export downloaded. It is recorded in the audit log.' })
    } catch {
      setMsg({ kind: 'err', text: 'The export could not be downloaded.' })
    }
  }
  void api

  const toggle = (id: number) =>
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]))

  return (
    <Page title={t('staff.pages.OutOfCell.outOfCell')}>
      <p className="text-sm text-ink-soft">{t('staff.pages.OutOfCell.tapResidentsOutWhen')}</p>
      <ErrorLine error={roster.error ?? out.error ?? report.error} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}

      <Panel title={t('staff.pages.OutOfCell.whoIsOutNow')}>
        {out.data?.length === 0 && (
          <p data-testid="nobody-out">{t('staff.pages.OutOfCell.nobodyIsOutOf')}</p>
        )}
        {!!out.data?.length && (
          <Table data-testid="out-now">
            <thead>
              <tr>
                <Th>{t('staff.pages.OutOfCell.resident')}</Th>
                <Th>{t('staff.pages.OutOfCell.unit')}</Th>
                <Th>{t('staff.pages.OutOfCell.for')}</Th>
                <Th>{t('staff.pages.OutOfCell.since')}</Th>
                <Th>{t('staff.pages.OutOfCell.minutes')}</Th>
                <Th></Th>
              </tr>
            </thead>
            <tbody>
              {out.data.map((o) => (
                <tr key={o.resident_id} data-testid={`out-${o.resident}`}>
                  <Td>{o.resident}</Td>
                  <Td>{o.unit}</Td>
                  <Td>{o.activity}</Td>
                  <Td>{fmt(o.since)}</Td>
                  <Td>{o.minutes}</Td>
                  <Td>
                    {canLog && (
                      <Btn kind="plain" onClick={() => void move('in', [o.resident_id])}>
                        {t('staff.pages.OutOfCell.tapIn')}
                      </Btn>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {canLog && !!out.data?.length && (
          <Btn
            kind="plain"
            onClick={() =>
              void move(
                'in',
                (out.data ?? []).map((o) => o.resident_id),
              )
            }
          >
            {t('staff.pages.OutOfCell.tapEveryoneIn')}
          </Btn>
        )}
      </Panel>

      {canLog && (
        <Panel title={t('staff.pages.OutOfCell.tapResidentsOut')}>
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <label className="text-sm">
              {t('staff.pages.OutOfCell.outFor')}
              <select
                aria-label={t('staff.pages.OutOfCell.outFor')}
                className="ml-2 rounded-ctl border px-2 py-1"
                value={activity}
                onChange={(e) => setActivity(e.target.value)}
              >
                {['indoor', 'outdoor', 'program', 'visit', 'other'].map((a) => (
                  <option key={a}>{a}</option>
                ))}
              </select>
            </label>
            <Btn disabled={picked.length === 0} onClick={() => void move('out', picked)}>
              Tap out {picked.length || ''} selected
            </Btn>
          </div>
          <ul className="grid grid-cols-2 gap-1 text-sm md:grid-cols-4" data-testid="pick-list">
            {(roster.data ?? []).map((r) => (
              <li key={r.resident_id}>
                <label className={outIds.has(r.resident_id) ? 'text-ink-soft' : ''}>
                  <input
                    type="checkbox"
                    aria-label={`Select ${r.code}`}
                    disabled={outIds.has(r.resident_id)}
                    checked={picked.includes(r.resident_id)}
                    onChange={() => toggle(r.resident_id)}
                  />{' '}
                  {r.code}
                </label>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      <Panel title={t('staff.pages.OutOfCell.belowTheMinimum')}>
        {below.data?.length === 0 && (
          <p data-testid="none-below">{t('staff.pages.OutOfCell.nobodyWasUnderThe')}</p>
        )}
        {!!below.data?.length && (
          <Table data-testid="below-minimum">
            <thead>
              <tr>
                <Th>{t('staff.pages.OutOfCell.resident')}</Th>
                <Th>{t('staff.pages.OutOfCell.day')}</Th>
                <Th>{t('staff.pages.OutOfCell.minutesOut')}</Th>
                <Th>{t('staff.pages.OutOfCell.minimum')}</Th>
              </tr>
            </thead>
            <tbody>
              {below.data.map((b) => (
                <tr key={b.resident_id} data-testid={`below-${b.resident}`}>
                  <Td>{b.resident}</Td>
                  <Td>{b.day}</Td>
                  <Td>{b.minutes}</Td>
                  <Td>{b.minimum}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>

      <Panel title={t('staff.pages.OutOfCell.scheduledVersusActual')}>
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <label className="text-sm">
            {t('staff.pages.OutOfCell.day')}
            <input
              aria-label={t('staff.pages.OutOfCell.reportDay')}
              type="date"
              className="ml-2 rounded-ctl border px-2 py-1"
              value={day}
              onChange={(e) => setDay(e.target.value)}
            />
          </label>
          {canExport && (
            <>
              <Btn kind="plain" onClick={() => void download('csv')}>
                {t('staff.pages.OutOfCell.exportCsv')}
              </Btn>
              <Btn kind="plain" onClick={() => void download('json')}>
                {t('staff.pages.OutOfCell.exportJson')}
              </Btn>
            </>
          )}
        </div>
        <Table data-testid="discrepancy-blocks">
          <thead>
            <tr>
              <Th>{t('staff.pages.OutOfCell.block')}</Th>
              <Th>{t('staff.pages.OutOfCell.signedUp')}</Th>
              <Th>{t('staff.pages.OutOfCell.attended')}</Th>
              <Th>{t('staff.pages.OutOfCell.partOfIt')}</Th>
              <Th>{t('staff.pages.OutOfCell.didNotComeOut')}</Th>
            </tr>
          </thead>
          <tbody>
            {(report.data?.blocks ?? [])
              .filter((b) => b.booked > 0)
              .map((b) => (
                <tr key={b.block_id}>
                  <Td>
                    {b.unit} {b.start} {b.title ?? b.kind}
                  </Td>
                  <Td>{b.booked}</Td>
                  <Td>{b.attended}</Td>
                  <Td>{b.partial}</Td>
                  <Td>{b.missed_residents.join(', ') || '—'}</Td>
                </tr>
              ))}
          </tbody>
        </Table>
        <Table data-testid="discrepancy-residents">
          <thead>
            <tr>
              <Th>{t('staff.pages.OutOfCell.resident')}</Th>
              <Th>{t('staff.pages.OutOfCell.unit')}</Th>
              <Th>{t('staff.pages.OutOfCell.bookedMinutes')}</Th>
              <Th>{t('staff.pages.OutOfCell.minutesOut')}</Th>
              <Th>{t('staff.pages.OutOfCell.notes')}</Th>
            </tr>
          </thead>
          <tbody>
            {(report.data?.residents ?? []).map((r) => (
              <tr key={r.resident_id} data-testid={`day-${r.resident}`}>
                <Td>{r.resident}</Td>
                <Td>{r.unit}</Td>
                <Td>{r.scheduled_minutes}</Td>
                <Td>{r.actual_minutes}</Td>
                <Td>
                  {r.below_minimum && (
                    <Badge tone="red">{t('staff.pages.OutOfCell.belowMinimum')}</Badge>
                  )}{' '}
                  {r.short_of_schedule && (
                    <Badge tone="amber">{t('staff.pages.OutOfCell.shortOfSchedule')}</Badge>
                  )}
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Panel>
    </Page>
  )
}
