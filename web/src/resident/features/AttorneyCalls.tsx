import { useEffect, useState } from 'react'
import { Briefcase, Lock, ShieldCheck } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { LinkButton } from '../../ui/Button'
import { Card, ScreenFrame } from '../components'
import { useResident } from '../ResidentContext'

interface Contact {
  id: number
  name: string
  type: 'family' | 'friend' | 'attorney'
  available: boolean
}

export function AttorneyCalls() {
  const { t } = useTranslation()
  const { request } = useResident()
  const [contacts, setContacts] = useState<Contact[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    request<Contact[]>('/device/contacts')
      .then((list) => setContacts(list.filter((c) => c.type === 'attorney')))
      .catch(() => setError('Could not load contacts. Please check your connection.'))
  }, [request])

  return (
    <ScreenFrame title="Attorney Calls">
      <Card className="flex items-start gap-4 border-2 border-primary bg-primary-soft">
        <ShieldCheck aria-hidden="true" className="mt-1 size-8 shrink-0 text-primary" strokeWidth={1.75} />
        <div className="space-y-1">
          <p className="font-bold text-primary">
            Attorney calls are privileged and confidential.
          </p>
          <p className="text-body">
            They are never recorded, monitored, or content-logged. Only that a call occurred
            and its duration may be kept — this is required by law.
          </p>
        </div>
      </Card>

      <Card className="rounded-ctl bg-surface-raised p-4 text-sm">
        Attorney calls do not count against your daily call minutes.
      </Card>

      {error && <p role="alert" className="font-bold text-lock">{error}</p>}

      {contacts !== null && contacts.length === 0 && (
        <Card className="space-y-4 text-center">
          <Lock aria-hidden="true" className="mx-auto size-10 text-ink-soft" strokeWidth={1.5} />
          <p className="font-bold">No attorney contacts on file.</p>
          <p className="text-ink-soft">
            Submit a contact request to add your attorney.
          </p>
          <LinkButton to="/resident/feature/contact_requests" variant="secondary">
            Add attorney contact
          </LinkButton>
        </Card>
      )}

      {contacts !== null && contacts.length > 0 && (
        <Card className="space-y-3">
          <h2 className="text-h3 font-bold">Your attorney contacts</h2>
          <ul className="space-y-3">
            {contacts.map((c) => (
              <li
                key={c.id}
                className="flex items-center gap-4 rounded-ctl border border-line bg-surface p-4"
              >
                <Briefcase
                  aria-hidden="true"
                  className="size-8 shrink-0 text-primary"
                  strokeWidth={1.75}
                />
                <span className="min-w-0 flex-1">
                  <span className="block font-bold">{c.name}</span>
                  <span className="block text-sm text-ink-soft">Attorney</span>
                </span>
                {c.available ? (
                  <button
                    type="button"
                    disabled
                    className="rounded-ctl bg-primary px-5 py-2.5 text-label font-bold text-primary-ink opacity-70"
                    title="Call functionality available via staff-initiated session"
                  >
                    Request call
                  </button>
                ) : (
                  <span className="rounded-full bg-surface-raised px-3 py-1 text-sm text-ink-soft">
                    Unavailable
                  </span>
                )}
              </li>
            ))}
          </ul>
          <p className="text-sm text-ink-soft">
            To place a call, press "Request call" or use the Request Staff button.
          </p>
        </Card>
      )}
    </ScreenFrame>
  )
}
