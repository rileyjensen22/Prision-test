import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { errorText, fmt, post } from '../api'
import { useAuth } from '../auth'
import { Badge, Btn, ErrorLine, FIELD, Notice, Page, Panel, Table, Td, Th, useLoad } from '../ui'
import type { Overview } from './FacilityOverview'

interface Row {
  device: string
  paired: boolean
  cell: string | null
  resident: string | null
  last_seen: string | null
  offline: boolean
  health: {
    storage_used_mb?: number
    storage_quota_mb?: number
    camera?: string
    microphone?: string
    app_version?: string
    queue_pending?: number
  } | null
  locked_until: string | null
}

const mb = (n?: number) => (n === undefined ? '—' : `${n} MB`)
const LIMIT = 200

export default function Devices() {
  const { t } = useTranslation()

  const { user } = useAuth()
  const [hub, setHub] = useState('')
  const [line, setLine] = useState('')
  const [offlineOnly, setOfflineOnly] = useState(false)
  const query = new URLSearchParams({ limit: String(LIMIT) })
  if (hub) query.set('hub', hub)
  if (line) query.set('line', line)
  if (offlineOnly) query.set('offline_only', 'true')
  const { data, error, reload } = useLoad<Row[]>(`/staff/devices?${query}`)
  const hubs = useLoad<Overview>('/staff/facility/overview').data?.hubs ?? []
  const lines = hubs.filter((h) => !hub || h.code === hub).flatMap((h) => h.lines)
  const isAdmin = user?.role === 'admin'
  const canPair = !!user && ['supervisor', 'admin'].includes(user.role)
  const [newCode, setNewCode] = useState('')
  const [reason, setReason] = useState('')
  const [hours, setHours] = useState(2)
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)
  const [pairing, setPairing] = useState<{
    device: string
    code: string
    expires_at: string
  } | null>(null)

  async function act(label: string, fn: () => Promise<unknown>) {
    try {
      await fn()
      setMsg({ kind: 'ok', text: label })
      await reload()
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  return (
    <Page title={t('staff.pages.Devices.devices')}>
      <ErrorLine error={error} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      {pairing && (
        <Panel title={`Setup code for ${pairing.device}`}>
          <p className="font-mono text-h1" data-testid="pairing-code">
            {pairing.code}
          </p>
          <p className="text-sm">
            Type it on the device. It works once and expires at {fmt(pairing.expires_at)}. It is not
            shown again.
          </p>
        </Panel>
      )}
      <div className="flex flex-wrap items-end gap-3" data-testid="device-filters">
        {hubs.length > 0 && (
          <>
            <label className="text-sm">
              {t('staff.roster.hub')}
              <select
                className={FIELD}
                value={hub}
                onChange={(e) => {
                  setHub(e.target.value)
                  setLine('')
                }}
              >
                <option value="">{t('staff.roster.all')}</option>
                {hubs.map((h) => (
                  <option key={h.code}>{h.code}</option>
                ))}
              </select>
            </label>
            <label className="text-sm">
              {t('staff.roster.line')}
              <select className={FIELD} value={line} onChange={(e) => setLine(e.target.value)}>
                <option value="">{t('staff.roster.all')}</option>
                {lines.map((l) => (
                  <option key={l.code}>{l.code}</option>
                ))}
              </select>
            </label>
          </>
        )}
        <label className="flex min-h-touch items-center gap-2">
          <input
            type="checkbox"
            checked={offlineOnly}
            onChange={(e) => setOfflineOnly(e.target.checked)}
          />
          {t('staff.devicesPage.offlineOnly')}
        </label>
        {(data?.length ?? 0) >= LIMIT && (
          <span className="text-sm text-ink-soft">
            {t('staff.devicesPage.capped', { n: LIMIT })}
          </span>
        )}
      </div>
      {isAdmin && (
        <Panel title={t('staff.pages.Devices.enrollADevice')}>
          <div className="flex flex-wrap gap-2">
            <input
              aria-label={t('staff.pages.Devices.newDeviceCode')}
              placeholder={t('staff.pages.Devices.deviceCode')}
              className="rounded-ctl border px-2 py-1"
              value={newCode}
              onChange={(e) => setNewCode(e.target.value)}
            />
            <Btn
              disabled={newCode.length < 3}
              onClick={() =>
                void act(`Device ${newCode} enrolled.`, async () => {
                  await post('/staff/devices', { code: newCode })
                  setNewCode('')
                })
              }
            >
              {t('staff.pages.Devices.enroll')}
            </Btn>
          </div>
        </Panel>
      )}
      {isAdmin && (
        <Panel title={t('staff.pages.Devices.pauseOrRestartNeeds')}>
          <div className="flex flex-wrap gap-2 text-sm">
            <input
              aria-label={t('staff.pages.Devices.reason')}
              placeholder={t('staff.pages.Devices.reason')}
              className="rounded-ctl border px-2 py-1"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
            <label>
              {t('staff.pages.Devices.pauseFor')}
              <input
                aria-label={t('staff.pages.Devices.pauseHours')}
                type="number"
                min={0.5}
                max={24}
                step={0.5}
                className="mx-2 w-20 rounded-ctl border px-2 py-1"
                value={hours}
                onChange={(e) => setHours(Number(e.target.value))}
              />
              {t('staff.pages.Devices.hours')}
            </label>
          </div>
        </Panel>
      )}
      <Table data-testid="device-table">
        <thead>
          <tr>
            <Th>{t('staff.pages.Devices.device')}</Th>
            <Th>{t('staff.pages.Devices.cell')}</Th>
            <Th>{t('staff.pages.Devices.resident')}</Th>
            <Th>{t('staff.pages.Devices.lastSeen')}</Th>
            <Th>{t('staff.pages.Devices.health')}</Th>
            <Th>{t('staff.pages.Devices.actions')}</Th>
          </tr>
        </thead>
        <tbody>
          {(data ?? []).map((d) => (
            <tr key={d.device} data-testid={`device-${d.device}`}>
              <Td>
                {d.device}{' '}
                {!d.paired && <Badge tone="gray">{t('staff.pages.Devices.notPaired')}</Badge>}
              </Td>
              <Td>{d.cell ?? '—'}</Td>
              <Td>{d.resident ?? '—'}</Td>
              <Td>
                {fmt(d.last_seen)}{' '}
                {d.offline && <Badge tone="red">{t('staff.pages.Devices.offline')}</Badge>}
              </Td>
              <Td>
                {d.health ? (
                  <span className="text-sm">
                    storage {mb(d.health.storage_used_mb)} of {mb(d.health.storage_quota_mb)} ·
                    camera {d.health.camera} · mic {d.health.microphone} · queue{' '}
                    {d.health.queue_pending ?? 0}
                  </span>
                ) : (
                  '—'
                )}
                {d.locked_until && <Badge tone="amber">paused until {fmt(d.locked_until)}</Badge>}
              </Td>
              <Td>
                <div className="flex flex-wrap gap-1">
                  {canPair && (
                    <Btn
                      kind="plain"
                      onClick={() =>
                        void act(`Setup code issued for ${d.device}.`, async () =>
                          setPairing(await post(`/staff/devices/${d.device}/pairing`)),
                        )
                      }
                    >
                      {t('staff.pages.Devices.setupCode')}
                    </Btn>
                  )}
                  {isAdmin && (
                    <>
                      <Btn
                        kind="danger"
                        disabled={reason.trim().length < 3}
                        onClick={() =>
                          void act(`${d.device} paused.`, () =>
                            post(`/staff/devices/${d.device}/lock`, { hours, reason }),
                          )
                        }
                      >
                        {t('staff.pages.Devices.pause')}
                      </Btn>
                      <Btn
                        kind="plain"
                        disabled={reason.trim().length < 3}
                        onClick={() =>
                          void act(`${d.device} resumed.`, () =>
                            post(`/staff/devices/${d.device}/unlock`, { reason }),
                          )
                        }
                      >
                        {t('staff.pages.Devices.resume')}
                      </Btn>
                      <Btn
                        kind="plain"
                        disabled={reason.trim().length < 3}
                        onClick={() =>
                          void act(`Restart sent to ${d.device}.`, () =>
                            post(`/staff/devices/${d.device}/restart`, { reason }),
                          )
                        }
                      >
                        {t('staff.pages.Devices.restart')}
                      </Btn>
                    </>
                  )}
                </div>
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Page>
  )
}
