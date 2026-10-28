import { CheckCircle2, ChevronRight, Lock as LockIcon, Minus, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { cn } from '../ui/cn'
import { LinkButton } from '../ui/Button'
import { reasonTitle, EndTime } from './components'
import { featureIcon } from './icons'
import type { Feature, Lock, Tier } from './types'

const STEPS = Array.from({ length: 10 }, (_, i) => i + 1)

/**
 * The tier ladder: ten steps that rise left to right. Earned steps are solid, steps still to
 * climb are outlined, and steps above the resident's ceiling are dashed (with the reason on the
 * Tier screen). Drawn as one labelled image so a screen reader gets the sentence, not ten shapes.
 */
export function TierStaircase({ tier }: { tier: Tier }) {
  const { t } = useTranslation()
  return (
    <div
      role="img"
      aria-label={t('tier.ladder', { n: tier.effective })}
      className="flex h-28 items-end gap-1.5"
    >
      {STEPS.map((n) => {
        const earned = n <= tier.effective
        const beyond = n > tier.ceiling
        return (
          <div key={n} className="flex flex-1 flex-col items-center gap-1">
            <div
              className={cn(
                'w-full rounded-t-md border-2',
                earned
                  ? 'border-primary-ink bg-primary-ink'
                  : beyond
                    ? 'border-dashed border-primary-ink/40'
                    : 'border-primary-ink/70',
                n === tier.effective && 'ring-2 ring-primary-ink ring-offset-2 ring-offset-primary',
              )}
              style={{ height: `${18 + n * 7}px` }}
            />
            <span
              className={cn(
                'text-sm leading-none',
                n === tier.effective ? 'font-bold' : 'opacity-80',
              )}
            >
              {n}
            </span>
          </div>
        )
      })}
    </div>
  )
}

export function ProgressMeter({
  pct,
  label,
  tone = 'on-primary',
}: {
  pct: number
  label: string
  tone?: 'on-primary' | 'on-light'
}) {
  const light = tone === 'on-light'
  return (
    <div
      role="progressbar"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
      className={cn(
        'h-4 w-full overflow-hidden rounded-full',
        light ? 'bg-primary-soft' : 'border-2 border-primary-ink/70 bg-primary-ink/15',
      )}
    >
      <div
        className={cn('h-full rounded-full', light ? 'bg-primary' : 'bg-primary-ink')}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

/** Features that the next tier switches on, read from the lock reasons already in the view. */
export function unlockedByNext(features: Record<string, Feature>, next: number | null): string[] {
  if (!next) return []
  return Object.entries(features)
    .filter(
      ([, f]) =>
        !f.allowed && f.reasons.some((r) => r.code === 'TIER_LOCKED' && r.params.tier === next),
    )
    .map(([name]) => name)
}

export function Tile({
  name,
  feature,
  compact = false,
}: {
  name: string
  feature: Feature
  compact?: boolean
}) {
  const { t } = useTranslation()
  const Icon = featureIcon(name)
  const open = feature.allowed
  const reason = feature.reasons[0]
  return (
    <Link
      to={open ? `/resident/feature/${name}` : `/resident/locks?feature=${name}`}
      data-testid={`tile-${name}`}
      data-allowed={open}
      className={cn(
        'group flex items-center gap-4 rounded-card border-2 p-5 transition-colors',
        compact ? 'min-h-touch py-3' : 'min-h-28',
        open
          ? 'border-line bg-surface shadow-card hover:border-primary'
          : 'border-lock bg-lock-soft text-ink hover:brightness-95',
      )}
    >
      <Icon
        aria-hidden="true"
        className={cn(
          'shrink-0',
          compact ? 'size-7' : 'size-10',
          open ? 'text-primary' : 'text-lock',
        )}
        strokeWidth={1.75}
      />
      <span className="min-w-0 flex-1">
        <span className="block text-label font-bold">{t(`feature.${name}`)}</span>
        {!compact && (
          <span
            className={cn(
              'mt-1 flex items-center gap-1.5 text-sm font-bold',
              open ? 'text-ok' : 'text-lock',
            )}
          >
            {open ? (
              <CheckCircle2 aria-hidden="true" className="size-[1em]" strokeWidth={2.5} />
            ) : (
              <LockIcon aria-hidden="true" className="size-[1em]" strokeWidth={2.5} />
            )}
            {open ? t('home.open') : t('home.locked')}
          </span>
        )}
        {!compact && !open && reason && (
          <span className="mt-1 block text-sm text-ink" data-testid={`tile-reason-${name}`}>
            {reasonTitle(t, reason)}
          </span>
        )}
      </span>
      <ChevronRight aria-hidden="true" className="size-6 shrink-0 text-ink-soft" />
    </Link>
  )
}

/** A restriction, in plain words: what, why, until when, what you can do about it. */
export function LockNotice({ lock }: { lock: Lock }) {
  const { t } = useTranslation()
  return (
    <li
      data-testid="lock"
      data-code={lock.code}
      className="rounded-card border-2 border-lock bg-lock-soft p-5"
    >
      <div className="flex gap-4">
        <LockIcon
          aria-hidden="true"
          className="mt-1 size-9 shrink-0 text-lock"
          strokeWidth={1.75}
        />
        <div className="min-w-0 flex-1 space-y-1">
          <p className="text-label font-bold" data-testid="lock-title">
            {reasonTitle(t, lock)}
          </p>
          {lock.source === 'offense' && lock.detail && <p>{lock.detail}</p>}
          <p data-testid="lock-until">
            <EndTime iso={lock.ends_at} />
          </p>
          <p className="text-ink-soft">
            {t('locks.affects', {
              features: lock.features.map((f) => t(`feature.${f}`)).join(', '),
            })}
          </p>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap gap-3">
        {lock.how_to_appeal === 'appeal' &&
          lock.sanction_id != null &&
          (lock.appeal_open ? (
            <span
              className="inline-flex min-h-touch items-center gap-2 rounded-ctl bg-surface px-6 py-3 text-label font-bold"
              data-testid="appeal-sent"
            >
              <CheckCircle2 aria-hidden="true" className="size-6 text-ok" />
              {t('home.appealSent')}
            </span>
          ) : (
            <LinkButton variant="primary" to={`/resident/appeal/${lock.sanction_id}`}>
              {t('home.appeal')}
            </LinkButton>
          ))}
        <LinkButton to={`/resident/locks?lock=${encodeURIComponent(lock.key)}`}>
          {t('home.why')}
        </LinkButton>
      </div>
    </li>
  )
}

/** A − / count / + control with 64 px buttons. Labels are for screen readers; the glyphs are plain. */
export function Stepper({
  value,
  onChange,
  decLabel,
  incLabel,
  testId,
}: {
  value: number
  onChange: (n: number) => void
  decLabel: string
  incLabel: string
  testId: string
}) {
  const btn =
    'inline-flex size-16 items-center justify-center rounded-ctl border-2 border-ink bg-surface text-ink hover:bg-surface-2 disabled:opacity-40'
  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        aria-label={decLabel}
        onClick={() => onChange(value - 1)}
        className={btn}
      >
        <Minus aria-hidden="true" className="size-7" strokeWidth={2.5} />
      </button>
      <span data-testid={testId} className="min-w-8 text-center text-h3 font-bold">
        {value}
      </span>
      <button
        type="button"
        aria-label={incLabel}
        onClick={() => onChange(value + 1)}
        className={btn}
      >
        <Plus aria-hidden="true" className="size-7" strokeWidth={2.5} />
      </button>
    </div>
  )
}
