import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { errorText, fmt, post } from '../api'
import { useAuth } from '../auth'
import { Badge, Btn, DataTable, ErrorLine, Notice, Page, useLoad } from '../ui'
import type { Column } from '../ui'

interface Item {
  appeal_id: number
  sanction_id: number
  resident_code: string
  infraction_code: string
  status: string
  filed_at: string
  due_at: string | null
  overdue: boolean
  issued_by: { username: string } | null
  reviewer: { username: string } | null
  outcome_note: string | null
  can_review: boolean
}

export default function Appeals() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const [closed, setClosed] = useState(false)
  const { data, error, reload } = useLoad<Item[]>(`/staff/appeals?include_closed=${closed}`)
  const [open, setOpen] = useState<number | null>(null)
  const [outcome, setOutcome] = useState<'upheld' | 'overturned'>('upheld')
  const [note, setNote] = useState('')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  async function review(id: number) {
    try {
      await post(`/staff/appeals/${id}/review`, { outcome, note })
      setMsg({
        kind: 'ok',
        text:
          outcome === 'overturned' ? t('staff.appeals.okOverturned') : t('staff.appeals.okUpheld'),
      })
      setOpen(null)
      setNote('')
      await reload()
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  const columns: Column<Item>[] = [
    {
      key: 'resident',
      header: t('staff.appeals.resident'),
      sort: (a) => a.resident_code,
      text: (a) => a.resident_code,
      cell: (a) => <strong>{a.resident_code}</strong>,
    },
    {
      key: 'infraction',
      header: t('staff.appeals.infraction'),
      sort: (a) => a.infraction_code,
      text: (a) => a.infraction_code,
      cell: (a) => a.infraction_code,
    },
    {
      key: 'by',
      header: t('staff.appeals.recordedBy'),
      sort: (a) => a.issued_by?.username ?? '',
      text: (a) => a.issued_by?.username ?? '',
      cell: (a) => a.issued_by?.username ?? t('staff.common.system'),
    },
    {
      key: 'filed',
      header: t('staff.appeals.filed'),
      sort: (a) => a.filed_at,
      cell: (a) => fmt(a.filed_at),
    },
    {
      key: 'due',
      header: t('staff.appeals.due'),
      sort: (a) => a.due_at ?? '',
      cell: (a) => (
        <>
          {fmt(a.due_at)} {a.overdue && <Badge tone="red">{t('staff.appeals.overdue')}</Badge>}
        </>
      ),
    },
    {
      key: 'status',
      header: t('staff.appeals.status'),
      sort: (a) => a.status,
      text: (a) => `${a.status} ${a.outcome_note ?? ''}`,
      cell: (a) => (
        <>
          {a.reviewer
            ? t('staff.appeals.statusBy', { status: a.status, name: a.reviewer.username })
            : a.status}
          {a.outcome_note && <div className="text-ink-soft">{a.outcome_note}</div>}
        </>
      ),
    },
    {
      key: 'action',
      header: t('staff.appeals.action'),
      cell: (a) =>
        a.status !== 'open' ? (
          ''
        ) : user?.role !== 'supervisor' ? (
          <span className="text-ink-soft">{t('staff.common.supervisorsOnly')}</span>
        ) : !a.can_review ? (
          <span data-testid="own-appeal" className="text-ink-soft">
            {t('staff.appeals.own')}
          </span>
        ) : open === a.appeal_id ? (
          <span className="flex flex-wrap gap-2">
            <select
              aria-label={t('staff.appeals.outcome')}
              value={outcome}
              onChange={(e) => setOutcome(e.target.value as 'upheld' | 'overturned')}
            >
              <option value="upheld">{t('staff.appeals.uphold')}</option>
              <option value="overturned">{t('staff.appeals.overturn')}</option>
            </select>
            <input
              aria-label={t('staff.appeals.note')}
              placeholder={t('staff.appeals.reason')}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <Btn disabled={!note.trim()} onClick={() => void review(a.appeal_id)}>
              {t('staff.appeals.submit')}
            </Btn>
            <Btn kind="plain" onClick={() => setOpen(null)}>
              {t('staff.common.cancel')}
            </Btn>
          </span>
        ) : (
          <Btn onClick={() => setOpen(a.appeal_id)}>{t('staff.appeals.review')}</Btn>
        ),
    },
  ]

  return (
    <Page title={t('staff.appeals.title')}>
      <p className="text-ink-soft">{t('staff.appeals.intro')}</p>
      <label className="flex items-center gap-2">
        <input type="checkbox" checked={closed} onChange={(e) => setClosed(e.target.checked)} />
        {t('staff.appeals.showDecided')}
      </label>
      <ErrorLine error={error} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      <DataTable
        columns={columns}
        rows={data ?? []}
        rowKey={(a) => a.appeal_id}
        testId="appeal-queue"
        rowTestId={(a) => `appeal-${a.appeal_id}`}
        empty={
          <p className="rounded-card border border-line bg-surface p-4">
            {t('staff.appeals.empty')}
          </p>
        }
      />
    </Page>
  )
}
