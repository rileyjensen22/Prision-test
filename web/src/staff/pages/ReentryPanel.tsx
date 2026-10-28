import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { errorText, fmt, post, put } from '../api'
import { Badge, Btn, ErrorLine, Notice, Panel, Table, Td, Th, useLoad } from '../ui'

interface View {
  release_date: string | null
  checklist: { code: string; title: string; status: string; note?: string; at?: string }[]
  progress: { done: number; resolved: number; total: number }
}

const STATUSES = ['todo', 'in_progress', 'done', 'not_needed']

export default function ReentryPanel({
  residentId,
  canRecord,
  canSetDate,
}: {
  residentId: number
  canRecord: boolean
  canSetDate: boolean
}) {
  const { t } = useTranslation()

  const path = `/staff/residents/${residentId}/reentry`
  const { data, error, reload } = useLoad<View>(path)
  const [date, setDate] = useState('')
  const [reason, setReason] = useState('')
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  async function saveDate(clear = false) {
    try {
      await put(`/staff/residents/${residentId}/release-date`, {
        release_date: clear ? null : date,
        reason,
      })
      setMsg({ kind: 'ok', text: clear ? 'Release date cleared.' : 'Release date saved.' })
      await reload()
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  async function setStatus(code: string, status: string) {
    try {
      await post(`/staff/residents/${residentId}/reentry-items`, {
        item_code: code,
        status,
        note: notes[code] || null,
      })
      setNotes({ ...notes, [code]: '' })
      await reload()
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  return (
    <Panel title={t('staff.pages.ReentryPanel.releaseAndReentry')} data-testid="reentry-panel">
      <ErrorLine error={error} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      {data && (
        <>
          <p data-testid="release-date">
            {t('staff.msg.releaseDate', { date: data.release_date ?? t('staff.msg.notSet') })}
          </p>
          {canSetDate && (
            <div className="my-2 flex flex-wrap items-center gap-2">
              <input
                aria-label={t('staff.pages.ReentryPanel.releaseDate')}
                type="date"
                className="rounded-ctl border px-2 py-1"
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
              <input
                aria-label={t('staff.pages.ReentryPanel.reasonForTheDate')}
                placeholder={t('staff.pages.ReentryPanel.reason')}
                className="rounded-ctl border px-2 py-1"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
              <Btn disabled={!date} onClick={() => void saveDate()}>
                {t('staff.pages.ReentryPanel.saveDate')}
              </Btn>
              <Btn kind="plain" onClick={() => void saveDate(true)}>
                {t('staff.pages.ReentryPanel.clear')}
              </Btn>
            </div>
          )}
          <p className="text-sm">
            {t('staff.msg.checklistProgress', {
              done: data.progress.resolved,
              total: data.progress.total,
            })}
          </p>
          <Table>
            <thead>
              <tr>
                <Th>{t('staff.pages.ReentryPanel.item')}</Th>
                <Th>{t('staff.pages.ReentryPanel.status')}</Th>
                <Th>{t('staff.pages.ReentryPanel.lastNote')}</Th>
                {canRecord && <Th>{t('staff.pages.ReentryPanel.update')}</Th>}
              </tr>
            </thead>
            <tbody>
              {data.checklist.map((i) => (
                <tr key={i.code} data-testid={`staff-item-${i.code}`}>
                  <Td>{i.title}</Td>
                  <Td>
                    <Badge tone={i.status === 'done' ? 'green' : 'gray'}>{i.status}</Badge>
                  </Td>
                  <Td>{i.note ? `${i.note} (${fmt(i.at)})` : '—'}</Td>
                  {canRecord && (
                    <Td>
                      <input
                        aria-label={`Note for ${i.code}`}
                        placeholder={t('staff.pages.ReentryPanel.note')}
                        className="mr-2 rounded-ctl border px-2 py-1"
                        value={notes[i.code] ?? ''}
                        onChange={(e) => setNotes({ ...notes, [i.code]: e.target.value })}
                      />
                      <select
                        aria-label={`Status for ${i.code}`}
                        className="rounded-ctl border px-2 py-1"
                        value={i.status}
                        onChange={(e) => void setStatus(i.code, e.target.value)}
                      >
                        {STATUSES.map((s) => (
                          <option key={s}>{s}</option>
                        ))}
                      </select>
                    </Td>
                  )}
                </tr>
              ))}
            </tbody>
          </Table>
        </>
      )}
    </Panel>
  )
}
