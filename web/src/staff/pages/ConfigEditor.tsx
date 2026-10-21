import { useEffect, useState } from 'react'

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
    <Panel title="Repeat-return ceiling" data-testid="curve-panel">
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm">
          N (returns that reach the lowest tier)
          <input
            aria-label="N"
            value={n}
            onChange={(e) => setN(e.target.value)}
            className="mt-1 block w-24 rounded border px-2 py-1"
          />
        </label>
        <label className="text-sm">
          p (how fast the loss grows)
          <input
            aria-label="p"
            value={pp}
            onChange={(e) => setP(e.target.value)}
            className="mt-1 block w-24 rounded border px-2 py-1"
          />
        </label>
        {editable && (
          <Btn kind="plain" onClick={apply}>
            Use these values in the editor
          </Btn>
        )}
      </div>
      <ErrorLine error={preview.error} />
      <Table data-testid="curve-preview">
        <thead>
          <tr>
            <Th>Prior returns</Th>
            <Th>Highest tier</Th>
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
    </Panel>
  )
}

export default function ConfigEditor() {
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
    <Page title="Configuration">
      <p className="text-sm text-gray-600">
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
            className={`rounded px-3 py-1.5 text-sm ${s.name === name ? 'bg-blue-700 text-white' : 'border bg-white'}`}
          >
            {s.name} <span className="opacity-70">v{s.version}</span>
          </button>
        ))}
      </div>
      <ErrorLine error={current.error} />
      {name === 'tiers' && <RepeatReturn text={text} setText={setText} editable={isAdmin} />}
      <Panel title={`${name}${current.data ? ` (version ${current.data.version})` : ''}`}>
        <textarea
          aria-label="Config JSON"
          data-testid="config-json"
          value={text}
          readOnly={!isAdmin}
          onChange={(e) => setText(e.target.value)}
          rows={18}
          spellCheck={false}
          className="w-full rounded border bg-gray-50 p-2 font-mono text-xs"
        />
        {isAdmin && (
          <div className="mt-3 flex flex-wrap items-end gap-3">
            <label className="flex-1 text-sm">
              Reason for change
              <input
                aria-label="Reason for change"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="mt-1 block w-full rounded border px-2 py-2"
              />
            </label>
            <Btn onClick={() => void save()} disabled={reason.trim().length < 3}>
              Save new version
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
        <Panel title="Version history">
          <Table data-testid="versions">
            <thead>
              <tr>
                <Th>Version</Th>
                <Th>When</Th>
                <Th>Reason</Th>
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
