import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { fmt } from '../api'
import { Badge, DataTable, ErrorLine, Page, useLoad } from '../ui'
import type { Column } from '../ui'

interface Row {
  resident_id: number
  code: string
  cell: string | null
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
  const { data, error } = useLoad<Row[]>('/staff/roster')

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
      <DataTable
        columns={columns}
        rows={data ?? []}
        rowKey={(r) => r.resident_id}
        testId="roster"
        rowTestId={(r) => `row-${r.code}`}
      />
    </Page>
  )
}
