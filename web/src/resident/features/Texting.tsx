import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { NetworkError } from '../api'
import { BackLink, Card } from '../components'
import { useResident } from '../ResidentContext'
import { errorCode } from './helpers'

interface Contact {
  id: number
  name: string
  type: 'family' | 'friend' | 'attorney'
  available: boolean
}
interface Msg {
  id: number
  direction: 'out' | 'in'
  body: string | null
  private: boolean
  delivery: 'queued' | 'sent' | 'delivered' | 'failed'
}

export function Texting() {
  const { t } = useTranslation()
  const { request, view, refresh } = useResident()
  const [contacts, setContacts] = useState<Contact[]>([])
  const [who, setWho] = useState<Contact | null>(null)
  const [thread, setThread] = useState<Msg[]>([])
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [sentPrivately, setSentPrivately] = useState(false)

  useEffect(() => {
    request<Contact[]>('/device/contacts')
      .then(setContacts)
      .catch(() => setError(t('calls.needsConnection')))
  }, [request, t])

  useEffect(() => {
    if (who)
      request<Msg[]>(`/device/messages?contact_id=${who.id}`)
        .then(setThread)
        .catch(() => {})
  }, [who, request])

  async function send() {
    if (!who) return
    setError(null)
    try {
      const r = await request<{ private: boolean }>('/device/messages', {
        method: 'POST',
        body: JSON.stringify({ contact_id: who.id, body: text }),
      })
      setText('')
      setSentPrivately(r.private)
      setThread(await request<Msg[]>(`/device/messages?contact_id=${who.id}`))
      void refresh()
    } catch (e) {
      const code = errorCode(e)
      setError(
        e instanceof NetworkError
          ? t('calls.needsConnection')
          : t(`texting.err.${code}`, { defaultValue: code }),
      )
    }
  }

  const allowance = view?.allowances.find((a) => a.feature === 'texting')
  const privileged = who?.type === 'attorney'

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6">
      <BackLink />
      <h1 className="text-h1 font-bold">{t('texting.title')}</h1>
      {allowance && (
        <p data-testid="texts-left">
          {t('texting.left', { n: Math.max(0, allowance.limit - allowance.used) })}
        </p>
      )}
      {error && (
        <p role="alert" data-testid="text-error">
          {error}
        </p>
      )}
      {!who ? (
        <>
          <h2 className="text-h2 font-bold">{t('texting.contacts')}</h2>
          {contacts.length === 0 && <p>{t('texting.none')}</p>}
          <Link
            to="/resident/feature/contact_requests"
            className="inline-block text-primary underline underline-offset-4"
          >
            {t('contacts.link')}
          </Link>
          <ul className="space-y-3">
            {contacts.map((c) => (
              <li key={c.id}>
                <button
                  disabled={!c.available}
                  onClick={() => setWho(c)}
                  data-testid={`text-contact-${c.type}`}
                  className="min-h-touch rounded-ctl border-2 border-ink bg-surface px-6 py-3 text-label font-bold text-ink hover:bg-surface-2 w-full justify-start text-left disabled:opacity-40"
                >
                  {c.name} · {t(`calls.type.${c.type}`)}
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <>
          <button
            onClick={() => {
              setWho(null)
              setSentPrivately(false)
            }}
            className="min-h-touch rounded-ctl border-2 border-ink bg-surface px-6 py-3 text-label font-bold text-ink hover:bg-surface-2"
          >
            ← {who.name}
          </button>
          <p data-testid="text-notice" className="font-semibold">
            {privileged ? t('texting.privileged') : t('texting.monitored')}
          </p>
          <Card data-testid="thread">
            {thread.length === 0 && !sentPrivately && <p>…</p>}
            {thread.map((m) => (
              <p key={m.id} data-testid={`msg-${m.direction}`}>
                <strong>{m.direction === 'out' ? t('texting.you') : t('texting.them')}: </strong>
                {m.body ?? t('texting.sentPrivately')}
                {m.direction === 'out' && (
                  <span
                    data-testid="delivery"
                    data-state={m.delivery}
                    className="ml-2 text-ink-soft"
                  >
                    ({t(`texting.delivery.${m.delivery}`)})
                  </span>
                )}
              </p>
            ))}
          </Card>
          <textarea
            aria-label={t('texting.placeholder')}
            placeholder={t('texting.placeholder')}
            value={text}
            maxLength={500}
            onChange={(e) => setText(e.target.value)}
            className="w-full rounded-ctl border-2 border-ink bg-surface p-3 text-body"
            rows={3}
          />
          <button
            disabled={!text.trim()}
            onClick={() => void send()}
            className="min-h-touch rounded-ctl bg-primary px-6 py-3 text-label font-bold text-primary-ink hover:brightness-110 disabled:opacity-40"
          >
            {t('texting.send')}
          </button>
        </>
      )}
    </div>
  )
}
