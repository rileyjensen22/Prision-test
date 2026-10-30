import { useEffect, useState } from 'react'
import { CheckCircle2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '../../ui/Button'
import { Card, ScreenFrame } from '../components'
import { useResident } from '../ResidentContext'

interface Grievance {
  id: number
  category: string
  status: 'open' | 'under_review' | 'resolved' | 'closed'
  created_at: string
  response: string
}

const CATEGORIES = [
  { value: 'conditions', label: 'Conditions of confinement' },
  { value: 'staff_conduct', label: 'Staff conduct' },
  { value: 'medical', label: 'Medical care' },
  { value: 'programs', label: 'Programs and activities' },
  { value: 'other', label: 'Other' },
]

const STATUS_LABEL: Record<Grievance['status'], string> = {
  open: 'Open',
  under_review: 'Under review',
  resolved: 'Resolved',
  closed: 'Closed',
}

const STATUS_COLOR: Record<Grievance['status'], string> = {
  open: 'bg-notice-soft text-notice',
  under_review: 'bg-primary-soft text-primary',
  resolved: 'bg-ok-soft text-ok',
  closed: 'bg-surface-raised text-ink-soft',
}

export function Grievances() {
  const { t } = useTranslation()
  const { request } = useResident()

  const [category, setCategory] = useState('conditions')
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [past, setPast] = useState<Grievance[]>([])

  useEffect(() => {
    request<Grievance[]>('/device/grievances')
      .then(setPast)
      .catch(() => {})
  }, [request, submitted])

  async function handleSubmit() {
    if (description.trim().length < 10) {
      setError('Please provide more detail (at least 10 characters).')
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      await request('/device/grievance', {
        method: 'POST',
        body: JSON.stringify({ category, description: description.trim() }),
      })
      setSubmitted(true)
      setDescription('')
    } catch {
      setError('Could not submit your grievance. Please try again or speak with staff.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <ScreenFrame title="Grievances and Appeals">
      <Card className="bg-primary-soft p-4">
        <p className="text-sm">
          Filing a grievance is your right. It is always available regardless of your tier.
          You will receive a response within 30 days. If unsatisfied, you may appeal.
        </p>
      </Card>

      {submitted && (
        <Card className="flex items-center gap-4 border-2 border-ok bg-ok-soft">
          <CheckCircle2 aria-hidden="true" className="size-8 shrink-0 text-ok" strokeWidth={1.75} />
          <p className="font-bold">Your grievance has been filed. You will receive a response within 30 days.</p>
        </Card>
      )}

      <Card className="space-y-4">
        <h2 className="text-h3 font-bold">File a grievance</h2>

        <div>
          <label htmlFor="griev-category" className="mb-2 block font-bold">
            Category
          </label>
          <select
            id="griev-category"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="w-full rounded-ctl border border-line bg-surface p-3 text-body focus:outline-none focus:ring-2 focus:ring-primary"
          >
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="griev-desc" className="mb-2 block font-bold">
            Describe your grievance
          </label>
          <textarea
            id="griev-desc"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={5}
            placeholder="Describe the issue and what resolution you are seeking..."
            className="w-full rounded-ctl border border-line bg-surface p-3 text-body focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>

        {error && <p role="alert" className="text-lock font-bold">{error}</p>}

        <Button
          variant="primary"
          onClick={() => void handleSubmit()}
          disabled={submitting}
        >
          {submitting ? 'Submitting…' : 'Submit grievance'}
        </Button>
      </Card>

      {past.length > 0 && (
        <Card className="space-y-3">
          <h2 className="text-h3 font-bold">Your past grievances</h2>
          <ul className="space-y-3">
            {past.map((g) => (
              <li key={g.id} className="rounded-ctl border border-line bg-surface p-4 space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-bold">
                    {CATEGORIES.find((c) => c.value === g.category)?.label ?? g.category}
                  </span>
                  <span className={`rounded-full px-3 py-0.5 text-sm font-bold ${STATUS_COLOR[g.status]}`}>
                    {STATUS_LABEL[g.status]}
                  </span>
                </div>
                <p className="text-sm text-ink-soft">
                  {new Date(g.created_at).toLocaleDateString()}
                </p>
                {g.response && (
                  <div className="rounded-ctl bg-surface-raised p-3 text-sm">
                    <span className="font-bold">Staff response: </span>{g.response}
                  </div>
                )}
                {(g.status === 'resolved' || g.status === 'closed') && (
                  <Button variant="secondary" className="text-sm">
                    Appeal this decision
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </ScreenFrame>
  )
}
