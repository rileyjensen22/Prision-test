import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { errorText, fmt, post } from '../api'
import { useAuth } from '../auth'
import { Badge, Btn, ErrorLine, Notice, Page, Panel, Table, Td, Th, useLoad } from '../ui'

interface Request {
  id: number
  resident_id: number
  name: string
  type: string
  phone: string
  requested_at: string | null
  verification: string
}

const VERIFY: Record<string, { text: string; tone: 'green' | 'amber' | 'gray' }> = {
  stub_verified: { text: 'Number checked (stub)', tone: 'green' },
  stub_unverified: { text: 'Number not checked (stub)', tone: 'amber' },
  stub_needs_bar_check: { text: 'Bar number check needed (stub)', tone: 'amber' },
}

export default function ContactRequests() {
  const { t } = useTranslation()

  const { user } = useAuth()
  const { data, error, reload } = useLoad<Request[]>('/staff/contact-requests')
  const [note, setNote] = useState<Record<number, string>>({})
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  async function review(r: Request, approve: boolean) {
    try {
      await post(`/staff/contact-requests/${r.id}/review`, { approve, note: note[r.id] ?? '' })
      setMsg({ kind: 'ok', text: approve ? 'Approved.' : 'Refused.' })
      await reload()
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  const canReview = (r: Request) =>
    !!user && (r.type !== 'attorney' || ['supervisor', 'admin'].includes(user.role))

  return (
    <Page title={t('staff.pages.ContactRequests.contactRequests')}>
      <p className="text-sm text-ink-soft">{t('staff.pages.ContactRequests.residentsAskToAdd')}</p>
      <ErrorLine error={error} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      <Panel>
        {data?.length === 0 && (
          <p data-testid="no-contact-requests">
            {t('staff.pages.ContactRequests.noRequestsAreWaiting')}
          </p>
        )}
        {!!data?.length && (
          <Table data-testid="contact-requests">
            <thead>
              <tr>
                <Th>{t('staff.pages.ContactRequests.resident')}</Th>
                <Th>{t('staff.pages.ContactRequests.name')}</Th>
                <Th>{t('staff.pages.ContactRequests.type')}</Th>
                <Th>{t('staff.pages.ContactRequests.number')}</Th>
                <Th>{t('staff.pages.ContactRequests.asked')}</Th>
                <Th>{t('staff.pages.ContactRequests.check')}</Th>
                <Th>{t('staff.pages.ContactRequests.decision')}</Th>
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.id} data-testid={`request-${r.id}`}>
                  <Td>
                    <Link
                      className="text-primary underline"
                      to={`/staff/residents/${r.resident_id}`}
                    >
                      #{r.resident_id}
                    </Link>
                  </Td>
                  <Td>{r.name}</Td>
                  <Td>{r.type}</Td>
                  <Td>{r.phone}</Td>
                  <Td>{fmt(r.requested_at)}</Td>
                  <Td>
                    <Badge tone={VERIFY[r.verification]?.tone ?? 'gray'}>
                      {VERIFY[r.verification]?.text ?? r.verification}
                    </Badge>
                  </Td>
                  <Td>
                    {canReview(r) ? (
                      <div className="flex flex-wrap items-center gap-2">
                        <input
                          aria-label={`Note for request ${r.id}`}
                          placeholder={t('staff.pages.ContactRequests.noteNeededToRefuse')}
                          className="rounded-ctl border px-2 py-1"
                          value={note[r.id] ?? ''}
                          onChange={(e) => setNote({ ...note, [r.id]: e.target.value })}
                        />
                        <Btn onClick={() => void review(r, true)}>
                          {t('staff.pages.ContactRequests.approve')}
                        </Btn>
                        <Btn kind="danger" onClick={() => void review(r, false)}>
                          {t('staff.pages.ContactRequests.refuse')}
                        </Btn>
                      </div>
                    ) : (
                      <span className="text-ink-soft">
                        {t('staff.pages.ContactRequests.aSupervisorMustReview')}
                      </span>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>
    </Page>
  )
}
