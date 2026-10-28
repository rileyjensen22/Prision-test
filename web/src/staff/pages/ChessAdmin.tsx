import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { errorText, fmt } from '../api'
import { api } from '../api'
import { useAuth } from '../auth'
import { Btn, DataTable, ErrorLine, FIELD, Notice, Page, Panel, useLoad } from '../ui'
import type { Column } from '../ui'

interface Match {
  id: number
  opponent: 'engine' | 'human'
  level: number | null
  status: string
  white: string
  black: string | null
  white_handle: string | null
  black_handle: string | null
  result: string | null
  reason: string | null
  plies: number
  started_at: string
}
interface CellRow {
  code: string
  unit: string
  line_code: string | null
}

export default function ChessAdmin() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const canEdit = user?.role === 'supervisor' || user?.role === 'admin'
  const matches = useLoad<Match[]>('/staff/chess/matches')
  const cells = useLoad<CellRow[]>('/staff/cells')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)
  const [resident, setResident] = useState('')
  const [setting, setSetting] = useState<'on' | 'off' | 'follow'>('follow')
  const [reason, setReason] = useState('')
  const [lines, setLines] = useState<Record<string, string>>({})

  async function save(path: string, body: unknown, ok: string) {
    setMsg(null)
    try {
      await api(path, { method: 'PUT', body: JSON.stringify(body) })
      setMsg({ kind: 'ok', text: ok })
      await cells.reload()
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  async function saveSwitch() {
    setMsg(null)
    try {
      const roster = await api<{ code: string; resident_id: number }[]>(
        `/staff/residents/lookup?q=${encodeURIComponent(resident.trim())}&limit=20`,
      )
      const found = roster.find((r) => r.code === resident.trim())
      if (!found) throw new Error(t('staff.chess.noResident'))
      await save(
        `/staff/residents/${found.resident_id}/chess`,
        { human: setting === 'follow' ? null : setting === 'on', reason },
        t('staff.chess.saved'),
      )
      setReason('')
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  const columns: Column<Match>[] = [
    { key: 'id', header: '#', sort: (m) => m.id, cell: (m) => m.id },
    {
      key: 'kind',
      header: t('staff.chess.kind'),
      text: (m) => m.opponent,
      cell: (m) =>
        m.opponent === 'engine'
          ? t('staff.chess.engine', { level: m.level })
          : t('staff.chess.human'),
    },
    {
      key: 'players',
      header: t('staff.chess.players'),
      text: (m) => `${m.white} ${m.black ?? ''}`,
      cell: (m) => (
        <span>
          <strong>{m.white}</strong>
          {m.white_handle && <span className="text-ink-soft"> ({m.white_handle})</span>}
          {m.black && (
            <>
              {' vs '}
              <strong>{m.black}</strong>
              <span className="text-ink-soft"> ({m.black_handle})</span>
            </>
          )}
        </span>
      ),
    },
    {
      key: 'status',
      header: t('staff.chess.status'),
      text: (m) => m.status,
      cell: (m) => m.status,
    },
    {
      key: 'result',
      header: t('staff.chess.result'),
      text: (m) => `${m.result ?? ''} ${m.reason ?? ''}`,
      cell: (m) => [m.result, m.reason].filter(Boolean).join(', ') || '—',
    },
    { key: 'plies', header: t('staff.chess.moves'), sort: (m) => m.plies, cell: (m) => m.plies },
    {
      key: 'at',
      header: t('staff.chess.started'),
      sort: (m) => m.started_at,
      cell: (m) => fmt(m.started_at),
    },
  ]

  return (
    <Page title={t('staff.chess.title')}>
      <p className="text-sm text-ink-soft">{t('staff.chess.intro')}</p>
      <ErrorLine error={matches.error ?? cells.error} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      <Panel title={t('staff.chess.log')}>
        <DataTable
          rows={matches.data ?? []}
          columns={columns}
          rowKey={(m) => m.id}
          empty={<p>{t('staff.chess.none')}</p>}
        />
      </Panel>
      {canEdit && (
        <Panel title={t('staff.chess.switchTitle')}>
          <p className="mb-2 text-sm">{t('staff.chess.switchHelp')}</p>
          <div className="flex flex-wrap gap-2">
            <input
              aria-label={t('staff.chess.residentCode')}
              placeholder={t('staff.chess.residentCode')}
              className={`${FIELD} max-w-48`}
              value={resident}
              onChange={(e) => setResident(e.target.value)}
            />
            <select
              aria-label={t('staff.chess.setting')}
              className={`${FIELD} max-w-56`}
              value={setting}
              onChange={(e) => setSetting(e.target.value as typeof setting)}
            >
              <option value="follow">{t('staff.chess.follow')}</option>
              <option value="on">{t('staff.chess.on')}</option>
              <option value="off">{t('staff.chess.off')}</option>
            </select>
            <input
              aria-label={t('staff.chess.reason')}
              placeholder={t('staff.chess.reason')}
              className={`${FIELD} max-w-sm`}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
            <Btn disabled={!resident || reason.trim().length < 3} onClick={() => void saveSwitch()}>
              {t('staff.chess.save')}
            </Btn>
          </div>
        </Panel>
      )}
      <Panel title={t('staff.chess.linesTitle')}>
        <p className="mb-2 text-sm">{t('staff.chess.linesHelp')}</p>
        <ul className="space-y-2">
          {(cells.data ?? []).map((c) => (
            <li
              key={c.code}
              className="flex flex-wrap items-center gap-2"
              data-testid={`cell-${c.code}`}
            >
              <span className="w-40 font-bold">{c.code}</span>
              <span className="w-20 text-ink-soft">{c.unit}</span>
              {canEdit ? (
                <>
                  <input
                    aria-label={`${t('staff.chess.line')} ${c.code}`}
                    className={`${FIELD} max-w-32`}
                    value={lines[c.code] ?? c.line_code ?? ''}
                    onChange={(e) => setLines({ ...lines, [c.code]: e.target.value })}
                  />
                  <Btn
                    kind="plain"
                    disabled={(lines[c.code] ?? c.line_code ?? '') === (c.line_code ?? '')}
                    onClick={() =>
                      void save(
                        `/staff/cells/${c.code}/line`,
                        {
                          line_code: (lines[c.code] ?? '').trim() || null,
                          reason: t('staff.chess.lineReason'),
                        },
                        t('staff.chess.saved'),
                      )
                    }
                  >
                    {t('staff.chess.save')}
                  </Btn>
                </>
              ) : (
                <span>{c.line_code ?? '—'}</span>
              )}
            </li>
          ))}
        </ul>
      </Panel>
    </Page>
  )
}
