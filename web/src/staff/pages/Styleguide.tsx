import { Phone, Plus } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Banner } from '../../ui/Banner'
import { Button } from '../../ui/Button'
import { Card } from '../../ui/Card'
import { Notice as InlineNotice } from '../../ui/Notice'
import { EmptyState, ErrorState, LoadingState } from '../../ui/States'
import { StatusBadge } from '../../ui/StatusBadge'
import { ProgressMeter, Tile, TierStaircase } from '../../resident/parts'
import type { Feature, Tier } from '../../resident/types'
import { Badge, Btn, DataTable, Notice, Page, Panel, SimulationBanner } from '../ui'
import type { Column } from '../ui'

// Full class names, so Tailwind sees them (it cannot read `bg-${name}`).
const SWATCHES = [
  ['bg', 'bg-bg'],
  ['surface', 'bg-surface'],
  ['surface-2', 'bg-surface-2'],
  ['ink', 'bg-ink'],
  ['ink-soft', 'bg-ink-soft'],
  ['line', 'bg-line'],
  ['primary', 'bg-primary'],
  ['primary-soft', 'bg-primary-soft'],
  ['ok', 'bg-ok'],
  ['ok-soft', 'bg-ok-soft'],
  ['lock', 'bg-lock'],
  ['lock-soft', 'bg-lock-soft'],
  ['notice', 'bg-notice'],
  ['notice-soft', 'bg-notice-soft'],
  ['danger', 'bg-danger'],
  ['danger-soft', 'bg-danger-soft'],
] as const
const SIZES = [
  ['sm', 'text-sm'],
  ['body', 'text-body'],
  ['label', 'text-label'],
  ['h3', 'text-h3'],
  ['h2', 'text-h2'],
  ['h1', 'text-h1'],
  ['display', 'text-display'],
] as const

const TIER: Tier = {
  earned: 4,
  ceiling: 8,
  effective: 4,
  points: 520,
  next_tier: 5,
  points_to_next: 180,
  capped_by_ceiling: false,
  max_tier_override: null,
}
const OPEN: Feature = { allowed: true, baseline: false, limits: {}, reasons: [] }
const LOCKED: Feature = {
  allowed: false,
  baseline: false,
  limits: {},
  reasons: [
    {
      code: 'TIER_LOCKED',
      source: 'tier',
      how_to_appeal: 'request_staff',
      ends_at: null,
      detail: '',
      params: { tier: 6 },
      sanction_id: null,
    },
  ],
}

interface Row {
  id: number
  name: string
  tier: number
}
const ROWS: Row[] = [
  { id: 1, name: 'SAMPLE-ONE', tier: 3 },
  { id: 2, name: 'SAMPLE-TWO', tier: 7 },
  { id: 3, name: 'SAMPLE-THREE', tier: 5 },
]

/** Every token and component, on one page. It is also the target of the visual-regression test. */
export default function Styleguide() {
  const { t } = useTranslation()
  const [night, setNight] = useState(false)
  const columns: Column<Row>[] = [
    { key: 'name', header: 'Name', sort: (r) => r.name, text: (r) => r.name, cell: (r) => r.name },
    {
      key: 'tier',
      header: 'Tier',
      sort: (r) => r.tier,
      text: (r) => String(r.tier),
      cell: (r) => r.tier,
    },
  ]
  return (
    <Page title={t('staff.styleguide.title')}>
      <p className="max-w-[70ch] text-ink-soft">{t('staff.styleguide.intro')}</p>

      <Panel title={t('staff.styleguide.colors')} data-testid="sg-colors">
        <ul className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {SWATCHES.map(([name, cls]) => (
            <li key={name} className="flex items-center gap-2">
              <span className={`size-8 shrink-0 rounded-ctl border border-line ${cls}`} />
              <code className="text-sm">{name}</code>
            </li>
          ))}
        </ul>
      </Panel>

      <Panel title={t('staff.styleguide.type')}>
        <ul className="space-y-2">
          {SIZES.map(([name, cls]) => (
            <li key={name} className="flex items-baseline gap-4">
              <code className="w-16 shrink-0 text-sm text-ink-soft">{name}</code>
              <span className={cls}>{t('staff.styleguide.sample')}</span>
            </li>
          ))}
        </ul>
      </Panel>

      <Panel title={t('staff.styleguide.buttons')}>
        <div className="flex flex-wrap gap-3">
          <Btn>Primary</Btn>
          <Btn kind="plain">Plain</Btn>
          <Btn kind="danger">Danger</Btn>
          <Btn disabled>Disabled</Btn>
        </div>
      </Panel>

      <Panel title={t('staff.styleguide.status')}>
        <div className="flex flex-wrap gap-3">
          <Badge tone="green">Open</Badge>
          <Badge tone="amber">CELL_MESS ×3</Badge>
          <Badge tone="red">Offline</Badge>
          <Badge>Neutral</Badge>
        </div>
      </Panel>

      <Panel title={t('staff.styleguide.notices')}>
        <div className="space-y-3">
          <Notice kind="ok">Saved.</Notice>
          <Notice kind="err">Something needs your attention.</Notice>
          <SimulationBanner />
        </div>
      </Panel>

      <Panel title={t('staff.styleguide.table')}>
        <DataTable columns={columns} rows={ROWS} rowKey={(r) => r.id} />
      </Panel>

      <Panel title={t('staff.styleguide.tiles')}>
        <label className="mb-3 flex items-center gap-2">
          <input type="checkbox" checked={night} onChange={(e) => setNight(e.target.checked)} />
          Night mode
        </label>
        <div
          // Tiles are real links; in a style guide they must not navigate away.
          onClickCapture={(e) => {
            if ((e.target as HTMLElement).closest('a')) e.preventDefault()
          }}
          className="theme-resident space-y-4 rounded-card bg-bg p-6 text-body text-ink"
          data-mode={night ? 'night' : 'day'}
          data-testid="sg-resident"
        >
          <div className="grid gap-4 md:grid-cols-[22rem_1fr]">
            <div className="space-y-4 rounded-card bg-primary p-6 text-primary-ink">
              <p className="text-h1 font-bold">Tier 4</p>
              <TierStaircase tier={TIER} />
              <ProgressMeter pct={74} label="Progress" />
            </div>
            <div className="grid gap-3">
              <Tile name="calls" feature={OPEN} />
              <Tile name="video" feature={LOCKED} />
            </div>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button variant="primary" icon={Phone}>
              Primary
            </Button>
            <Button icon={Plus}>Secondary</Button>
            <Button variant="quiet">Quiet</Button>
            <Button variant="danger">Danger</Button>
            <StatusBadge tone="ok">Open</StatusBadge>
            <StatusBadge tone="lock">Locked</StatusBadge>
            <StatusBadge tone="notice">Soon</StatusBadge>
          </div>
          <Banner tone="offline">No connection. Your limits shown here are still in effect.</Banner>
          <InlineNotice tone="ok">Your request was sent.</InlineNotice>
          <Card>
            <p>A card.</p>
          </Card>
        </div>
      </Panel>

      <Panel title={t('staff.styleguide.states')}>
        <div className="grid gap-4 md:grid-cols-3">
          <EmptyState title="Nothing here yet">Plain-language next step.</EmptyState>
          <ErrorState title="That did not load" onRetry={() => undefined}>
            Check the connection and try again.
          </ErrorState>
          <LoadingState />
        </div>
      </Panel>
    </Page>
  )
}
