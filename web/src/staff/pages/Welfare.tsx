import { useState } from 'react'
import { useTranslation } from 'react-i18next'
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
  const { t } = useTranslation()

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
    <Page title={t('staff.pages.Welfare.welfare')}>
      <p className="text-sm text-ink-soft">{t('staff.pages.Welfare.eachResidentIsCompared')}</p>
      <ErrorLine error={error} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      {data?.length === 0 && (
        <Panel>
          <p data-testid="welfare-clear">{t('staff.pages.Welfare.noWelfareFlagsRight')}</p>
        </Panel>
      )}
      {(data ?? []).map((r) => (
        <Panel key={r.resident_id} data-testid={`welfare-${r.code}`}>
          <h2 className="mb-2 text-h3 font-semibold">
            <Link className="text-primary underline" to={`/staff/residents/${r.resident_id}`}>
              {r.code}
            </Link>
          </h2>
          <ul className="space-y-3">
            {r.flags.map((f) => (
              <li key={f.type} data-testid={`flag-${f.type}`}>
                <Badge tone={f.severity === 'attention' ? 'amber' : 'gray'}>{f.severity}</Badge>{' '}
                {f.escalated && (
                  <Badge tone="red" data-testid="escalated">
                    {t('staff.pages.Welfare.escalatedToASupervisor')}
                  </Badge>
                )}{' '}
                <strong>{f.message}</strong>
                <div className="text-sm text-ink-soft">{describe(f)}</div>
                {f.escalated && !canHandleEscalated && (
                  <p className="mt-1 text-sm text-ink-soft">
                    {t('staff.pages.Welfare.aSupervisorMustHandle')}
                  </p>
                )}
                {canAck &&
                  (f.escalated ? canHandleEscalated : true) &&
                  (open === `${r.code}:${f.type}` ? (
                    <div className="mt-2 flex flex-wrap gap-2">
                      <select
                        aria-label={t('staff.pages.Welfare.actionTaken')}
                        value={action}
                        onChange={(e) => setAction(e.target.value)}
                        className="rounded-ctl border px-2 py-1"
                      >
                        <option value="checked_in">
                          {t('staff.pages.Welfare.checkedInWithThe')}
                        </option>
                        <option value="referred_medical">
                          {t('staff.pages.Welfare.referredToMedical')}
                        </option>
                        <option value="referred_mental_health">
                          {t('staff.pages.Welfare.referredToMentalHealth')}
                        </option>
                        <option value="adjusted_schedule">
                          {t('staff.pages.Welfare.adjustedTheirSchedule')}
                        </option>
                        <option value="no_concern">
                          {t('staff.pages.Welfare.noConcernAfterLooking')}
                        </option>
                      </select>
                      <input
                        aria-label={t('staff.pages.Welfare.whatWasDone')}
                        placeholder={t('staff.pages.Welfare.whatWasDone2')}
                        value={note}
                        onChange={(e) => setNote(e.target.value)}
                        className="min-w-64 rounded-ctl border px-2 py-1"
                      />
                      <Btn disabled={note.trim().length < 3} onClick={() => void ack(r, f)}>
                        {t('staff.pages.Welfare.recordCheckIn')}
                      </Btn>
                      <Btn kind="plain" onClick={() => setOpen(null)}>
                        {t('staff.pages.Welfare.cancel')}
                      </Btn>
                    </div>
                  ) : (
                    <Btn kind="plain" onClick={() => setOpen(`${r.code}:${f.type}`)}>
                      {t('staff.pages.Welfare.iCheckedIn')}
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
