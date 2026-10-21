import { useCallback, useEffect, useState } from 'react'
import type { ReactNode } from 'react'

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

export function Page({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">{title}</h1>
      {children}
    </section>
  )
}

export function Panel({
  title,
  children,
  ...rest
}: { title?: string; children: ReactNode } & Record<string, unknown>) {
  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm" {...rest}>
      {title && <h2 className="mb-3 text-lg font-semibold">{title}</h2>}
      {children}
    </div>
  )
}

export const Table = ({ children, ...rest }: { children: ReactNode } & Record<string, unknown>) => (
  <div className="overflow-x-auto">
    <table className="w-full text-left text-sm" {...rest}>
      {children}
    </table>
  </div>
)
export const Th = ({ children }: { children?: ReactNode }) => (
  <th className="border-b px-2 py-2 font-medium text-gray-600">{children}</th>
)
export const Td = ({ children, ...rest }: { children?: ReactNode } & Record<string, unknown>) => (
  <td className="border-b px-2 py-2 align-top" {...rest}>
    {children}
  </td>
)

export function Badge({
  children,
  tone = 'gray',
  ...rest
}: { children: ReactNode; tone?: 'gray' | 'red' | 'amber' | 'green' } & Record<string, unknown>) {
  const tones = {
    gray: 'bg-gray-100 text-gray-800',
    red: 'bg-red-100 text-red-800',
    amber: 'bg-amber-100 text-amber-900',
    green: 'bg-green-100 text-green-800',
  }
  return (
    <span
      className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${tones[tone]}`}
      {...rest}
    >
      {children}
    </span>
  )
}

export const Btn = ({
  children,
  kind = 'primary',
  ...rest
}: {
  children: ReactNode
  kind?: 'primary' | 'danger' | 'plain'
} & React.ButtonHTMLAttributes<HTMLButtonElement>) => {
  const kinds = {
    primary: 'bg-blue-700 text-white',
    danger: 'bg-red-700 text-white',
    plain: 'border bg-white',
  }
  return (
    <button
      {...rest}
      className={`rounded px-3 py-1.5 text-sm font-medium disabled:opacity-40 ${kinds[kind]}`}
    >
      {children}
    </button>
  )
}

export function Notice({ kind, children }: { kind: 'ok' | 'err'; children: ReactNode }) {
  return (
    <p
      role={kind === 'ok' ? 'status' : 'alert'}
      data-testid="notice"
      className={`rounded px-3 py-2 text-sm ${kind === 'ok' ? 'bg-green-50 text-green-900' : 'bg-red-50 text-red-900'}`}
    >
      {children}
    </p>
  )
}

export const ErrorLine = ({ error }: { error: string | null }) =>
  error ? <Notice kind="err">{error}</Notice> : null
