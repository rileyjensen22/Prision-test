import { useState } from 'react'
import { useTranslation } from 'react-i18next'

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
  const { t } = useTranslation()

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
    <Page title={t('staff.pages.Schedule.unitSchedule')}>
      <p className="text-sm text-ink-soft">{t('staff.pages.Schedule.eachUnitHasIts')}</p>
      <ErrorLine error={units.error ?? view.error} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      <Panel>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm">
            {t('staff.pages.Schedule.unit')}
            <select
              aria-label={t('staff.pages.Schedule.unit')}
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
            {t('staff.pages.Schedule.day')}
            <input
              aria-label={t('staff.pages.Schedule.day')}
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
              {t('staff.pages.Schedule.makeTheNextWeek')}
            </Btn>
          )}
        </div>
      </Panel>
      <Panel title={`Unit ${unit}, ${day}`}>
        <Table data-testid="schedule-blocks">
          <thead>
            <tr>
              <Th>{t('staff.pages.Schedule.start')}</Th>
              <Th>{t('staff.pages.Schedule.what')}</Th>
              <Th>{t('staff.pages.Schedule.length')}</Th>
              <Th>{t('staff.pages.Schedule.signedUp')}</Th>
              <Th>{t('staff.pages.Schedule.whoCanSignUp')}</Th>
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
                  {b.status === 'cancelled' && (
                    <Badge tone="red">{t('staff.pages.Schedule.cancelled')}</Badge>
                  )}
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
                      {t('staff.pages.Schedule.cancel')}
                    </Btn>
                  )}
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
        {canEdit && (
          <label className="mt-3 block text-sm">
            {t('staff.pages.Schedule.reasonForCancelling')}
            <input
              aria-label={t('staff.pages.Schedule.reasonForCancelling')}
              className={`${field} ml-2 w-72`}
              value={cancelReason}
              onChange={(e) => setCancelReason(e.target.value)}
            />
          </label>
        )}
      </Panel>
      {canEdit && (
        <Panel title={t('staff.pages.Schedule.addABlock')}>
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-sm">
              {t('staff.pages.Schedule.kind')}
              <select
                aria-label={t('staff.pages.Schedule.kind')}
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
              {t('staff.pages.Schedule.start')}
              <input
                aria-label={t('staff.pages.Schedule.startTime')}
                className={`${field} ml-2 w-20`}
                value={form.start}
                onChange={(e) => setForm({ ...form, start: e.target.value })}
              />
            </label>
            <label className="text-sm">
              {t('staff.pages.Schedule.minutes')}
              <input
                aria-label={t('staff.pages.Schedule.minutes')}
                type="number"
                className={`${field} ml-2 w-20`}
                value={form.minutes}
                onChange={(e) => setForm({ ...form, minutes: Number(e.target.value) })}
              />
            </label>
            <label className="text-sm">
              {t('staff.pages.Schedule.capacity')}
              <input
                aria-label={t('staff.pages.Schedule.capacity')}
                type="number"
                className={`${field} ml-2 w-20`}
                value={form.capacity}
                onChange={(e) => setForm({ ...form, capacity: Number(e.target.value) })}
              />
            </label>
            <label className="text-sm">
              {t('staff.pages.Schedule.title')}
              <input
                aria-label={t('staff.pages.Schedule.title')}
                className={`${field} ml-2 w-48`}
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
              />
            </label>
            <label className="text-sm">
              {t('staff.pages.Schedule.reason')}
              <input
                aria-label={t('staff.pages.Schedule.reason')}
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
              {t('staff.pages.Schedule.addBlock')}
            </Btn>
          </div>
        </Panel>
      )}
    </Page>
  )
}
