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
import { useResident } from './ResidentContext'
import type { Tier } from './types'

const ALWAYS_ORDER = [
  'attorney_calls',
  'contact_requests',
  'legal_materials',
  'grievances_appeals',
  'health_requests',
  'basic_education',
  'reentry',
] // request_staff is the persistent button; emergency_contact / out_of_cell_minimum are not tiled

// Display order for services (lower tier = earlier in list)
const SERVICE_ORDER = [
  'calls', 'commissary', 'reading_general', 'chess', 'advanced_education',
  'texting', 'video', 'outdoor_rec',
]

export function Home() {
  const { t } = useTranslation()
  const { view, features } = useResident()
  if (!view) return null
  const { tier } = view
  const pct = tier.next_tier
    ? Math.min(100, Math.round((tier.points / (tier.points + (tier.points_to_next ?? 1))) * 100))
    : 100
  const services = Object.entries(features)
    .filter(([, f]) => !f.baseline)
    .sort(([a], [b]) => {
      const ai = SERVICE_ORDER.indexOf(a)
      const bi = SERVICE_ORDER.indexOf(b)
      if (ai === -1 && bi === -1) return 0
      if (ai === -1) return 1
      if (bi === -1) return -1
      return ai - bi
    })
  const next = tier.capped_by_ceiling ? null : tier.next_tier
  const nextUnlocks = unlockedByNext(features, next)

  return (
    <div className="mx-auto grid w-full gap-6 min-[1180px]:grid-cols-[clamp(20rem,30vw,26rem)_1fr] min-[1180px]:items-start">
      <aside className="min-[1180px]:sticky min-[1180px]:top-6">
        <section
          data-testid="tier-card"
          className="space-y-5 rounded-card bg-primary p-6 text-primary-ink"
        >
          <div className="flex flex-wrap items-baseline justify-between gap-x-3">
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
              <OptionalLink to="/resident/jobs" testId="jobs-link" icon={Wrench}>
                {t('home.jobsLink')}
              </OptionalLink>
            </li>
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

// Tier feature data — matches tiers.yaml
const TIER_DATA = [
  { calls: 15, texts: 0, video: 0, commissary: 20, chess: 'none', rec: 0 },
  { calls: 20, texts: 0, video: 0, commissary: 30, chess: 'engine', rec: 0 },
  { calls: 30, texts: 0, video: 0, commissary: 40, chess: 'engine', rec: 0 },
  { calls: 30, texts: 10, video: 0, commissary: 50, chess: 'engine', rec: 0 },
  { calls: 40, texts: 20, video: 0, commissary: 60, chess: 'human', rec: 0 },
  { calls: 45, texts: 30, video: 30, commissary: 70, chess: 'human', rec: 0 },
  { calls: 60, texts: 40, video: 60, commissary: 70, chess: 'human', rec: 0 },
  { calls: 60, texts: 50, video: 75, commissary: 70, chess: 'human', rec: 60 },
  { calls: 75, texts: 60, video: 75, commissary: 70, chess: 'human', rec: 60 },
  { calls: 90, texts: 75, video: 75, commissary: 70, chess: 'human', rec: 60 },
]

const POINT_EVENTS = [
  { label: 'Clean day (no infractions)', points: '+2' },
  { label: 'Basic course completed', points: '+50' },
  { label: 'Advanced course completed', points: '+100' },
  { label: 'Program / certificate completed', points: '+200' },
  { label: 'Staff commendation', points: '+10' },
]

const POINT_LOSSES = [
  { label: 'Minor infraction confirmed', points: '−25' },
  { label: 'Major infraction confirmed', points: '−100' },
]

const THRESHOLDS = [0, 100, 250, 450, 700, 1000, 1400, 1900, 2500, 3200]

export function TierScreen() {
  const { t } = useTranslation()
  const { view } = useResident()
  if (!view) return null
  const { tier } = view
  const [selected, setSelected] = useState(tier.effective)

  const td = TIER_DATA[selected - 1]
  const chessLabel =
    td.chess === 'none' ? 'No chess' : td.chess === 'engine' ? 'vs. computer' : 'vs. people or computer'

  return (
    <ScreenFrame title={t('tier.details')}>
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

      <Card className="space-y-4">
        <h2 className="text-h3 font-bold">What each tier includes</h2>
        <div className="flex flex-wrap gap-2">
          {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => {
            const isLocked = n > tier.effective
            const isCurrent = n === tier.effective
            return (
              <button
                key={n}
                onClick={() => setSelected(n)}
                className={`relative min-h-touch min-w-[3.5rem] rounded-ctl border-2 px-3 py-2 text-label font-bold transition-colors ${
                  n === selected
                    ? 'border-primary bg-primary text-primary-ink'
                    : isCurrent
                      ? 'border-primary bg-primary/10 text-primary'
                      : isLocked
                        ? 'border-line bg-surface/60 text-ink-soft'
                        : 'border-line bg-surface hover:border-primary'
                }`}
                aria-pressed={n === selected}
                aria-label={`Tier ${n}${isLocked ? ' (locked)' : isCurrent ? ' (current)' : ''}`}
              >
                <span className="flex items-center justify-center gap-1">
                  T{n}
                  {isLocked && <Lock aria-hidden="true" className="size-3 opacity-60" />}
                </span>
              </button>
            )
          })}
        </div>
        {selected === tier.effective && (
          <p className="text-sm font-bold text-ok">← Your current tier</p>
        )}
        {selected > tier.ceiling && (
          <p className="text-sm text-lock">Above your current ceiling (T{tier.ceiling})</p>
        )}
        <table className="w-full text-body">
          <tbody className="divide-y divide-line">
            <tr>
              <td className="py-2 text-ink-soft">Phone calls</td>
              <td className="py-2 font-bold">{td.calls} min/day</td>
            </tr>
            <tr>
              <td className="py-2 text-ink-soft">Text messages</td>
              <td className="py-2 font-bold">{td.texts === 0 ? 'Not available' : `${td.texts}/day`}</td>
            </tr>
            <tr>
              <td className="py-2 text-ink-soft">Video calls</td>
              <td className="py-2 font-bold">{td.video === 0 ? 'Not available' : `${td.video} min/day`}</td>
            </tr>
            <tr>
              <td className="py-2 text-ink-soft">Commissary</td>
              <td className="py-2 font-bold">${td.commissary}/week</td>
            </tr>
            <tr>
              <td className="py-2 text-ink-soft">Chess</td>
              <td className="py-2 font-bold">{chessLabel}</td>
            </tr>
            <tr>
              <td className="py-2 text-ink-soft">Outdoor rec</td>
              <td className="py-2 font-bold">{td.rec === 0 ? 'Not available' : `${td.rec} min/day`}</td>
            </tr>
          </tbody>
        </table>
        <p className="text-sm text-ink-soft">
          Points needed to reach T{selected}: {THRESHOLDS[selected - 1].toLocaleString()}
          {selected < 10 && ` · T${selected + 1} requires ${THRESHOLDS[selected].toLocaleString()}`}
        </p>
      </Card>

      <Card className="space-y-3">
        <h2 className="text-h3 font-bold">How you earn points</h2>
        <table className="w-full text-body">
          <tbody className="divide-y divide-line">
            {POINT_EVENTS.map((e) => (
              <tr key={e.label}>
                <td className="py-2">{e.label}</td>
                <td className="py-2 font-bold text-ok">{e.points}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card className="space-y-3">
        <h2 className="text-h3 font-bold">How you lose points</h2>
        <table className="w-full text-body">
          <tbody className="divide-y divide-line">
            {POINT_LOSSES.map((e) => (
              <tr key={e.label}>
                <td className="py-2">{e.label}</td>
                <td className="py-2 font-bold text-lock">{e.points}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="text-sm text-ink-soft">Points never go below 0. Tier can drop at most one level per week.</p>
      </Card>
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
    <ScreenFrame title={t(`feature.${name}`)} narrow>
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
          <p>This feature is available from this device. Please speak with staff if you have questions.</p>
        )}
      </Card>
      <p className="hidden">
        <Time iso={new Date().toISOString()} />
      </p>
    </ScreenFrame>
  )
}
