import { useTranslation } from 'react-i18next'
import { Wrench } from 'lucide-react'
import { BackLink, Card } from '../components'

export function Jobs() {
  const { t } = useTranslation()
  return (
    <div className="mx-auto w-full max-w-2xl space-y-6">
      <BackLink />
      <h1 className="text-h1 font-bold">{t('jobs.title')}</h1>
      <Card>
        <div className="flex items-start gap-4">
          <Wrench
            aria-hidden="true"
            className="mt-1 size-8 shrink-0 text-primary"
            strokeWidth={1.75}
          />
          <p className="text-body">{t('jobs.comingSoon')}</p>
        </div>
      </Card>
    </div>
  )
}
