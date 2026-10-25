import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { errorText, fmt, put } from '../api'
import { useAuth } from '../auth'
import { Btn, ErrorLine, Notice, Page, Panel, Table, Td, Th, useLoad } from '../ui'

interface Section {
  name: string
  version: number | null
}
interface Current {
  name: string
  version: number
  payload: Record<string, unknown>
}
interface Version {
  version: number
  reason: string
  created_at: string
  created_by: number | null
}
interface CeilingRow {
  returns: number
  ceiling_tier: number
  raw_loss: number
}

function RepeatReturn({
  text,
  setText,
  editable,
}: {
  text: string
  setText: (t: string) => void
  editable: boolean
}) {
  const { t: tr } = useTranslation()

  let N = 12
  let p = 1.5
  try {
    const rr = (JSON.parse(text) as { repeat_return?: { N: number; p: number } }).repeat_return
    if (rr) ({ N, p } = rr)
  } catch {
    /* the JSON box shows the syntax error */
  }
  const [n, setN] = useState(String(N))
  const [pp, setP] = useState(String(p))
  const preview = useLoad<CeilingRow[]>(
    `/staff/ceiling-preview?N=${encodeURIComponent(n)}&p=${encodeURIComponent(pp)}`,
  )

  function apply() {
    const obj = JSON.parse(text)
    obj.repeat_return = { N: Number(n), p: Number(pp) }
    setText(JSON.stringify(obj, null, 2))
  }

  return (
    <Panel title={tr('staff.pages.ConfigEditor.repeatReturnCeiling')} data-testid="curve-panel">
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm">
          {tr('staff.pages.ConfigEditor.nReturnsThatReach')}
          <input
            aria-label="N"
            value={n}
            onChange={(e) => setN(e.target.value)}
            className="mt-1 block w-24 rounded-ctl border px-2 py-1"
          />
        </label>
        <label className="text-sm">
          {tr('staff.pages.ConfigEditor.pHowFastThe')}
          <input
            aria-label="p"
            value={pp}
            onChange={(e) => setP(e.target.value)}
            className="mt-1 block w-24 rounded-ctl border px-2 py-1"
          />
        </label>
        {editable && (
          <Btn kind="plain" onClick={apply}>
            {tr('staff.pages.ConfigEditor.useTheseValuesIn')}
          </Btn>
        )}
      </div>
      <ErrorLine error={preview.error} />
      <div className="mt-3 max-w-md">
        <Table data-testid="curve-preview">
          <thead>
            <tr>
              <Th>{tr('staff.pages.ConfigEditor.priorReturns')}</Th>
              <Th>{tr('staff.pages.ConfigEditor.highestTier')}</Th>
            </tr>
          </thead>
          <tbody>
            {(preview.data ?? []).map((r) => (
              <tr key={r.returns}>
                <Td>{r.returns}</Td>
                <Td>{r.ceiling_tier}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </div>
    </Panel>
  )
}

export default function ConfigEditor() {
  const { t: tr } = useTranslation()

  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const canSeeHistory = user?.role === 'admin' || user?.role === 'auditor'
  const sections = useLoad<Section[]>('/config')
  const [name, setName] = useState('tiers')
  const current = useLoad<Current>(`/config/${name}`)
  const versions = useLoad<Version[]>(canSeeHistory ? `/config/${name}/versions` : null)
  const [text, setText] = useState('')
  const [reason, setReason] = useState('')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  useEffect(() => {
    if (current.data) setText(JSON.stringify(current.data.payload, null, 2))
  }, [current.data])

  async function save() {
    setMsg(null)
    let payload: unknown
    try {
      payload = JSON.parse(text)
    } catch (e) {
      setMsg({ kind: 'err', text: `Not valid JSON: ${(e as Error).message}` })
      return
    }
    try {
      const r = await put<{ version: number }>(`/config/${name}`, { payload, reason })
      setMsg({ kind: 'ok', text: `Saved as version ${r.version}.` })
      setReason('')
      await current.reload()
      await versions.reload()
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  return (
    <Page title={tr('staff.pages.ConfigEditor.configuration')}>
      <p className="text-sm text-ink-soft">
        Every change creates a new version and an audit entry.{' '}
        {isAdmin ? 'You can edit.' : 'You can view; only admins can edit.'}
      </p>
      <div className="flex flex-wrap gap-2" role="tablist">
        {(sections.data ?? []).map((s) => (
          <button
            key={s.name}
            role="tab"
            aria-selected={s.name === name}
            onClick={() => {
              setName(s.name)
              setMsg(null)
            }}
            className={`rounded-ctl px-3 py-1.5 text-sm ${s.name === name ? 'bg-primary text-primary-ink' : 'border bg-surface'}`}
          >
            {s.name} <span className="opacity-70">v{s.version}</span>
          </button>
        ))}
      </div>
      <ErrorLine error={current.error} />
      {name === 'tiers' && <RepeatReturn text={text} setText={setText} editable={isAdmin} />}
      <Panel title={`${name}${current.data ? ` (version ${current.data.version})` : ''}`}>
        <textarea
          aria-label={tr('staff.pages.ConfigEditor.configJson')}
          data-testid="config-json"
          value={text}
          readOnly={!isAdmin}
          onChange={(e) => setText(e.target.value)}
          rows={18}
          spellCheck={false}
          className="w-full rounded-ctl border bg-surface-2 p-2 font-mono text-sm"
        />
        {isAdmin && (
          <div className="mt-3 flex flex-wrap items-end gap-3">
            <label className="flex-1 text-sm">
              {tr('staff.pages.ConfigEditor.reasonForChange')}
              <input
                aria-label={tr('staff.pages.ConfigEditor.reasonForChange')}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="mt-1 block w-full rounded-ctl border px-2 py-2"
              />
            </label>
            <Btn onClick={() => void save()} disabled={reason.trim().length < 3}>
              {tr('staff.pages.ConfigEditor.saveNewVersion')}
            </Btn>
          </div>
        )}
        {msg && (
          <div className="mt-3">
            <Notice kind={msg.kind}>{msg.text}</Notice>
          </div>
        )}
      </Panel>
      {canSeeHistory && (
        <Panel title={tr('staff.pages.ConfigEditor.versionHistory')}>
          <Table data-testid="versions">
            <thead>
              <tr>
                <Th>{tr('staff.pages.ConfigEditor.version')}</Th>
                <Th>{tr('staff.pages.ConfigEditor.when')}</Th>
                <Th>{tr('staff.pages.ConfigEditor.reason')}</Th>
              </tr>
            </thead>
            <tbody>
              {(versions.data ?? [])
                .slice()
                .reverse()
                .map((v) => (
                  <tr key={v.version}>
                    <Td>{v.version}</Td>
                    <Td>{fmt(v.created_at)}</Td>
                    <Td>{v.reason}</Td>
                  </tr>
                ))}
            </tbody>
          </Table>
        </Panel>
      )}
    </Page>
  )
}
