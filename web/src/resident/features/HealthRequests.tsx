import { useTranslation } from 'react-i18next'
import { HeartPulse } from 'lucide-react'
import { ScreenFrame } from '../components'
import { useResident } from '../ResidentContext'
import { featureIcon } from '../icons'

export function HealthRequests() {
  const { t } = useTranslation()
  const { features } = useResident()
  const f = features['health_requests']
  if (!f) return null
  const Icon = featureIcon('health_requests')
  return (
    <ScreenFrame title={t('feature.health_requests')} icon={Icon}>
      <p className="text-body text-ink-soft">{t('stub.text')}</p>
      <div className="mt-6 space-y-3">
        <RequestCard label={t('request.medical')} icon={HeartPulse} />
        <RequestCard label={t('request.mental_health')} icon={HeartPulse} />
      </div>
    </ScreenFrame>
  )
}

function RequestCard({ label, icon: Icon }: { label: string; icon: typeof HeartPulse }) {
  const { t } = useTranslation()
  return (
    <div className="flex items-center gap-4 rounded-card border border-line bg-surface p-5 shadow-card">
      <Icon aria-hidden="true" className="size-8 shrink-0 text-primary" strokeWidth={1.75} />
      <span className="flex-1 text-label font-bold">{label}</span>
      <span className="rounded-full bg-surface-raised px-3 py-1 text-sm text-ink-soft">
        {t('stub.title')}
      </span>
    </div>
  )
}
