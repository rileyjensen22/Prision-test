import { useTranslation } from 'react-i18next'
import { featureIcon } from '../icons'
import { ScreenFrame } from '../components'

export function Grievances() {
  const { t } = useTranslation()
  const Icon = featureIcon('grievances_appeals')
  return (
    <ScreenFrame title={t('feature.grievances_appeals')} icon={Icon}>
      <p className="text-body text-ink-soft">{t('stub.text')}</p>
    </ScreenFrame>
  )
}
