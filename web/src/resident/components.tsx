import type { TFunction } from 'i18next'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import type { Lock, Reason } from './types'

export function Time({ iso }: { iso: string }) {
  const { i18n } = useTranslation()
  const text = new Date(iso).toLocaleString(i18n.language, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
  return <time dateTime={iso}>{text}</time>
}

export function BackLink() {
  const { t } = useTranslation()
  return (
    <Link to="/resident" className="inline-block rounded-lg border-2 border-white px-6 py-4">
      ← {t('app.back')}
    </Link>
  )
}

export function Card({ children, ...rest }: { children: ReactNode } & Record<string, unknown>) {
  return (
    <section className="rounded-xl border-2 border-slate-500 bg-slate-900 p-5" {...rest}>
      {children}
    </section>
  )
}

export function reasonTitle(t: TFunction, r: Pick<Reason | Lock, 'code' | 'params'>) {
  return t(`code.${r.code}`, r.params)
}

export function EndTime({ iso }: { iso: string | null }) {
  const { t } = useTranslation()
  if (!iso) return <span>{t('home.untilReview')}</span>
  return (
    <span>
      {t('home.until', { time: '' })}
      <Time iso={iso} />
    </span>
  )
}
