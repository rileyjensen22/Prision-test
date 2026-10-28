import { ChevronRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { Panel, useLoad } from '../ui'

interface Counts {
  cells: number
  occupied: number
  offline: number
  locked: number
}
interface Floor extends Counts {
  level: number
}
interface Line extends Counts {
  code: string
  floors: Floor[]
}
interface Hub extends Counts {
  code: string
  lines: Line[]
}
export interface Overview {
  hubs: Hub[]
  total: Counts
}

function Numbers({ c }: { c: Counts }) {
  const { t } = useTranslation()
  return (
    <span className="ml-auto flex flex-wrap gap-x-4 gap-y-1 text-sm tabular-nums">
      <span>{t('staff.facility.occupied', { n: c.occupied, cells: c.cells })}</span>
      <span className={c.offline ? 'font-bold text-notice' : 'text-ink-soft'}>
        {t('staff.facility.offline', { n: c.offline })}
      </span>
      <span className={c.locked ? 'font-bold text-notice' : 'text-ink-soft'}>
        {t('staff.facility.locked', { n: c.locked })}
      </span>
    </span>
  )
}

/** Cells, devices and locks by hub, then line, then floor. A floor opens its roster. */
export function FacilityOverview() {
  const { t } = useTranslation()
  const { data } = useLoad<Overview>('/staff/facility/overview')
  if (!data || data.hubs.length === 0) return null
  return (
    <Panel title={t('staff.facility.title')}>
      <div className="space-y-2" data-testid="facility-overview">
        {data.hubs.map((hub) => (
          <details
            key={hub.code}
            className="rounded-ctl border border-line"
            open={data.hubs.length === 1}
          >
            <summary className="flex min-h-touch cursor-pointer flex-wrap items-center gap-3 px-3 py-2 font-bold">
              <ChevronRight aria-hidden="true" className="size-4" />
              {t('staff.facility.hub', { code: hub.code })}
              <Numbers c={hub} />
            </summary>
            <div className="space-y-1 px-3 pb-3">
              {hub.lines.map((line) => (
                <details key={line.code} className="rounded-ctl border border-line">
                  <summary className="flex min-h-touch cursor-pointer flex-wrap items-center gap-3 px-3 py-1">
                    <ChevronRight aria-hidden="true" className="size-4" />
                    {t('staff.facility.line', { code: line.code })}
                    <Numbers c={line} />
                  </summary>
                  <ul className="px-3 pb-2">
                    {line.floors.map((f) => (
                      <li key={f.level}>
                        <Link
                          className="flex min-h-touch flex-wrap items-center gap-3 rounded-ctl px-2 py-1 hover:bg-primary-soft"
                          to={`/staff/roster?hub=${hub.code}&line=${line.code}&floor=${f.level}`}
                          data-testid={`floor-${line.code}-${f.level}`}
                        >
                          {t('staff.facility.floor', { n: f.level })}
                          <Numbers c={f} />
                        </Link>
                      </li>
                    ))}
                  </ul>
                </details>
              ))}
            </div>
          </details>
        ))}
      </div>
    </Panel>
  )
}
