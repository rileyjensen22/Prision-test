import { Link } from 'react-router-dom'

import { fmt } from '../api'
import { Badge, ErrorLine, Page, Table, Td, Th, useLoad } from '../ui'

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

export default function Roster() {
  const { data, error } = useLoad<Row[]>('/staff/roster')
  return (
    <Page title="Roster">
      <ErrorLine error={error} />
      <Table data-testid="roster">
        <thead>
          <tr>
            <Th>Resident</Th>
            <Th>Cell</Th>
            <Th>Tier</Th>
            <Th>Points</Th>
            <Th>Active locks</Th>
            <Th>Pending</Th>
            <Th>Appeals</Th>
            <Th>Last synced</Th>
          </tr>
        </thead>
        <tbody>
          {(data ?? []).map((r) => (
            <tr key={r.resident_id} data-testid={`row-${r.code}`}>
              <Td>
                <Link className="text-blue-700 underline" to={`/staff/residents/${r.resident_id}`}>
                  {r.code}
                </Link>
              </Td>
              <Td>{r.cell ?? '—'}</Td>
              <Td>
                {r.tier.effective}
                {r.tier.ceiling < 10 && (
                  <span className="ml-1 text-gray-500">(ceiling {r.tier.ceiling})</span>
                )}
                {r.tier.earned !== r.tier.effective && (
                  <span className="ml-1 text-gray-500">earned {r.tier.earned}</span>
                )}
              </Td>
              <Td>{r.points}</Td>
              <Td>
                {r.active_sanctions.map((s) => (
                  <Badge key={s.id} tone="amber">
                    {s.code}
                  </Badge>
                ))}
              </Td>
              <Td>{r.pending_sanctions || ''}</Td>
              <Td>{r.open_appeals || ''}</Td>
              <Td>
                {fmt(r.last_sync_at)}{' '}
                {r.offline && (
                  <Badge tone="red" data-testid="offline-badge">
                    offline
                  </Badge>
                )}
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Page>
  )
}
