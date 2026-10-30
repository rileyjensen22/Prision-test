import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { EmptyState } from '../../ui/States'
import { NetworkError } from '../api'
import { BackLink, Card } from '../components'
import { Notice } from '../../ui/Notice'
import { useResident } from '../ResidentContext'
import { errorCode } from './helpers'

interface Contact {
  id: number
  name: string
  type: 'family' | 'friend' | 'attorney'
  status: 'pending' | 'approved' | 'rejected'
  available: boolean
  note: string | null
}

const PHONE_RE = /^\+?[0-9\s\-\(\)]{7,15}$/

export function Contacts() {
  const { t } = useTranslation()
  const { request } = useResident()
  const [list, setList] = useState<Contact[] | null>(null)
  const [name, setName] = useState('')
  const [kind, setKind] = useState('family')
  const [phone, setPhone] = useState('')
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const phoneValid = PHONE_RE.test(phone.trim())
  const phoneDuplicate = phone.trim().length > 0 && !!list?.some((c) => c.name.toLowerCase() === name.trim().toLowerCase())

  const load = useCallback(() => {
    request<Contact[]>('/device/contacts/all')
      .then(setList)
      .catch(() => setMessage({ ok: false, text: t('calls.needsConnection') }))
  }, [request, t])
  useEffect(load, [load])

  async function send() {
    setMessage(null)
    try {
      await request('/device/contacts', {
        method: 'POST',
        body: JSON.stringify({ name, type: kind, phone }),
      })
      setName('')
      setPhone('')
      setMessage({ ok: true, text: t('contacts.sent') })
      load()
    } catch (e) {
      setMessage({
        ok: false,
        text:
          e instanceof NetworkError
            ? t('calls.needsConnection')
            : t(`contacts.err.${errorCode(e)}`, { defaultValue: t('contacts.err.ERROR') }),
      })
    }
  }

  const field = 'min-h-touch w-full rounded-ctl border-2 border-ink bg-surface px-3 text-body'
  return (
    <div className="mx-auto w-full max-w-5xl space-y-6">
      <BackLink />
      <h1 className="text-h1 font-bold">{t('contacts.title')}</h1>
      <p>{t('contacts.explain')}</p>
      {message && (
        <Notice
          tone={message.ok ? 'ok' : 'danger'}
          role={message.ok ? 'status' : 'alert'}
          data-testid="contact-message"
        >
          {message.text}
        </Notice>
      )}
      <ul className="space-y-3">
        {(list ?? []).map((c) => (
          <li key={c.id}>
            <Card data-testid={`contact-row-${c.id}`} data-status={c.status}>
              <p className="text-label font-bold">{c.name}</p>
              <p>
                {t(`calls.type.${c.type}`)} · <span>{t(`contacts.status.${c.status}`)}</span>
              </p>
              {c.status === 'rejected' && c.note && <p>{t('contacts.reason', { note: c.note })}</p>}
            </Card>
          </li>
        ))}
      </ul>
      {list?.length === 0 && <EmptyState title={t('calls.none')} />}
      <Card data-testid="contact-form">
        <h2 className="mb-3 text-h2 font-bold">{t('contacts.request')}</h2>
        <label className="block">
          {t('contacts.name')}
          <input
            className={field}
            value={name}
            maxLength={64}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label className="mt-3 block">
          {t('contacts.type')}
          <select className={field} value={kind} onChange={(e) => setKind(e.target.value)}>
            {['family', 'friend', 'attorney'].map((k) => (
              <option key={k} value={k}>
                {t(`calls.type.${k}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="mt-3 block">
          {t('contacts.phone')}
          <input
            className={field}
            value={phone}
            maxLength={20}
            inputMode="tel"
            onChange={(e) => setPhone(e.target.value)}
          />
          {phone.trim().length > 0 && !phoneValid && (
            <p className="mt-1 text-sm text-danger">Enter a valid phone number (7–15 digits, spaces, hyphens, or parentheses allowed).</p>
          )}
        </label>
        {phoneDuplicate && (
          <p className="mt-1 text-sm text-notice">A contact with this name is already in your list.</p>
        )}
        <button
          disabled={!name.trim() || !phoneValid || phoneDuplicate}
          onClick={() => void send()}
          className="mt-4 min-h-touch rounded-ctl bg-primary px-6 py-3 text-label font-bold text-primary-ink hover:brightness-110 disabled:opacity-40"
        >
          {t('contacts.send')}
        </button>
      </Card>
    </div>
  )
}
