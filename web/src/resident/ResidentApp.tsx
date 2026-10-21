import { useTranslation } from 'react-i18next'

export default function ResidentApp() {
  const { t } = useTranslation()
  return (
    <main className="p-8 text-2xl">
      <h1>{t('residentHome')}</h1>
      <button className="mt-6 rounded bg-blue-700 px-8 py-6 text-white">{t('requestStaff')}</button>
    </main>
  )
}
