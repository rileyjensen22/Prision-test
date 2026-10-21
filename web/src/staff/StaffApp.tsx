import { useTranslation } from 'react-i18next'

export default function StaffApp() {
  const { t } = useTranslation()
  return (
    <main className="p-8">
      <h1 className="text-xl">{t('staffHome')}</h1>
    </main>
  )
}
