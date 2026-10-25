import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Brain, CheckCircle2, HeartPulse, UserRound } from 'lucide-react'

import { Button } from '../ui/Button'
import { Sheet } from '../ui/Sheet'
import { useResident } from './ResidentContext'

const KINDS = ['staff', 'medical', 'mental_health'] as const
const ICON = { staff: UserRound, medical: HeartPulse, mental_health: Brain }

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
    <Sheet title={t('request.title')} onClose={onClose}>
      {result ? (
        <p
          data-testid="request-result"
          role="status"
          className="flex items-center gap-3 rounded-card border-2 border-ok bg-ok-soft p-5 text-label font-bold"
        >
          <CheckCircle2 aria-hidden="true" className="size-8 shrink-0 text-ok" />
          {result === 'queued' ? t('app.queued') : t('request.sent')}
        </p>
      ) : (
        <ul className="space-y-3">
          {KINDS.map((k) => (
            <li key={k}>
              <Button
                variant={k === 'staff' ? 'primary' : 'secondary'}
                icon={ICON[k]}
                onClick={() => void send(k)}
                className="w-full justify-start"
              >
                {t(`request.${k}`)}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Sheet>
  )
}
