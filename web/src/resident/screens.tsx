import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { BackLink, Card, EndTime, Time, reasonTitle } from './components'
import { money } from './features/helpers'
import { useResident } from './ResidentContext'

const ALWAYS_ORDER = [
  'attorney_calls',
  'contact_requests',
  'legal_materials',
  'grievances_appeals',
  'medical_requests',
  'mental_health_requests',
  'emergency_contact',
  'religious_texts',
  'basic_education',
  'out_of_cell_minimum',
] // request_staff is the persistent button, so it is not repeated as a tile

export function Home() {
  const { t, i18n } = useTranslation()
  const { view, features } = useResident()
  if (!view) return null
  const { tier } = view
  const pct = tier.next_tier
    ? Math.min(100, Math.round((tier.points / (tier.points + (tier.points_to_next ?? 1))) * 100))
    : 100
  const services = Object.entries(features).filter(([, f]) => !f.baseline)

  return (
    <div className="space-y-6">
      <Card data-testid="tier-card">
        <div className="flex items-baseline justify-between">
          <h1 className="text-4xl font-bold" data-testid="tier-label">
            {t('tier.label', { n: tier.effective })}
          </h1>
          <span>{t('tier.points', { count: tier.points })}</span>
        </div>
        <div
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          className="my-3 h-4 w-full rounded bg-slate-700"
        >
          <div className="h-4 rounded bg-green-500" style={{ width: `${pct}%` }} />
        </div>
        <p data-testid="next-tier">
          {tier.next_tier && !tier.capped_by_ceiling
            ? t('tier.toNext', { count: tier.points_to_next, next: tier.next_tier })
            : tier.capped_by_ceiling
              ? t('tier.cappedNote', { n: tier.ceiling })
              : t('tier.top')}
        </p>
        <Link to="/resident/tier" className="mt-3 inline-block underline">
          {t('tier.details')}
        </Link>
      </Card>

      <Card data-testid="locks-card">
        <h2 className="mb-3 text-2xl font-bold">{t('home.locks')}</h2>
        {view.locks.length === 0 && <p>{t('home.noLocks')}</p>}
        <ul className="space-y-4">
          {view.locks.map((lock) => (
            <li
              key={lock.key}
              data-testid="lock"
              data-code={lock.code}
              className="rounded-lg border-2 border-amber-400 p-4"
            >
              <p className="text-xl font-semibold" data-testid="lock-title">
                {reasonTitle(t, lock)}
              </p>
              {lock.source === 'offense' && lock.detail && <p>{lock.detail}</p>}
              <p data-testid="lock-until">
                <EndTime iso={lock.ends_at} />
              </p>
              <p>
                {t('locks.affects', {
                  features: lock.features.map((f) => t(`feature.${f}`)).join(', '),
                })}
              </p>
              <div className="mt-3 flex flex-wrap gap-3">
                <Link
                  to={`/resident/locks?lock=${encodeURIComponent(lock.key)}`}
                  className="min-h-14 rounded-lg border-2 border-white px-5 py-3"
                >
                  {t('home.why')}
                </Link>
                {lock.how_to_appeal === 'appeal' &&
                  lock.sanction_id != null &&
                  (lock.appeal_open ? (
                    <span
                      className="min-h-14 rounded-lg bg-slate-700 px-5 py-3"
                      data-testid="appeal-sent"
                    >
                      {t('home.appealSent')}
                    </span>
                  ) : (
                    <Link
                      to={`/resident/appeal/${lock.sanction_id}`}
                      className="min-h-14 rounded-lg bg-amber-500 px-5 py-3 font-semibold text-black"
                    >
                      {t('home.appeal')}
                    </Link>
                  ))}
              </div>
            </li>
          ))}
        </ul>
      </Card>

      {view.allowances.length > 0 && (
        <Card data-testid="allowances">
          <h2 className="mb-3 text-2xl font-bold">{t('home.allowances')}</h2>
          <ul className="space-y-1">
            {view.allowances.map((a) => (
              <li key={`${a.feature}-${a.unit}`} data-testid={`allowance-${a.feature}`}>
                {t(`feature.${a.feature}`)}:{' '}
                {a.unit === 'dollars'
                  ? t('home.leftMoney', {
                      left: money(Math.round((a.limit - a.used) * 100), i18n.language),
                      limit: money(a.limit * 100, i18n.language),
                    })
                  : t('home.left', {
                      left: a.limit - a.used,
                      limit: a.limit,
                      unit: t(`units.${a.unit}`),
                    })}{' '}
                {a.period === 'day' ? t('home.perDay') : t('home.perWeek')}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card>
        <h2 className="mb-3 text-2xl font-bold">{t('home.services')}</h2>
        <ul className="grid grid-cols-2 gap-3">
          {services.map(([name, f]) => (
            <li key={name}>
              <Link
                to={f.allowed ? `/resident/feature/${name}` : `/resident/locks?feature=${name}`}
                data-testid={`tile-${name}`}
                data-allowed={f.allowed}
                className={`block min-h-24 rounded-xl border-2 p-4 ${f.allowed ? 'border-green-400' : 'border-amber-400 opacity-90'}`}
              >
                <span className="block text-xl font-semibold">{t(`feature.${name}`)}</span>
                <span className="block">
                  {f.allowed ? t('home.open') : `🔒 ${t('home.locked')}`}
                </span>
                {!f.allowed && f.reasons[0] && (
                  <span className="block text-base" data-testid={`tile-reason-${name}`}>
                    {reasonTitle(t, f.reasons[0])}
                  </span>
                )}
              </Link>
            </li>
          ))}
        </ul>
      </Card>

      {view.reentry && (
        <Link to="/resident/reentry" data-testid="release-countdown" className="block">
          <Card>
            <p className="text-lg">{t('reentry.countdownLabel')}</p>
            <p className="text-4xl font-bold">
              {t('reentry.daysLeft', { count: view.reentry.days_left })}
            </p>
          </Card>
        </Link>
      )}

      <Card>
        <h2 className="mb-3 text-2xl font-bold">{t('home.optional')}</h2>
        <Link
          to="/resident/reentry"
          data-testid="reentry-link"
          className="mb-3 block min-h-16 rounded-xl border-2 border-slate-400 p-4 text-xl"
        >
          {t('home.reentryLink')}
        </Link>
        <Link
          to="/resident/jobs"
          data-testid="jobs-link"
          className="block min-h-16 rounded-xl border-2 border-slate-400 p-4 text-xl"
        >
          {t('home.jobsLink')}
        </Link>
      </Card>

      <Card>
        <h2 className="mb-3 text-2xl font-bold">{t('home.always')}</h2>
        <ul className="grid grid-cols-2 gap-3">
          {ALWAYS_ORDER.filter((n) => features[n]).map((name) => (
            <li key={name}>
              <Link
                to={`/resident/feature/${name}`}
                data-testid={`tile-${name}`}
                data-allowed="true"
                className="block min-h-20 rounded-xl border-2 border-green-400 p-4 text-xl"
              >
                {t(`feature.${name}`)}
              </Link>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  )
}

export function Locks() {
  const { t } = useTranslation()
  const { view, features } = useResident()
  const [params] = useSearchParams()
  if (!view) return null
  const feature = params.get('feature')
  const lockKey = params.get('lock')
  const shown = feature
    ? (features[feature]?.reasons ?? []).map((r) => ({
        ...r,
        features: [feature],
        key: `${r.code}-${r.sanction_id}`,
      }))
    : view.locks.filter((l) => !lockKey || l.key === lockKey)

  return (
    <div className="space-y-6">
      <BackLink />
      <h1 className="text-3xl font-bold">{t('locks.title')}</h1>
      {feature && <p className="text-xl">{t(`feature.${feature}`)}</p>}
      {shown.length === 0 && <p>{t('locks.none')}</p>}
      {shown.map((r) => (
        <Card key={r.key} data-testid="reason">
          <p className="text-2xl font-semibold" data-testid="reason-title">
            {reasonTitle(t, r)}
          </p>
          {r.source === 'offense' && r.detail && <p>{r.detail}</p>}
          {r.source !== 'tier' && r.source !== 'ceiling' && r.source !== 'offline' && (
            <p data-testid="reason-until">
              <EndTime iso={r.ends_at} />
            </p>
          )}
          <h2 className="mt-3 text-xl font-bold">{t('locks.howToAppeal')}</h2>
          <p data-testid="reason-how">{t(`locks.${r.how_to_appeal}`)}</p>
          {r.how_to_appeal === 'appeal' && r.sanction_id != null && (
            <Link
              to={`/resident/appeal/${r.sanction_id}`}
              className="mt-3 inline-block min-h-14 rounded-lg bg-amber-500 px-5 py-3 font-semibold text-black"
            >
              {t('home.appeal')}
            </Link>
          )}
        </Card>
      ))}
    </div>
  )
}

export function Appeal() {
  const { t } = useTranslation()
  const { sanctionId } = useParams()
  const { view, submit } = useResident()
  const [result, setResult] = useState<'sent' | 'queued' | 'duplicate' | null>(null)
  const lock = view?.locks.find((l) => String(l.sanction_id) === sanctionId)
  return (
    <div className="space-y-6">
      <BackLink />
      <h1 className="text-3xl font-bold">{t('locks.appealTitle')}</h1>
      {lock && (
        <Card>
          <p className="text-2xl font-semibold">{reasonTitle(t, lock)}</p>
          <p>
            <EndTime iso={lock.ends_at} />
          </p>
        </Card>
      )}
      {result ? (
        <p role="status" data-testid="appeal-result" className="text-2xl">
          {result === 'queued'
            ? t('locks.appealQueued')
            : result === 'duplicate'
              ? t('locks.appealDuplicate')
              : t('locks.appealDone')}
        </p>
      ) : (
        <button
          onClick={() =>
            void submit({ type: 'appeal', payload: { sanction_id: Number(sanctionId) } }).then(
              setResult,
            )
          }
          className="min-h-16 w-full rounded-xl bg-amber-500 px-6 py-4 text-xl font-bold text-black"
        >
          {t('locks.appealConfirm')}
        </button>
      )}
    </div>
  )
}

export function TierScreen() {
  const { t } = useTranslation()
  const { view } = useResident()
  if (!view) return null
  const { tier } = view
  return (
    <div className="space-y-6">
      <BackLink />
      <h1 className="text-3xl font-bold">{t('tier.label', { n: tier.effective })}</h1>
      <Card>
        <p>{t('tier.points', { count: tier.points })}</p>
        <p>
          {tier.next_tier && !tier.capped_by_ceiling
            ? t('tier.toNext', { count: tier.points_to_next, next: tier.next_tier })
            : t('tier.top')}
        </p>
      </Card>
      {tier.ceiling < 10 && (
        <Card data-testid="ceiling-card">
          <h2 className="text-2xl font-bold" data-testid="ceiling-title">
            {t('tier.ceilingTitle', { n: tier.ceiling })}
          </h2>
          <p>{t('tier.ceilingWhy')}</p>
          {tier.capped_by_ceiling && <p>{t('tier.cappedNote', { n: tier.ceiling })}</p>}
        </Card>
      )}
    </div>
  )
}

export function FeaturePage() {
  const { t } = useTranslation()
  const { name = '' } = useParams()
  const { features } = useResident()
  const navigate = useNavigate()
  const f = features[name]
  if (f && !f.allowed) navigate(`/resident/locks?feature=${name}`, { replace: true })
  return (
    <div className="space-y-6">
      <BackLink />
      <h1 className="text-3xl font-bold">{t(`feature.${name}`)}</h1>
      <p>{t('stub.text')}</p>
      {f && Object.keys(f.limits).length > 0 && (
        <Card>
          <h2 className="font-bold">{t('featurePage.limits')}</h2>
          <ul>
            {Object.entries(f.limits).map(([k, v]) => (
              <li key={k}>
                {k}: {v}
              </li>
            ))}
          </ul>
        </Card>
      )}
      <p className="hidden">
        <Time iso={new Date().toISOString()} />
      </p>
    </div>
  )
}
