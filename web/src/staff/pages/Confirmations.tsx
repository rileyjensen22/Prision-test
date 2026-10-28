import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { errorText, fmt, post } from '../api'
import { useAuth } from '../auth'
import { Badge, Btn, DataTable, ErrorLine, Notice, Page, useLoad } from '../ui'
import type { Column } from '../ui'

interface Item {
  id: number
  resident_code: string
  infraction_code: string
  label: string
  severity: string
  duration_hours: number
  issued_at: string
  why_pending: string
  can_confirm: boolean
  issued_by: { id: number; username: string } | null
  evidence: { type: string | null; reporter: { username: string } | null; ref: string | null }
}

export default function Confirmations() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const { data, error, reload } = useLoad<Item[]>('/staff/confirmations')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)
  const [rejecting, setRejecting] = useState<number | null>(null)
  const [note, setNote] = useState('')
  const isSupervisor = user?.role === 'supervisor'

  async function act(fn: () => Promise<unknown>, ok: string) {
    setMsg(null)
    try {
      await fn()
      setMsg({ kind: 'ok', text: ok })
      setRejecting(null)
      setNote('')
      await reload()
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  const evidenceText = (q: Item) =>
    q.evidence.type === 'second_staff_report'
      ? t('staff.confirm.evidenceReport', { name: q.evidence.reporter?.username ?? '?' })
      : q.evidence.type === 'system_event'
        ? t('staff.confirm.evidenceSystem', { ref: q.evidence.ref ?? '' })
        : t('staff.confirm.evidenceNone')

  const columns: Column<Item>[] = [
    {
      key: 'resident',
      header: t('staff.confirm.resident'),
      sort: (q) => q.resident_code,
      text: (q) => q.resident_code,
      cell: (q) => <strong>{q.resident_code}</strong>,
    },
    {
      key: 'infraction',
      header: t('staff.confirm.infraction'),
      sort: (q) => q.infraction_code,
      text: (q) => `${q.infraction_code} ${q.label}`,
      cell: (q) => (
        <>
          {q.infraction_code}{' '}
          <Badge tone={q.severity === 'major' ? 'red' : 'gray'}>{q.severity}</Badge>
          <div className="text-ink-soft">
            {q.label}, {q.duration_hours}h · {fmt(q.issued_at)}
          </div>
        </>
      ),
    },
    {
      key: 'by',
      header: t('staff.confirm.recordedBy'),
      sort: (q) => q.issued_by?.username ?? '',
      text: (q) => q.issued_by?.username ?? '',
      cell: (q) => q.issued_by?.username ?? t('staff.common.system'),
    },
    {
      key: 'evidence',
      header: t('staff.confirm.evidence'),
      text: evidenceText,
      cell: evidenceText,
    },
    {
      key: 'why',
      header: t('staff.confirm.why'),
      text: (q) => q.why_pending,
      cell: (q) => q.why_pending,
    },
    {
      key: 'action',
      header: t('staff.confirm.action'),
      cell: (q) =>
        !isSupervisor ? (
          <span className="text-ink-soft">{t('staff.common.supervisorsOnly')}</span>
        ) : !q.can_confirm ? (
          <span data-testid="own-sanction" className="text-ink-soft">
            {t('staff.confirm.own')}
          </span>
        ) : rejecting === q.id ? (
          <span className="flex flex-wrap gap-2">
            <input
              aria-label={t('staff.confirm.rejectReason')}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <Btn
              kind="danger"
              disabled={!note.trim()}
              onClick={() =>
                void act(
                  () => post(`/staff/sanctions/${q.id}/reject`, { note }),
                  t('staff.confirm.okRejected'),
                )
              }
            >
              {t('staff.confirm.reject')}
            </Btn>
            <Btn kind="plain" onClick={() => setRejecting(null)}>
              {t('staff.common.cancel')}
            </Btn>
          </span>
        ) : (
          <span className="flex gap-2">
            <Btn
              onClick={() =>
                void act(
                  () => post(`/staff/sanctions/${q.id}/confirm`),
                  t('staff.confirm.okConfirmed'),
                )
              }
            >
              {t('staff.confirm.confirm')}
            </Btn>
            <Btn kind="plain" onClick={() => setRejecting(q.id)}>
              {t('staff.confirm.rejectAsk')}
            </Btn>
          </span>
        ),
    },
  ]

  return (
    <Page title={t('staff.confirm.title')}>
      <p className="text-ink-soft">{t('staff.confirm.intro')}</p>
      <ErrorLine error={error} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      <DataTable
        columns={columns}
        rows={data ?? []}
        rowKey={(q) => q.id}
        testId="confirmation-queue"
        rowTestId={(q) => `pending-${q.id}`}
        empty={
          <p className="rounded-card border border-line bg-surface p-4">
            {t('staff.confirm.empty')}
          </p>
        }
      />
    </Page>
  )
}
