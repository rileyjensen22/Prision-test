import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { BackLink, Card } from '../components'
import { useResident } from '../ResidentContext'
import { errorCode } from './helpers'

interface Slot {
  slot: string
  kind: 'indoor' | 'outdoor' | 'program' | 'visit'
  title: string | null
  minutes: number
  block_id: number | null
  cancelled: boolean
  allowed: boolean
  booked: boolean
  spaces: number
}
interface Day {
  day: string
  baseline_minutes: number
  slots: Slot[]
}

export function Rec() {
  const { t } = useTranslation()
  const { request } = useResident()
  const [day, setDay] = useState<Day | null>(null)
  const [error, setError] = useState<string | null>(null)
  const load = () =>
    request<Day>('/device/rec')
      .then(setDay)
      .catch(() => {})
  useEffect(() => {
    void load()
  }, [request])

  async function act(slot: string, block: number | null, what: 'book' | 'cancel') {
    if (!day) return
    setError(null)
    try {
      await request(`/device/rec/${what}`, {
        method: 'POST',
        body: JSON.stringify({ day: day.day, slot, block_id: block }),
      })
    } catch (e) {
      const code = errorCode(e)
      setError(t(`rec.err.${code}`, { defaultValue: code }))
    }
    await load()
  }

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6">
      <BackLink />
      <h1 className="text-h1 font-bold">{t('rec.title')}</h1>
      {day && <p data-testid="rec-baseline">{t('rec.baseline', { n: day.baseline_minutes })}</p>}
      {error && (
        <p role="alert" data-testid="rec-error">
          {error}
        </p>
      )}
      <ul className="space-y-3">
        {(day?.slots ?? []).map((s) => (
          <li key={`${s.slot}-${s.kind}`}>
            <Card
              data-testid={`slot-${s.slot}`}
              data-kind={s.kind}
              data-allowed={s.allowed}
              data-booked={s.booked}
            >
              <p className="text-label font-bold">
                {s.slot} · {s.title ?? t(`rec.${s.kind}`)}
              </p>
              <p className="text-ink-soft">
                {t(`rec.${s.kind}`)} · {t('rec.minutes', { n: s.minutes })}
              </p>
              {s.cancelled ? (
                <p data-testid="slot-cancelled">{t('rec.cancelledBlock')}</p>
              ) : !s.allowed ? (
                <p>🔒 {t('rec.locked')}</p>
              ) : (
                <div className="mt-2 flex items-center gap-3">
                  <span>{t('rec.spaces', { n: s.spaces })}</span>
                  {s.booked ? (
                    <>
                      <span>✓ {t('rec.booked')}</span>
                      <button
                        onClick={() => void act(s.slot, s.block_id, 'cancel')}
                        className="min-h-touch rounded-ctl border-2 border-ink bg-surface px-6 py-3 text-label font-bold text-ink hover:bg-surface-2"
                      >
                        {t('rec.cancel')}
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={() => void act(s.slot, s.block_id, 'book')}
                      className="min-h-touch rounded-ctl bg-primary px-6 py-3 text-label font-bold text-primary-ink hover:brightness-110"
                    >
                      {t('rec.book')}
                    </button>
                  )}
                </div>
              )}
            </Card>
          </li>
        ))}
      </ul>
    </div>
  )
}
