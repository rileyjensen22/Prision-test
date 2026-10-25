import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { ErrorState, LoadingState } from '../../ui/States'
import { BackLink, Card } from '../components'
import { useResident } from '../ResidentContext'
import { L } from './helpers'
import type { Bi } from './helpers'

interface Data {
  countdown: { release_date: string; days_left: number; weeks_left: number } | null
  checklist: { code: string; title: Bi; detail: Bi; status: string }[]
  progress: { done: number; resolved: number; total: number }
  courses: { code: string; title: Bi; lessons: number; lessons_done: number; completed: boolean }[]
  resources: { code: string; category: string; title: Bi; description: Bi; phone: string }[]
}

export function Reentry() {
  const { t, i18n } = useTranslation()
  const { request, online } = useResident()
  const [data, setData] = useState<Data | null>(null)
  const [error, setError] = useState(false)
  const lang = i18n.language

  useEffect(() => {
    request<Data>('/device/reentry')
      .then(setData)
      .catch(() => setError(true))
  }, [request, online])

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6">
      <BackLink />
      <h1 className="text-h1 font-bold">{t('reentry.title')}</h1>
      {error && <ErrorState title={t('reentry.needsConnection')} />}
      {!data && !error && <LoadingState />}
      {data && (
        <>
          <Card data-testid="reentry-countdown">
            {data.countdown ? (
              <>
                <p className="text-body">{t('reentry.countdownLabel')}</p>
                <p className="text-display font-bold">
                  {t('reentry.daysLeft', { count: data.countdown.days_left })}
                </p>
              </>
            ) : (
              <p>{t('reentry.noDate')}</p>
            )}
          </Card>

          <Card>
            <h2 className="text-h2 font-bold">{t('reentry.checklist')}</h2>
            <p data-testid="reentry-progress">
              {t('reentry.progress', { done: data.progress.resolved, total: data.progress.total })}
            </p>
            <ul className="mt-3 space-y-3">
              {data.checklist.map((i) => (
                <li
                  key={i.code}
                  data-testid={`reentry-item-${i.code}`}
                  data-status={i.status}
                  className="rounded-card border border-line bg-surface p-4 shadow-card"
                >
                  <p className="text-label font-bold">
                    {i.status === 'done' ? '✓ ' : ''}
                    {L(i.title, lang)}
                  </p>
                  <p className="text-sm font-bold text-ink-soft">
                    {t(`reentry.status.${i.status}`)}
                  </p>
                  <p className="mt-1">{L(i.detail, lang)}</p>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-sm">{t('reentry.staffNote')}</p>
          </Card>

          {data.courses.length > 0 && (
            <Card>
              <h2 className="text-h2 font-bold">{t('reentry.courses')}</h2>
              <ul className="mt-3 space-y-2">
                {data.courses.map((c) => (
                  <li key={c.code}>
                    <Link
                      to={`/resident/course/${c.code}`}
                      className="block min-h-touch rounded-card border border-line bg-surface p-4 font-bold text-primary shadow-card hover:border-primary"
                    >
                      {L(c.title, lang)}{' '}
                      {c.completed
                        ? `✓ ${t('education.done')}`
                        : `(${t('education.progress', { done: c.lessons_done, total: c.lessons })})`}
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <Card data-testid="reentry-resources">
            <h2 className="text-h2 font-bold">{t('reentry.resources')}</h2>
            <p className="text-sm">{t('reentry.resourcesNote')}</p>
            <ul className="mt-3 space-y-3">
              {data.resources.map((r) => (
                <li
                  key={r.code}
                  className="rounded-card border border-line bg-surface p-4 shadow-card"
                >
                  <p className="text-label font-bold">{L(r.title, lang)}</p>
                  <p>{L(r.description, lang)}</p>
                  <p className="font-mono">{r.phone}</p>
                </li>
              ))}
            </ul>
          </Card>
        </>
      )}
    </div>
  )
}
