import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'

import {
  CheckCircle2,
  ChevronRight,
  ListOrdered,
  Lock,
  Send,
  Sprout,
  Wrench,
  type LucideIcon,
} from 'lucide-react'

import { LinkButton, Button } from '../ui/Button'
import { Card, EndTime, ScreenFrame, Time, reasonTitle } from './components'
import { featureIcon } from './icons'
import { LockNotice, ProgressMeter, Tile, TierStaircase, unlockedByNext } from './parts'
import { money } from './features/helpers'
import { useResident } from './ResidentContext'
import type { Tier } from './types'

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
  const next = tier.capped_by_ceiling ? null : tier.next_tier
  const nextUnlocks = unlockedByNext(features, next)

  return (
    <div className="mx-auto grid w-full gap-6 lg:grid-cols-[clamp(20rem,30vw,26rem)_1fr] lg:items-start">
      <aside className="lg:sticky lg:top-6">
        <section
          data-testid="tier-card"
          className="space-y-5 rounded-card bg-primary p-6 text-primary-ink"
        >
          <div className="flex items-baseline justify-between gap-3">
            <h1 className="text-h1 font-bold" data-testid="tier-label">
              {t('tier.label', { n: tier.effective })}
            </h1>
            <span className="text-body">{t('tier.points', { count: tier.points })}</span>
          </div>
          <TierStaircase tier={tier} />
          <ProgressMeter pct={pct} label={t('tier.label', { n: tier.effective })} />
          <p className="text-body font-bold" data-testid="next-tier">
            {tier.next_tier && !tier.capped_by_ceiling
              ? t('tier.toNext', { count: tier.points_to_next, next: tier.next_tier })
              : tier.capped_by_ceiling
                ? t('tier.cappedNote', { n: tier.ceiling })
                : t('tier.top')}
          </p>
          {nextUnlocks.length > 0 && (
            <div className="rounded-ctl bg-primary-ink/10 p-4">
              <p className="text-sm font-bold">{t('tier.unlocksNext', { n: next })}</p>
              <ul className="mt-1 space-y-1 text-body">
                {nextUnlocks.map((f) => (
                  <li key={f}>{t(`feature.${f}`)}</li>
                ))}
              </ul>
            </div>
          )}
          <LinkButton
            to="/resident/tier"
            icon={ListOrdered}
            className="w-full border-2 border-primary-ink bg-transparent text-primary-ink hover:bg-primary-ink/10"
          >
            {t('tier.details')}
          </LinkButton>
        </section>
        {view.reentry && (
          <Link
            to="/resident/reentry"
            data-testid="release-countdown"
            className="mt-4 flex items-center gap-4 rounded-card border border-line bg-surface p-5 shadow-card"
          >
            <Sprout
              aria-hidden="true"
              className="size-9 shrink-0 text-primary"
              strokeWidth={1.75}
            />
            <span>
              <span className="block text-sm text-ink-soft">{t('reentry.countdownLabel')}</span>
              <span className="block text-h3 font-bold">
                {t('reentry.daysLeft', { count: view.reentry.days_left })}
              </span>
            </span>
          </Link>
        )}
      </aside>

      <div className="space-y-8">
        <section data-testid="locks-card" aria-labelledby="h-locks" className="space-y-3">
          <h2 id="h-locks" className="text-h2 font-bold">
            {t('home.locks')}
          </h2>
          {view.locks.length === 0 ? (
            <p className="flex items-center gap-3 rounded-card border border-line bg-surface p-5 shadow-card">
              <CheckCircle2 aria-hidden="true" className="size-8 shrink-0 text-ok" />
              {t('home.noLocks')}
            </p>
          ) : (
            <ul className="space-y-4">
              {view.locks.map((lock) => (
                <LockNotice key={lock.key} lock={lock} />
              ))}
            </ul>
          )}
        </section>

        {view.allowances.length > 0 && (
          <section data-testid="allowances" aria-labelledby="h-allow" className="space-y-3">
            <h2 id="h-allow" className="text-h2 font-bold">
              {t('home.allowances')}
            </h2>
            <ul className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(18rem,1fr))]">
              {view.allowances.map((a) => {
                const Icon = featureIcon(a.feature)
                return (
                  <li
                    key={`${a.feature}-${a.unit}`}
                    data-testid={`allowance-${a.feature}`}
                    className="flex items-center gap-3 rounded-card border border-line bg-surface p-4 shadow-card"
                  >
                    <Icon
                      aria-hidden="true"
                      className="size-8 shrink-0 text-primary"
                      strokeWidth={1.75}
                    />
                    <span>
                      <span className="block font-bold">{t(`feature.${a.feature}`)}:</span>
                      <span className="block">
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
                      </span>
                    </span>
                  </li>
                )
              })}
            </ul>
          </section>
        )}

        <section aria-labelledby="h-services" className="space-y-3">
          <h2 id="h-services" className="text-h2 font-bold">
            {t('home.services')}
          </h2>
          <ul className="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(20rem,1fr))]">
            {services.map(([name, f]) => (
              <li key={name}>
                <Tile name={name} feature={f} />
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="h-optional" className="space-y-3">
          <h2 id="h-optional" className="text-h2 font-bold">
            {t('home.optional')}
          </h2>
          <ul className="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(20rem,1fr))]">
            <li>
              <OptionalLink to="/resident/reentry" testId="reentry-link" icon={Sprout}>
                {t('home.reentryLink')}
              </OptionalLink>
            </li>
            <li>
              <OptionalLink to="/resident/jobs" testId="jobs-link" icon={Wrench}>
                {t('home.jobsLink')}
              </OptionalLink>
            </li>
          </ul>
        </section>

        <section aria-labelledby="h-always" className="space-y-3">
          <h2 id="h-always" className="text-h2 font-bold">
            {t('home.always')}
          </h2>
          <ul className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(18rem,1fr))]">
            {ALWAYS_ORDER.filter((n) => features[n]).map((name) => (
              <li key={name}>
                <Tile name={name} feature={features[name]} compact />
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}

function OptionalLink({
  to,
  testId,
  icon: Icon,
  children,
}: {
  to: string
  testId: string
  icon: LucideIcon
  children: string
}) {
  return (
    <Link
      to={to}
      data-testid={testId}
      className="flex min-h-touch items-center gap-4 rounded-card border-2 border-line bg-surface p-5 text-label font-bold hover:border-primary"
    >
      <Icon aria-hidden="true" className="size-8 shrink-0 text-primary" strokeWidth={1.75} />
      <span className="flex-1">{children}</span>
      <ChevronRight aria-hidden="true" className="size-6 text-ink-soft" />
    </Link>
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
    <ScreenFrame
      title={t('locks.title')}
      intro={feature ? t(`feature.${feature}`) : undefined}
      narrow
    >
      {shown.length === 0 && <p className="text-body">{t('locks.none')}</p>}
      {shown.map((r) => (
        <Card
          key={r.key}
          data-testid="reason"
          className="space-y-4 border-2 border-lock bg-lock-soft"
        >
          <div className="flex gap-4">
            <Lock
              aria-hidden="true"
              className="mt-1 size-9 shrink-0 text-lock"
              strokeWidth={1.75}
            />
            <div className="space-y-1">
              <p className="text-h3 font-bold" data-testid="reason-title">
                {reasonTitle(t, r)}
              </p>
              {r.source === 'offense' && r.detail && <p>{r.detail}</p>}
              {r.source !== 'tier' && r.source !== 'ceiling' && r.source !== 'offline' && (
                <p data-testid="reason-until">
                  <EndTime iso={r.ends_at} />
                </p>
              )}
            </div>
          </div>
          <div className="rounded-ctl bg-surface p-4">
            <h2 className="text-label font-bold">{t('locks.howToAppeal')}</h2>
            <p data-testid="reason-how">{t(`locks.${r.how_to_appeal}`)}</p>
          </div>
          {r.how_to_appeal === 'appeal' && r.sanction_id != null && (
            <LinkButton variant="primary" to={`/resident/appeal/${r.sanction_id}`}>
              {t('home.appeal')}
            </LinkButton>
          )}
        </Card>
      ))}
    </ScreenFrame>
  )
}

export function Appeal() {
  const { t } = useTranslation()
  const { sanctionId } = useParams()
  const { view, submit } = useResident()
  const [result, setResult] = useState<'sent' | 'queued' | 'duplicate' | null>(null)
  const lock = view?.locks.find((l) => String(l.sanction_id) === sanctionId)
  return (
    <ScreenFrame title={t('locks.appealTitle')} narrow>
      {lock && (
        <Card className="space-y-1 border-2 border-lock bg-lock-soft">
          <p className="text-h3 font-bold">{reasonTitle(t, lock)}</p>
          <p>
            <EndTime iso={lock.ends_at} />
          </p>
        </Card>
      )}
      {result ? (
        <p
          role="status"
          data-testid="appeal-result"
          className="flex items-center gap-3 rounded-card border-2 border-ok bg-ok-soft p-6 text-label font-bold"
        >
          <CheckCircle2 aria-hidden="true" className="size-8 shrink-0 text-ok" />
          {result === 'queued'
            ? t('locks.appealQueued')
            : result === 'duplicate'
              ? t('locks.appealDuplicate')
              : t('locks.appealDone')}
        </p>
      ) : (
        <Button
          variant="primary"
          icon={Send}
          className="self-start"
          onClick={() =>
            void submit({ type: 'appeal', payload: { sanction_id: Number(sanctionId) } }).then(
              setResult,
            )
          }
        >
          {t('locks.appealConfirm')}
        </Button>
      )}
    </ScreenFrame>
  )
}

export function TierScreen() {
  const { t } = useTranslation()
  const { view } = useResident()
  if (!view) return null
  const { tier } = view
  return (
    <ScreenFrame title={t('tier.label', { n: tier.effective })} narrow>
      <Card className="space-y-4">
        <TierRail tier={tier} />
        <p className="text-label font-bold">{t('tier.points', { count: tier.points })}</p>
        {!tier.capped_by_ceiling && (
          <p>
            {tier.next_tier
              ? t('tier.toNext', { count: tier.points_to_next, next: tier.next_tier })
              : t('tier.top')}
          </p>
        )}
      </Card>
      {tier.ceiling < 10 && (
        <Card data-testid="ceiling-card" className="space-y-2">
          <h2 className="text-h3 font-bold" data-testid="ceiling-title">
            {t('tier.ceilingTitle', { n: tier.ceiling })}
          </h2>
          <p>{t('tier.ceilingWhy')}</p>
          {tier.capped_by_ceiling && <p>{t('tier.cappedNote', { n: tier.ceiling })}</p>}
        </Card>
      )}
    </ScreenFrame>
  )
}

/** The staircase again, on a light surface, for the detail screen. */
function TierRail({ tier }: { tier: Tier }) {
  return (
    <div className="rounded-ctl bg-primary p-4 text-primary-ink">
      <TierStaircase tier={tier} />
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
  const Icon = featureIcon(name)
  return (
    <ScreenFrame title={t(`feature.${name}`)} intro={t('stub.text')} narrow>
      <Card className="flex items-center gap-4">
        <Icon aria-hidden="true" className="size-12 text-primary" strokeWidth={1.5} />
        {f && Object.keys(f.limits).length > 0 ? (
          <div>
            <h2 className="font-bold">{t('featurePage.limits')}</h2>
            <ul>
              {Object.entries(f.limits).map(([k, v]) => (
                <li key={k}>
                  {k}: {v}
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p>{t('stub.text')}</p>
        )}
      </Card>
      <p className="hidden">
        <Time iso={new Date().toISOString()} />
      </p>
    </ScreenFrame>
  )
}
