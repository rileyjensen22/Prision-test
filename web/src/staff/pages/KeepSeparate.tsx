import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { errorText, fmt, post } from '../api'
import { useAuth } from '../auth'
import { Btn, DataTable, ErrorLine, Notice, Page, Panel, useLoad } from '../ui'
import type { Column } from '../ui'

interface Entry {
  id: number
  a: string
  b: string
  reason: string
  added_at: string
  ended_at: string | null
}

export default function KeepSeparate() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const canEdit = user?.role === 'supervisor' || user?.role === 'admin'
  const [showEnded, setShowEnded] = useState(false)
  const { data, error, reload } = useLoad<Entry[]>(
    `/staff/keep-separate?include_ended=${showEnded}`,
  )
  const [a, setA] = useState('')
  const [b, setB] = useState('')
  const [reason, setReason] = useState('')
  const [ending, setEnding] = useState<number | null>(null)
  const [endReason, setEndReason] = useState('')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  async function act(fn: () => Promise<unknown>, ok: string) {
    setMsg(null)
    try {
      await fn()
      setMsg({ kind: 'ok', text: ok })
      setEnding(null)
      setEndReason('')
      await reload()
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  const columns: Column<Entry>[] = [
    {
      key: 'a',
      header: t('staff.keepSeparate.a'),
      sort: (e) => e.a,
      text: (e) => e.a,
      cell: (e) => <strong>{e.a}</strong>,
    },
    {
      key: 'b',
      header: t('staff.keepSeparate.b'),
      sort: (e) => e.b,
      text: (e) => e.b,
      cell: (e) => <strong>{e.b}</strong>,
    },
    {
      key: 'reason',
      header: t('staff.keepSeparate.reason'),
      text: (e) => e.reason,
      cell: (e) => e.reason,
    },
    {
      key: 'added',
      header: t('staff.keepSeparate.added'),
      sort: (e) => e.added_at,
      cell: (e) => fmt(e.added_at),
    },
    {
      key: 'action',
      header: t('staff.keepSeparate.action'),
      cell: (e) =>
        e.ended_at ? (
          <span className="text-ink-soft">
            {t('staff.keepSeparate.ended')} {fmt(e.ended_at)}
          </span>
        ) : !canEdit ? null : ending === e.id ? (
          <span className="flex flex-wrap gap-2">
            <input
              aria-label={t('staff.keepSeparate.endReason')}
              value={endReason}
              onChange={(x) => setEndReason(x.target.value)}
            />
            <Btn
              disabled={endReason.trim().length < 3}
              onClick={() =>
                void act(
                  () => post(`/staff/keep-separate/${e.id}/end`, { reason: endReason }),
                  t('staff.keepSeparate.okEnded'),
                )
              }
            >
              {t('staff.keepSeparate.confirmEnd')}
            </Btn>
            <Btn kind="plain" onClick={() => setEnding(null)}>
              {t('staff.keepSeparate.cancel')}
            </Btn>
          </span>
        ) : (
          <Btn kind="plain" onClick={() => setEnding(e.id)}>
            {t('staff.keepSeparate.endEntry')}
          </Btn>
        ),
    },
  ]

  return (
    <Page title={t('staff.keepSeparate.title')}>
      <p className="text-ink-soft">{t('staff.keepSeparate.intro')}</p>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={showEnded}
          onChange={(e) => setShowEnded(e.target.checked)}
        />
        {t('staff.keepSeparate.showEnded')}
      </label>
      <ErrorLine error={error} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      <DataTable
        columns={columns}
        rows={data ?? []}
        rowKey={(e) => e.id}
        testId="keep-separate"
        rowTestId={(e) => `separate-${e.id}`}
        empty={
          <p className="rounded-card border border-line bg-surface p-4">
            {t('staff.keepSeparate.empty')}
          </p>
        }
      />
      {canEdit && (
        <Panel title={t('staff.keepSeparate.addTitle')} data-testid="separate-form">
          <form
            className="flex flex-wrap items-end gap-3"
            onSubmit={(e) => {
              e.preventDefault()
              void act(
                () => post('/staff/keep-separate', { resident_code: a, other_code: b, reason }),
                t('staff.keepSeparate.okAdded'),
              ).then(() => {
                setA('')
                setB('')
                setReason('')
              })
            }}
          >
            <label className="block">
              {t('staff.keepSeparate.residentCode')}
              <input value={a} onChange={(e) => setA(e.target.value)} className="mt-1 block" />
            </label>
            <label className="block">
              {t('staff.keepSeparate.otherCode')}
              <input value={b} onChange={(e) => setB(e.target.value)} className="mt-1 block" />
            </label>
            <label className="block min-w-64 flex-1">
              {t('staff.keepSeparate.reason')}
              <input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="mt-1 block w-full"
              />
            </label>
            <Btn type="submit" disabled={!a || !b || reason.trim().length < 3}>
              {t('staff.keepSeparate.addButton')}
            </Btn>
          </form>
        </Panel>
      )}
    </Page>
  )
}
