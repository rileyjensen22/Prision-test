import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { ErrorLine, Page, Panel, useLoad } from '../ui'

interface VideoSession {
  id: number
  resident_id: number
  contact_id: number
  duration_seconds: number | null
  started_at: string
  ended_at: string | null
  status: string
  monitored: boolean
}

function fmtDuration(s: number | null) {
  if (s == null) return '—'
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}m ${sec}s`
}

export default function VideoOversight() {
  const { t } = useTranslation()
  const { data, error } = useLoad<VideoSession[]>('/staff/video/sessions')

  return (
    <Page title={t('staff.pages.VideoOversight.title', 'Video Call Oversight')}>
      <Panel className="border-primary bg-primary/5 text-sm">
        Attorney video calls are excluded from this view. They are privileged and no content
        is ever recorded (invariant 6).
      </Panel>
      <ErrorLine error={error} />
      {data?.length === 0 && <Panel><p>No video sessions on record.</p></Panel>}
      {(data ?? []).map((s) => (
        <Panel key={s.id} data-testid={`video-${s.id}`}>
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1">
              <p className="font-semibold">
                <Link className="text-primary underline" to={`/staff/residents/${s.resident_id}`}>
                  Resident #{s.resident_id}
                </Link>
                {' · '}Contact #{s.contact_id}
              </p>
              <p className="text-sm">Duration: {fmtDuration(s.duration_seconds)}</p>
              <p className="text-xs text-ink-soft">
                {new Date(s.started_at).toLocaleString()}
                {s.ended_at ? ` – ${new Date(s.ended_at).toLocaleString()}` : ' (active)'}
              </p>
            </div>
            <span className="text-sm text-ink-soft">{s.monitored ? 'Monitored' : 'Not monitored'}</span>
          </div>
        </Panel>
      ))}
    </Page>
  )
}
