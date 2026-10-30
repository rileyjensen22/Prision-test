import { useEffect, useState } from 'react'
import { CheckCircle2, HeartPulse } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '../../ui/Button'
import { Card, ScreenFrame } from '../components'
import { useResident } from '../ResidentContext'

interface HealthRequest {
  id: number
  kind: 'medical' | 'mental_health'
  status: 'open' | 'triaged' | 'scheduled' | 'seen' | 'closed'
  created_at: string
  staff_note: string
}

const STATUS_LABEL: Record<HealthRequest['status'], string> = {
  open: 'Open',
  triaged: 'Triaged',
  scheduled: 'Appointment scheduled',
  seen: 'Seen',
  closed: 'Closed',
}

const STATUS_COLOR: Record<HealthRequest['status'], string> = {
  open: 'bg-notice-soft text-notice',
  triaged: 'bg-primary-soft text-primary',
  scheduled: 'bg-primary-soft text-primary',
  seen: 'bg-ok-soft text-ok',
  closed: 'bg-surface-raised text-ink-soft',
}

export function HealthRequests() {
  const { t } = useTranslation()
  const { request, features } = useResident()
  const f = features['health_requests']

  const [kind, setKind] = useState<'medical' | 'mental_health'>('medical')
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [past, setPast] = useState<HealthRequest[]>([])

  useEffect(() => {
    request<HealthRequest[]>('/device/health-requests')
      .then(setPast)
      .catch(() => {})
  }, [request, submitted])

  if (!f) return null

  async function handleSubmit() {
    if (description.trim().length < 10) {
      setError('Please provide more detail (at least 10 characters).')
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      await request('/device/health-request', {
        method: 'POST',
        body: JSON.stringify({ kind, description: description.trim() }),
      })
      setSubmitted(true)
      setDescription('')
    } catch {
      setError('Could not submit your request. Please try again or speak with staff.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <ScreenFrame title="Health Requests">
      {submitted && (
        <Card className="flex items-center gap-4 border-2 border-ok bg-ok-soft">
          <CheckCircle2 aria-hidden="true" className="size-8 shrink-0 text-ok" strokeWidth={1.75} />
          <p className="font-bold">Your request has been received. Staff will follow up.</p>
        </Card>
      )}

      <Card className="space-y-4">
        <h2 className="text-h3 font-bold">Submit a request</h2>

        <div>
          <p className="mb-2 font-bold">Type of request</p>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => setKind('medical')}
              className={`flex-1 rounded-ctl border-2 px-4 py-3 text-label font-bold transition-colors ${
                kind === 'medical' ? 'border-primary bg-primary text-primary-ink' : 'border-line bg-surface hover:border-primary'
              }`}
            >
              <HeartPulse aria-hidden="true" className="mx-auto mb-1 size-6" />
              Medical
            </button>
            <button
              type="button"
              onClick={() => setKind('mental_health')}
              className={`flex-1 rounded-ctl border-2 px-4 py-3 text-label font-bold transition-colors ${
                kind === 'mental_health' ? 'border-primary bg-primary text-primary-ink' : 'border-line bg-surface hover:border-primary'
              }`}
            >
              <HeartPulse aria-hidden="true" className="mx-auto mb-1 size-6" />
              Mental health
            </button>
          </div>
        </div>

        <div>
          <label htmlFor="health-desc" className="mb-2 block font-bold">
            Describe your concern
          </label>
          <textarea
            id="health-desc"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
            placeholder="Describe what you need help with..."
            className="w-full rounded-ctl border border-line bg-surface p-3 text-body focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>

        {error && <p role="alert" className="text-lock font-bold">{error}</p>}

        <Button
          variant="primary"
          onClick={() => void handleSubmit()}
          disabled={submitting}
        >
          {submitting ? 'Submitting…' : 'Submit request'}
        </Button>
      </Card>

      {past.length > 0 && (
        <Card className="space-y-3">
          <h2 className="text-h3 font-bold">Your past requests</h2>
          <ul className="space-y-3">
            {past.map((r) => (
              <li key={r.id} className="rounded-ctl border border-line bg-surface p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-bold">{r.kind === 'medical' ? 'Medical' : 'Mental health'}</span>
                  <span className={`rounded-full px-3 py-0.5 text-sm font-bold ${STATUS_COLOR[r.status]}`}>
                    {STATUS_LABEL[r.status]}
                  </span>
                </div>
                <p className="mt-1 text-sm text-ink-soft">
                  {new Date(r.created_at).toLocaleDateString()}
                </p>
                {r.staff_note && (
                  <div className="mt-2 rounded-ctl bg-surface-raised p-3 text-sm">
                    <span className="font-bold">Staff note: </span>{r.staff_note}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </ScreenFrame>
  )
}
