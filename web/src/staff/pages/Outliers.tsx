import { Badge, ErrorLine, Page, Panel, Table, Td, Th, useLoad } from '../ui'
import { useTranslation } from 'react-i18next'

interface Flag {
  metric: string
  value: number
  peer_mean: number
  z: number
}
interface Row {
  username: string
  reports: number
  sanctions: number
  overturned: number
  rejected: number
  flags: Flag[]
}
interface Data {
  settings: { window_days: number; z_threshold: number; min_peers: number; min_count: number }
  groups: Record<string, Row[]>
  flagged: number
}

const LABEL: Record<string, string> = {
  reports: 'Infractions recorded',
  sanctions: 'Sanctions applied',
  overturn_rate: 'Overturned on appeal',
  rejection_rate: 'Rejected by a supervisor',
}

export default function Outliers() {
  const { t } = useTranslation()

  const { data, error } = useLoad<Data>('/staff/outliers')
  return (
    <Page title={t('staff.pages.Outliers.staffOutlierView')}>
      <ErrorLine error={error} />
      {data && (
        <>
          <p className="text-sm text-ink-soft" data-testid="outlier-settings">
            Last {data.settings.window_days} days, compared with others in the same role. A person
            is flagged when a number is at least {data.settings.z_threshold} standard deviations
            above their peers (needs {data.settings.min_peers}+ peers and {data.settings.min_count}+
            cases). A flag is a prompt to look, not a finding.
          </p>
          {Object.entries(data.groups).map(([role, rows]) => (
            <Panel key={role} title={`${role[0].toUpperCase()}${role.slice(1)}s`}>
              <Table data-testid={`outliers-${role}`}>
                <thead>
                  <tr>
                    <Th>{t('staff.pages.Outliers.who')}</Th>
                    <Th>{t('staff.pages.Outliers.recorded')}</Th>
                    <Th>{t('staff.pages.Outliers.applied')}</Th>
                    <Th>{t('staff.pages.Outliers.overturned')}</Th>
                    <Th>{t('staff.pages.Outliers.rejected')}</Th>
                    <Th>{t('staff.pages.Outliers.flags')}</Th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.username} data-testid={`outlier-${r.username}`}>
                      <Td>{r.username}</Td>
                      <Td>{r.reports}</Td>
                      <Td>{r.sanctions}</Td>
                      <Td>{r.overturned}</Td>
                      <Td>{r.rejected}</Td>
                      <Td>
                        {r.flags.map((f) => (
                          <Badge key={f.metric} tone="red">
                            {LABEL[f.metric]}: {f.value} vs peers {f.peer_mean}
                          </Badge>
                        ))}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </Panel>
          ))}
        </>
      )}
    </Page>
  )
}
