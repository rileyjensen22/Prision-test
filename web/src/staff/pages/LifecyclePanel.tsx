import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { errorText, post } from '../api'
import { Btn, Notice, Panel, useLoad } from '../ui'

interface Options {
  vacant_cells: { code: string; unit: string }[]
  free_devices: string[]
}

/** Move a resident to another cell, or release them. Supervisors and admins only. */
export function LifecyclePanel({
  residentId,
  released,
  onDone,
}: {
  residentId: number
  released: boolean
  onDone: () => void
}) {
  const { t } = useTranslation()
  const { data: options, reload } = useLoad<Options>('/staff/intake/options')
  const [cell, setCell] = useState('')
  const [device, setDevice] = useState('')
  const [reason, setReason] = useState('')
  const [confirming, setConfirming] = useState(false)
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  async function run(fn: () => Promise<string>) {
    setMsg(null)
    try {
      setMsg({ kind: 'ok', text: await fn() })
      setReason('')
      setConfirming(false)
      await reload()
      onDone()
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  if (released)
    return (
      <Panel title={t('staff.lifecycle.title')} data-testid="lifecycle-panel">
        <p>{t('staff.lifecycle.released')}</p>
      </Panel>
    )

  return (
    <Panel title={t('staff.lifecycle.title')} data-testid="lifecycle-panel">
      <p className="mb-3 text-ink-soft">{t('staff.lifecycle.intro')}</p>
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      <label className="mt-3 block">
        {t('staff.lifecycle.reason')}
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className="mt-1 block w-full"
        />
      </label>
      <div className="mt-4 grid gap-6 md:grid-cols-2">
        <div className="space-y-2">
          <h3 className="font-bold">{t('staff.lifecycle.transfer')}</h3>
          <label className="block">
            {t('staff.lifecycle.vacantCell')}
            <select
              value={cell}
              onChange={(e) => setCell(e.target.value)}
              className="mt-1 block w-full"
            >
              <option value="">{t('staff.lifecycle.choose')}</option>
              {(options?.vacant_cells ?? []).map((c) => (
                <option key={c.code} value={c.code}>
                  {c.code} ({c.unit})
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            {t('staff.lifecycle.freeDevice')}
            <select
              value={device}
              onChange={(e) => setDevice(e.target.value)}
              className="mt-1 block w-full"
            >
              <option value="">{t('staff.lifecycle.choose')}</option>
              {(options?.free_devices ?? []).map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
          <Btn
            disabled={!cell || !device || reason.trim().length < 3}
            onClick={() =>
              void run(async () => {
                const r = await post<{ cell: string; keep_separate_on_new_unit: string[] }>(
                  `/staff/residents/${residentId}/transfer`,
                  { cell_code: cell, device_code: device, reason },
                )
                setCell('')
                setDevice('')
                return r.keep_separate_on_new_unit.length
                  ? t('staff.lifecycle.movedConflict', {
                      cell: r.cell,
                      codes: r.keep_separate_on_new_unit.join(', '),
                    })
                  : t('staff.lifecycle.moved', { cell: r.cell })
              })
            }
          >
            {t('staff.lifecycle.moveButton')}
          </Btn>
        </div>
        <div className="space-y-2">
          <h3 className="font-bold">{t('staff.lifecycle.vacateTitle')}</h3>
          {confirming ? (
            <div className="flex flex-wrap gap-2">
              <Btn
                kind="danger"
                disabled={reason.trim().length < 3}
                onClick={() =>
                  void run(async () => {
                    const r = await post<{ freed_cell: string; freed_device: string }>(
                      `/staff/residents/${residentId}/vacate`,
                      { reason },
                    )
                    return t('staff.lifecycle.vacated', {
                      cell: r.freed_cell,
                      device: r.freed_device,
                    })
                  })
                }
              >
                {t('staff.lifecycle.confirmVacate')}
              </Btn>
              <Btn kind="plain" onClick={() => setConfirming(false)}>
                {t('staff.lifecycle.cancel')}
              </Btn>
            </div>
          ) : (
            <Btn kind="plain" onClick={() => setConfirming(true)}>
              {t('staff.lifecycle.vacateButton')}
            </Btn>
          )}
        </div>
      </div>
    </Panel>
  )
}
