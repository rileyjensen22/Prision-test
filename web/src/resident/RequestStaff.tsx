import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useResident } from './ResidentContext'

const KINDS = ['staff', 'medical', 'mental_health'] as const

export function RequestStaffDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const { submit } = useResident()
  const [result, setResult] = useState<'sent' | 'queued' | null>(null)

  async function send(kind: string) {
    const r = await submit({
      type: 'request',
      payload: { kind, created_at: new Date().toISOString() },
    })
    setResult(r === 'queued' ? 'queued' : 'sent')
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t('request.title')}
      className="fixed inset-0 z-20 flex items-center justify-center bg-black/80 p-6"
    >
      <div className="w-full max-w-xl space-y-4 rounded-2xl border-2 border-white bg-slate-900 p-8">
        <h2 className="text-3xl font-bold">{t('request.title')}</h2>
        {result ? (
          <p data-testid="request-result" role="status">
            {result === 'queued' ? t('app.queued') : t('request.sent')}
          </p>
        ) : (
          KINDS.map((k) => (
            <button
              key={k}
              onClick={() => void send(k)}
              className="block min-h-16 w-full rounded-xl bg-blue-700 px-6 py-4 text-left font-semibold"
            >
              {t(`request.${k}`)}
            </button>
          ))
        )}
        <button
          onClick={onClose}
          className="min-h-16 w-full rounded-xl border-2 border-white px-6 py-4"
        >
          {t('request.close')}
        </button>
      </div>
    </div>
  )
}
