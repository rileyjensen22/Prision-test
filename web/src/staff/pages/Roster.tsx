import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router-dom'

import { fmt } from '../api'
import { Badge, Btn, DataTable, ErrorLine, FIELD, Page, useLoad } from '../ui'
import type { Column } from '../ui'
import type { Overview } from './FacilityOverview'

const PAGE = 100

interface Row {
  resident_id: number
  code: string
  cell: string | null
  hub: string | null
  line: string | null
  floor: number | null
  device: string | null
  last_sync_at: string | null
  offline: boolean
  tier: { earned: number; ceiling: number; effective: number }
  points: number
  active_sanctions: { id: number; code: string; ends_at: string }[]
  pending_sanctions: number
  open_appeals: number
}

/** "CELL_MESS CELL_MESS CELL_MESS" reads as "CELL_MESS ×3". */
function groupCodes(list: Row['active_sanctions']): [string, number][] {
  const counts = new Map<string, number>()
  for (const s of list) counts.set(s.code, (counts.get(s.code) ?? 0) + 1)
  return [...counts]
}

export default function Roster() {
  const { t } = useTranslation()
  const [params, setParams] = useSearchParams()
  const hub = params.get('hub') ?? ''
  const line = params.get('line') ?? ''
  const floor = params.get('floor') ?? ''
  const q = params.get('q') ?? ''
  const page = Math.max(0, Number(params.get('page') ?? 0))
  const query = new URLSearchParams({ limit: String(PAGE), offset: String(page * PAGE) })
  for (const [k, v] of Object.entries({ hub, line, floor, q })) if (v) query.set(k, v)
  const { data, error } = useLoad<{ total: number; rows: Row[] }>(`/staff/roster/page?${query}`)
  const overview = useLoad<Overview>('/staff/facility/overview').data
  const hubs = overview?.hubs ?? []
  const lines = hubs.filter((h) => !hub || h.code === hub).flatMap((h) => h.lines)
  const total = data?.total ?? 0

  function set(next: Record<string, string>) {
    const p = new URLSearchParams(params)
    for (const [k, v] of Object.entries({ page: '', ...next })) {
      if (v) p.set(k, v)
      else p.delete(k)
    }
    setParams(p)
  }

  const columns: Column<Row>[] = [
    {
      key: 'resident',
      header: t('staff.roster.resident'),
      sort: (r) => r.code,
      text: (r) => r.code,
      cell: (r) => (
        <Link className="font-bold text-primary underline" to={`/staff/residents/${r.resident_id}`}>
          {r.code}
        </Link>
      ),
    },
    {
      key: 'cell',
      header: t('staff.roster.cell'),
      sort: (r) => r.cell ?? '',
      text: (r) => r.cell ?? '',
      cell: (r) => <span className="whitespace-nowrap">{r.cell ?? '—'}</span>,
    },
    {
      key: 'where',
      header: t('staff.roster.where'),
      sort: (r) => `${r.line ?? ''}${r.floor ?? ''}`,
      text: (r) => `${r.line ?? ''} ${r.floor ?? ''}`,
      cell: (r) => (
        <span className="whitespace-nowrap">
          {r.line ? `${r.line} · ${t('staff.facility.floor', { n: r.floor })}` : '—'}
        </span>
      ),
    },
    {
      key: 'tier',
      header: t('staff.roster.tier'),
      sort: (r) => r.tier.effective,
      text: (r) => `tier ${r.tier.effective}`,
      cell: (r) => (
        <span className="whitespace-nowrap">
          <strong>{r.tier.effective}</strong>
          {r.tier.ceiling < 10 && (
            <span className="ml-1 text-ink-soft">
              ({t('staff.roster.ceiling', { n: r.tier.ceiling })})
            </span>
          )}
          {r.tier.earned !== r.tier.effective && (
            <span className="ml-1 text-ink-soft">
              {t('staff.roster.earned', { n: r.tier.earned })}
            </span>
          )}
        </span>
      ),
    },
    {
      key: 'points',
      header: t('staff.roster.points'),
      sort: (r) => r.points,
      text: (r) => String(r.points),
      cell: (r) => <span className="tabular-nums">{r.points}</span>,
    },
    {
      key: 'locks',
      header: t('staff.roster.locks'),
      sort: (r) => r.active_sanctions.length,
      text: (r) => r.active_sanctions.map((s) => s.code).join(' '),
      cell: (r) => (
        <span className="flex flex-wrap gap-1">
          {groupCodes(r.active_sanctions).map(([code, n]) => (
            <Badge key={code} tone="amber">
              {code}
              {n > 1 && ` ×${n}`}
            </Badge>
          ))}
        </span>
      ),
    },
    {
      key: 'pending',
      header: t('staff.roster.pending'),
      sort: (r) => r.pending_sanctions,
      cell: (r) => (r.pending_sanctions ? <Badge tone="amber">{r.pending_sanctions}</Badge> : ''),
    },
    {
      key: 'appeals',
      header: t('staff.roster.appeals'),
      sort: (r) => r.open_appeals,
      cell: (r) => (r.open_appeals ? <Badge tone="amber">{r.open_appeals}</Badge> : ''),
    },
    {
      key: 'synced',
      header: t('staff.roster.synced'),
      sort: (r) => r.last_sync_at ?? '',
      cell: (r) => (
        <span className="flex flex-wrap items-center gap-2">
          <span>{r.last_sync_at ? fmt(r.last_sync_at) : t('staff.roster.never')}</span>
          {r.offline && (
            <Badge tone="red" data-testid="offline-badge">
              {t('staff.status.offline')}
            </Badge>
          )}
        </span>
      ),
    },
  ]

  return (
    <Page title={t('staff.roster.title')}>
      <ErrorLine error={error} />
      <div className="flex flex-wrap items-end gap-3" data-testid="roster-filters">
        {hubs.length > 0 && (
          <>
            <label className="text-sm">
              {t('staff.roster.hub')}
              <select
                className={FIELD}
                value={hub}
                onChange={(e) => set({ hub: e.target.value, line: '', floor: '' })}
              >
                <option value="">{t('staff.roster.all')}</option>
                {hubs.map((h) => (
                  <option key={h.code}>{h.code}</option>
                ))}
              </select>
            </label>
            <label className="text-sm">
              {t('staff.roster.line')}
              <select
                className={FIELD}
                value={line}
                onChange={(e) => set({ hub, line: e.target.value, floor: '' })}
              >
                <option value="">{t('staff.roster.all')}</option>
                {lines.map((l) => (
                  <option key={l.code}>{l.code}</option>
                ))}
              </select>
            </label>
            <label className="text-sm">
              {t('staff.roster.floor')}
              <select
                className={FIELD}
                value={floor}
                onChange={(e) => set({ hub, line, floor: e.target.value })}
              >
                <option value="">{t('staff.roster.all')}</option>
                {[1, 2, 3, 4].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}
        <label className="text-sm">
          {t('staff.roster.search')}
          <input
            className={FIELD}
            defaultValue={q}
            onKeyDown={(e) => {
              if (e.key === 'Enter') set({ hub, line, floor, q: e.currentTarget.value.trim() })
            }}
            placeholder={t('staff.roster.searchHint')}
          />
        </label>
      </div>
      <DataTable
        columns={columns}
        rows={data?.rows ?? []}
        rowKey={(r) => r.resident_id}
        testId="roster"
        rowTestId={(r) => `row-${r.code}`}
      />
      {total > PAGE && (
        <div className="flex items-center gap-3" data-testid="roster-pager">
          <Btn
            kind="plain"
            disabled={page === 0}
            onClick={() => set({ hub, line, floor, q, page: String(page - 1) })}
          >
            {t('staff.roster.previous')}
          </Btn>
          <span>
            {t('staff.roster.showing', {
              from: page * PAGE + 1,
              to: Math.min(total, (page + 1) * PAGE),
              total,
            })}
          </span>
          <Btn
            kind="plain"
            disabled={(page + 1) * PAGE >= total}
            onClick={() => set({ hub, line, floor, q, page: String(page + 1) })}
          >
            {t('staff.roster.next')}
          </Btn>
        </div>
      )}
    </Page>
  )
}
