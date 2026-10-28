import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { errorText, fmt, post } from '../api'
import { useAuth } from '../auth'
import { Badge, Btn, DataTable, ErrorLine, Notice, Panel, useLoad } from '../ui'
import type { Column } from '../ui'

interface Call {
  call_id: number
  resident: string
  contact_type: string
  at: string
  duration_seconds: number | null
  status: string
  recording_purged: boolean
}

/** Metadata of monitored phone calls. Opening a recording needs a reason; attorney calls never appear. */
export function MonitoredCalls() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const canOpen = !!user && ['supervisor', 'admin'].includes(user.role)
  const { data, error } = useLoad<Call[]>('/staff/monitoring/calls')
  const [reason, setReason] = useState('')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  async function open(c: Call) {
    setMsg(null)
    try {
      const r = await post<{ call_id: number; bytes: number }>(
        `/staff/monitoring/calls/${c.call_id}/review`,
        { reason },
      )
      setMsg({
        kind: 'ok',
        text: `${t('staff.callReview.opened', { id: r.call_id })} ${t('staff.callReview.bytes', { bytes: r.bytes })}`,
      })
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  const columns: Column<Call>[] = [
    { key: 'when', header: t('staff.callReview.when'), sort: (c) => c.at, cell: (c) => fmt(c.at) },
    {
      key: 'resident',
      header: t('staff.callReview.resident'),
      sort: (c) => c.resident,
      text: (c) => c.resident,
      cell: (c) => c.resident,
    },
    {
      key: 'contact',
      header: t('staff.callReview.contact'),
      sort: (c) => c.contact_type,
      text: (c) => c.contact_type,
      cell: (c) => c.contact_type,
    },
    {
      key: 'length',
      header: t('staff.callReview.length'),
      sort: (c) => c.duration_seconds ?? 0,
      cell: (c) => t('staff.callReview.seconds', { n: c.duration_seconds ?? 0 }),
    },
    {
      key: 'status',
      header: t('staff.callReview.status'),
      text: (c) => c.status,
      cell: (c) => c.status,
    },
    {
      key: 'open',
      header: '',
      cell: (c) =>
        c.recording_purged ? (
          <Badge>{t('staff.callReview.purged')}</Badge>
        ) : canOpen ? (
          <Btn kind="plain" disabled={reason.trim().length < 5} onClick={() => void open(c)}>
            {t('staff.callReview.open')}
          </Btn>
        ) : null,
    },
  ]

  return (
    <Panel title={t('staff.callReview.title')} data-testid="monitored-calls">
      <p className="mb-3 text-ink-soft">{t('staff.callReview.intro')}</p>
      <ErrorLine error={error} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      {canOpen && (
        <label className="mb-3 block">
          {t('staff.callReview.reason')}
          <input
            value={reason}
            placeholder={t('staff.callReview.reasonHint')}
            onChange={(e) => setReason(e.target.value)}
            className="mt-1 block w-full max-w-xl"
          />
        </label>
      )}
      <DataTable
        columns={columns}
        rows={data ?? []}
        rowKey={(c) => c.call_id}
        rowTestId={(c) => `call-${c.call_id}`}
        empty={<p data-testid="no-calls">{t('staff.callReview.empty')}</p>}
      />
      {msg?.kind === 'ok' && <p className="mt-2 text-ink-soft">{t('staff.callReview.logged')}</p>}
    </Panel>
  )
}
