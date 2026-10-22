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
    <div className="space-y-6">
      <BackLink />
      <h1 className="text-3xl font-bold">{t('texting.title')}</h1>
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
          <h2 className="text-2xl font-bold">{t('texting.contacts')}</h2>
          {contacts.length === 0 && <p>{t('texting.none')}</p>}
          <Link to="/resident/feature/contact_requests" className="inline-block underline">
            {t('contacts.link')}
          </Link>
          <ul className="space-y-3">
            {contacts.map((c) => (
              <li key={c.id}>
                <button
                  disabled={!c.available}
                  onClick={() => setWho(c)}
                  data-testid={`text-contact-${c.type}`}
                  className="min-h-16 w-full rounded-xl border-2 border-white px-5 py-3 text-left disabled:opacity-40"
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
            className="rounded-lg border-2 border-white px-5 py-3"
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
                  <span data-testid="delivery" data-state={m.delivery} className="ml-2 opacity-80">
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
            className="w-full rounded-lg border-2 border-white bg-slate-900 p-3"
            rows={3}
          />
          <button
            disabled={!text.trim()}
            onClick={() => void send()}
            className="min-h-14 rounded-lg bg-blue-700 px-6 py-3 font-semibold disabled:opacity-40"
          >
            {t('texting.send')}
          </button>
        </>
      )}
    </div>
  )
}
