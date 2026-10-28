import type { TFunction } from 'i18next'
import { ArrowLeft } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { Card } from '../ui/Card'
import { LinkButton } from '../ui/Button'
import { useResident } from './ResidentContext'
import type { Lock, Reason } from './types'

export { Card }

const LONG: Intl.DateTimeFormatOptions = {
  weekday: 'short',
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
}

export function Time({ iso, long = false }: { iso: string; long?: boolean }) {
  const { i18n } = useTranslation()
  const text = new Date(iso).toLocaleString(
    i18n.language,
    long ? LONG : { dateStyle: 'medium', timeStyle: 'short' },
  )
  return <time dateTime={iso}>{text}</time>
}

/** "in 23 hours" / "dentro de 23 horas": the length of a lock is easier to feel than a clock time. */
export function relativeFromNow(iso: string, nowMs: number, lang: string): string {
  const mins = Math.round((Date.parse(iso) - nowMs) / 60_000)
  const rtf = new Intl.RelativeTimeFormat(lang, { numeric: 'auto' })
  if (Math.abs(mins) < 60) return rtf.format(mins, 'minute')
  if (Math.abs(mins) < 48 * 60) return rtf.format(Math.round(mins / 60), 'hour')
  return rtf.format(Math.round(mins / 1440), 'day')
}

export function BackLink() {
  const { t } = useTranslation()
  return (
    <LinkButton to="/resident" icon={ArrowLeft} variant="secondary" className="self-start">
      {t('app.back')}
    </LinkButton>
  )
}

/** Every sub-screen: Back, one heading, then the content. One primary action lives in the content. */
export function ScreenFrame({
  title,
  intro,
  children,
  narrow = false,
}: {
  title: ReactNode
  intro?: ReactNode
  children: ReactNode
  narrow?: boolean
}) {
  return (
    <div className={`mx-auto flex w-full flex-col gap-6 ${narrow ? 'max-w-3xl' : 'max-w-5xl'}`}>
      <BackLink />
      <header className="space-y-2">
        <h1 className="text-h1 font-bold">{title}</h1>
        {intro && <p className="max-w-[60ch] text-body text-ink-soft">{intro}</p>}
      </header>
      {children}
    </div>
  )
}

export function reasonTitle(t: TFunction, r: Pick<Reason | Lock, 'code' | 'params'>) {
  return t(`code.${r.code}`, r.params)
}

export function EndTime({ iso }: { iso: string | null }) {
  const { t, i18n } = useTranslation()
  const { now } = useResident()
  if (!iso) return <span>{t('home.untilReview')}</span>
  return (
    <span>
      {t('home.until', { time: '' })}
      <Time iso={iso} long />{' '}
      <span className="text-ink-soft">({relativeFromNow(iso, now, i18n.language)})</span>
    </span>
  )
}
