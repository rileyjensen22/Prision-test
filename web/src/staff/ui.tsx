import {
  AlertOctagon,
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  ChevronsUpDown,
  CircleDot,
  CheckCircle2,
  Eye,
  Search,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { cn } from '../ui/cn'
import { EmptyState } from '../ui/States'
import { api, errorText } from './api'

/** Loads a GET endpoint; `reload` refetches (call it after a change). */
export function useLoad<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const reload = useCallback(async () => {
    if (!path) return
    try {
      setData(await api<T>(path))
      setError(null)
    } catch (e) {
      setError(errorText(e))
    }
  }, [path])
  useEffect(() => {
    void reload()
  }, [reload])
  return { data, error, reload }
}

export const FIELD =
  'min-h-touch w-full rounded-ctl border border-ink-soft bg-surface px-3 text-body text-ink placeholder:text-ink-soft'

export function Page({
  title,
  actions,
  children,
}: {
  title: string
  actions?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-h1 font-bold">{title}</h1>
        {actions}
      </div>
      {children}
    </section>
  )
}

export function Panel({
  title,
  children,
  className,
  ...rest
}: { title?: string; children: ReactNode; className?: string } & Record<string, unknown>) {
  return (
    <div className={cn('rounded-card border border-line bg-surface p-4', className)} {...rest}>
      {title && <h2 className="mb-3 text-h3 font-bold">{title}</h2>}
      {children}
    </div>
  )
}

/** Scroll container with a sticky header row, so long tables keep their column names in view. */
export const Table = ({
  children,
  className,
  ...rest
}: { children: ReactNode; className?: string } & Record<string, unknown>) => (
  <div className="max-h-[calc(100vh-13rem)] overflow-auto rounded-card border border-line bg-surface">
    <table className={cn('w-full border-collapse text-left', className)} {...rest}>
      {children}
    </table>
  </div>
)
export const Th = ({
  children,
  sort,
}: {
  children?: ReactNode
  sort?: 'ascending' | 'descending' | 'none'
}) => (
  <th
    aria-sort={sort}
    className="sticky top-0 z-[1] border-b border-line bg-surface-2 px-3 py-2 text-sm font-bold text-ink-soft"
  >
    {children}
  </th>
)
export const Td = ({ children, ...rest }: { children?: ReactNode } & Record<string, unknown>) => (
  <td className="border-b border-line px-3 py-2 align-top" {...rest}>
    {children}
  </td>
)

type Tone = 'gray' | 'red' | 'amber' | 'green'
const BADGE: Record<Tone, { cls: string; icon: typeof CircleDot }> = {
  gray: { cls: 'bg-surface-2 text-ink', icon: CircleDot },
  red: { cls: 'bg-danger-soft text-danger', icon: AlertOctagon },
  amber: { cls: 'bg-notice-soft text-notice', icon: AlertTriangle },
  green: { cls: 'bg-ok-soft text-ok', icon: CheckCircle2 },
}

/** Status is an icon plus words, never colour alone. */
export function Badge({
  children,
  tone = 'gray',
  ...rest
}: { children: ReactNode; tone?: Tone } & Record<string, unknown>) {
  const { cls, icon: Icon } = BADGE[tone]
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-sm font-bold',
        cls,
      )}
      {...rest}
    >
      <Icon aria-hidden="true" className="size-3.5 shrink-0" strokeWidth={2.5} />
      {children}
    </span>
  )
}

export const Btn = ({
  children,
  kind = 'primary',
  className,
  ...rest
}: {
  children: ReactNode
  kind?: 'primary' | 'danger' | 'plain'
} & ButtonHTMLAttributes<HTMLButtonElement>) => {
  const kinds = {
    primary: 'bg-primary text-primary-ink hover:brightness-110',
    danger: 'bg-danger text-primary-ink hover:brightness-110',
    plain: 'border border-ink-soft bg-surface hover:bg-surface-2',
  }
  return (
    <button
      {...rest}
      className={cn(
        'min-h-touch rounded-ctl px-3 py-1.5 text-body font-bold disabled:opacity-40',
        kinds[kind],
        className,
      )}
    >
      {children}
    </button>
  )
}

export function Notice({ kind, children }: { kind: 'ok' | 'err'; children: ReactNode }) {
  const Icon = kind === 'ok' ? CheckCircle2 : AlertTriangle
  return (
    <p
      role={kind === 'ok' ? 'status' : 'alert'}
      data-testid="notice"
      className={cn(
        'flex items-center gap-2 rounded-ctl border px-3 py-2',
        kind === 'ok' ? 'border-ok bg-ok-soft' : 'border-danger bg-danger-soft',
      )}
    >
      <Icon
        aria-hidden="true"
        className={cn('size-5 shrink-0', kind === 'ok' ? 'text-ok' : 'text-danger')}
      />
      {children}
    </p>
  )
}

export const ErrorLine = ({ error }: { error: string | null }) =>
  error ? <Notice kind="err">{error}</Notice> : null

/** Sticks to the top while a simulation is on screen, and cannot be dismissed. */
export function SimulationBanner({
  children,
  testId = 'simulation-banner',
}: {
  children?: ReactNode
  testId?: string
}) {
  const { t } = useTranslation()
  return (
    <div
      role="status"
      data-testid={testId}
      className="sticky top-0 z-20 flex items-center gap-3 rounded-ctl bg-danger px-4 py-3 text-label font-bold text-primary-ink"
    >
      <Eye aria-hidden="true" className="size-6 shrink-0" />
      <span>{children ?? t('staff.simulation')}</span>
    </div>
  )
}

export interface Column<T> {
  key: string
  header: string
  /** Renders the cell. */
  cell: (row: T) => ReactNode
  /** Sort key; a column with this is sortable. */
  sort?: (row: T) => string | number
  /** Text matched by the filter box. */
  text?: (row: T) => string
}

/**
 * Sortable, filterable table with a sticky header and a row count. Sorting is stable and stays on
 * the page; nothing here changes what the server returned.
 */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  testId,
  rowTestId,
  empty,
}: {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string | number
  testId?: string
  rowTestId?: (row: T) => string
  empty?: ReactNode
}) {
  const { t } = useTranslation()
  const [q, setQ] = useState('')
  const [sortKey, setSortKey] = useState<string | null>(null)
  const [dir, setDir] = useState<1 | -1>(1)

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase()
    let out = needle
      ? rows.filter((r) => columns.some((c) => (c.text?.(r) ?? '').toLowerCase().includes(needle)))
      : rows
    const col = columns.find((c) => c.key === sortKey)
    if (col?.sort) {
      const get = col.sort
      out = [...out].sort((a, b) => {
        const x = get(a)
        const y = get(b)
        return (x < y ? -1 : x > y ? 1 : 0) * dir
      })
    }
    return out
  }, [rows, columns, q, sortKey, dir])

  function toggle(key: string) {
    if (sortKey === key) setDir((d) => (d === 1 ? -1 : 1))
    else {
      setSortKey(key)
      setDir(1)
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-3">
        <label className="relative block w-72 max-w-full">
          <span className="sr-only">{t('staff.table.filter')}</span>
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-soft"
          />
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t('staff.table.filterHint')}
            className={cn(FIELD, 'pl-9')}
          />
        </label>
        <span className="text-sm text-ink-soft" aria-live="polite">
          {t('staff.table.showing', { shown: shown.length, total: rows.length })}
        </span>
      </div>
      {rows.length === 0 ? (
        (empty ?? <EmptyState title={t('staff.table.empty')} />)
      ) : shown.length === 0 ? (
        <EmptyState title={t('staff.table.noMatches', { q })} />
      ) : (
        <Table data-testid={testId} className="text-body">
          <thead>
            <tr>
              {columns.map((c) => (
                <Th
                  key={c.key}
                  sort={
                    sortKey === c.key
                      ? dir === 1
                        ? 'ascending'
                        : 'descending'
                      : c.sort
                        ? 'none'
                        : undefined
                  }
                >
                  {c.sort ? (
                    <button
                      type="button"
                      onClick={() => toggle(c.key)}
                      aria-label={t('staff.table.sort', { col: c.header })}
                      className="inline-flex items-center gap-1 font-bold hover:text-ink"
                    >
                      {c.header}
                      {sortKey === c.key ? (
                        dir === 1 ? (
                          <ArrowUp aria-hidden="true" className="size-4" />
                        ) : (
                          <ArrowDown aria-hidden="true" className="size-4" />
                        )
                      ) : (
                        <ChevronsUpDown aria-hidden="true" className="size-4 opacity-60" />
                      )}
                    </button>
                  ) : (
                    c.header
                  )}
                </Th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={rowKey(r)} data-testid={rowTestId?.(r)} className="hover:bg-surface-2">
                {columns.map((c) => (
                  <Td key={c.key}>{c.cell(r)}</Td>
                ))}
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  )
}
