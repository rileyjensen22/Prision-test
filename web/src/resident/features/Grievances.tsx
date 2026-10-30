import { useTranslation } from 'react-i18next'
import { ScreenFrame } from '../components'

export function Grievances() {
  const { t } = useTranslation()
  return (
    <ScreenFrame title={t('feature.grievances_appeals')}>
      <p className="text-body text-ink-soft">{t('stub.text')}</p>
    </ScreenFrame>
  )
}
