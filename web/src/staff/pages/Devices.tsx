import { useState } from 'react'

import { errorText, fmt, post } from '../api'
import { useAuth } from '../auth'
import { Badge, Btn, ErrorLine, Notice, Page, Panel, Table, Td, Th, useLoad } from '../ui'

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

export default function Devices() {
  const { user } = useAuth()
  const { data, error, reload } = useLoad<Row[]>('/staff/devices')
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
    <Page title="Devices">
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
      {isAdmin && (
        <Panel title="Enroll a device">
          <div className="flex flex-wrap gap-2">
            <input
              aria-label="New device code"
              placeholder="Device code"
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
              Enroll
            </Btn>
          </div>
        </Panel>
      )}
      {isAdmin && (
        <Panel title="Pause or restart (needs a reason)">
          <div className="flex flex-wrap gap-2 text-sm">
            <input
              aria-label="Reason"
              placeholder="Reason"
              className="rounded-ctl border px-2 py-1"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
            <label>
              Pause for
              <input
                aria-label="Pause hours"
                type="number"
                min={0.5}
                max={24}
                step={0.5}
                className="mx-2 w-20 rounded-ctl border px-2 py-1"
                value={hours}
                onChange={(e) => setHours(Number(e.target.value))}
              />
              hours
            </label>
          </div>
        </Panel>
      )}
      <Table data-testid="device-table">
        <thead>
          <tr>
            <Th>Device</Th>
            <Th>Cell</Th>
            <Th>Resident</Th>
            <Th>Last seen</Th>
            <Th>Health</Th>
            <Th>Actions</Th>
          </tr>
        </thead>
        <tbody>
          {(data ?? []).map((d) => (
            <tr key={d.device} data-testid={`device-${d.device}`}>
              <Td>
                {d.device} {!d.paired && <Badge tone="gray">not paired</Badge>}
              </Td>
              <Td>{d.cell ?? '—'}</Td>
              <Td>{d.resident ?? '—'}</Td>
              <Td>
                {fmt(d.last_seen)} {d.offline && <Badge tone="red">offline</Badge>}
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
                      Setup code
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
                        Pause
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
                        Resume
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
                        Restart
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
