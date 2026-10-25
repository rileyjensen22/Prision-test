import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { api, errorText, fmt, post } from '../api'
import { useAuth } from '../auth'
import { Btn, ErrorLine, Notice, Page, Panel, Table, Td, Th, useLoad } from '../ui'

interface Entry {
  seq: number
  ts: string
  actor_id: number | null
  actor_role: string
  action: string
  target_type: string
  target_id: string
  reason_code: string | null
  ref_seq: number | null
  payload: Record<string, unknown>
  hash: string
}

export default function AuditLog() {
  const { t } = useTranslation()

  const { user } = useAuth()
  const { data, error, reload } = useLoad<Entry[]>('/audit?limit=500')
  const [verify, setVerify] = useState<string | null>(null)
  const [fixing, setFixing] = useState<number | null>(null)
  const [reasonCode, setReasonCode] = useState('')
  const [note, setNote] = useState('')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  async function check() {
    try {
      const r = await api<{
        ok: boolean
        entries: number
        first_bad_seq: number | null
        problem: string | null
      }>('/audit/verify')
      setVerify(
        r.ok
          ? `Chain verified: ${r.entries} entries, no gaps or changes.`
          : `PROBLEM at entry ${r.first_bad_seq}: ${r.problem}`,
      )
    } catch (e) {
      setVerify(errorText(e))
    }
  }

  async function correct(seq: number) {
    try {
      await post('/audit/corrections', { ref_seq: seq, reason_code: reasonCode, note })
      setMsg({
        kind: 'ok',
        text: `Correction added for entry ${seq}. The original stays in the log.`,
      })
      setFixing(null)
      setReasonCode('')
      setNote('')
      await reload()
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  return (
    <Page title={t('staff.pages.AuditLog.auditLog')}>
      <p className="text-sm text-ink-soft">{t('staff.pages.AuditLog.appendOnlyAndHash')}</p>
      <div className="flex items-center gap-3">
        <Btn onClick={() => void check()}>{t('staff.pages.AuditLog.verifyChain')}</Btn>
        {verify && (
          <span role="status" data-testid="verify-result">
            {verify}
          </span>
        )}
      </div>
      <ErrorLine error={error} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      <Panel>
        <Table data-testid="audit-table">
          <thead>
            <tr>
              <Th>#</Th>
              <Th>{t('staff.pages.AuditLog.when')}</Th>
              <Th>{t('staff.pages.AuditLog.who')}</Th>
              <Th>{t('staff.pages.AuditLog.action')}</Th>
              <Th>{t('staff.pages.AuditLog.target')}</Th>
              <Th>{t('staff.pages.AuditLog.reason')}</Th>
              <Th>{t('staff.pages.AuditLog.refersTo')}</Th>
              <Th></Th>
            </tr>
          </thead>
          <tbody>
            {(data ?? [])
              .slice()
              .reverse()
              .map((e) => (
                <tr key={e.seq} data-testid={`audit-${e.seq}`}>
                  <Td>{e.seq}</Td>
                  <Td>{fmt(e.ts)}</Td>
                  <Td>
                    {e.actor_role}
                    {e.actor_id ? ` #${e.actor_id}` : ''}
                  </Td>
                  <Td>{e.action.replace(/_/g, ' ')}</Td>
                  <Td>
                    {e.target_type} {e.target_id}
                  </Td>
                  <Td>{e.reason_code ?? ''}</Td>
                  <Td>{e.ref_seq ?? ''}</Td>
                  <Td>
                    {user?.role === 'admin' &&
                      (fixing === e.seq ? (
                        <span className="flex flex-wrap gap-2">
                          <input
                            aria-label={t('staff.pages.AuditLog.correctionReasonCode')}
                            placeholder={t('staff.pages.AuditLog.reasonCode')}
                            value={reasonCode}
                            onChange={(ev) => setReasonCode(ev.target.value)}
                            className="w-32 rounded-ctl border px-2 py-1"
                          />
                          <input
                            aria-label={t('staff.pages.AuditLog.correctionNote')}
                            placeholder={t('staff.pages.AuditLog.whatIsWrong')}
                            value={note}
                            onChange={(ev) => setNote(ev.target.value)}
                            className="rounded-ctl border px-2 py-1"
                          />
                          <Btn
                            disabled={!reasonCode.trim() || !note.trim()}
                            onClick={() => void correct(e.seq)}
                          >
                            {t('staff.pages.AuditLog.addCorrection')}
                          </Btn>
                        </span>
                      ) : (
                        <Btn kind="plain" onClick={() => setFixing(e.seq)}>
                          {t('staff.pages.AuditLog.correct')}
                        </Btn>
                      ))}
                  </Td>
                </tr>
              ))}
          </tbody>
        </Table>
      </Panel>
    </Page>
  )
}
