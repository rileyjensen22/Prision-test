import fixtures from './fixtures.json'

type Json = Record<string, unknown> | unknown[]
type Snap = Record<string, Json>
type Fixtures = typeof fixtures & {
  scenarios: Record<string, { label: string; before: Snap; after?: Snap }>
}
const F = fixtures as unknown as Fixtures

export type Scenario = 'alice' | 'gina' | 'tess'
export const SCENARIOS: { id: Scenario; title: string; blurb: string }[] = [
  { id: 'alice', title: 'Locked feature', blurb: 'Tier 3 with a 24h communication lock: tap Locks to see the reason, end time and Appeal.' },
  { id: 'gina', title: 'Demo loop', blurb: 'Tier 1. Open Education, finish the sample course, and watch call minutes rise.' },
  { id: 'tess', title: 'Tier 4', blurb: 'Calls to family and attorney, texting, commissary and reading.' },
]

const ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/

/** Shift every timestamp so the recording looks like it was made just now. */
function shift(value: unknown, delta: number): unknown {
  if (typeof value === 'string' && ISO.test(value)) {
    const t = Date.parse(value)
    return Number.isNaN(t) ? value : new Date(t + delta).toISOString()
  }
  if (Array.isArray(value)) return value.map((v) => shift(v, delta))
  if (value && typeof value === 'object')
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, shift(v, delta)]))
  return value
}

const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T
const reply = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

export type DemoState = { scenario: Scenario; language: 'en' | 'es'; passed: boolean; balance: number }

const realFetch = window.fetch.bind(window)

export function installShim(state: DemoState): void {
  const real = realFetch
  const started = new Map<number, number>()

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    if (!url.startsWith('/api/')) return real(input, init)
    const path = url.slice(4)
    const method = (init?.method ?? 'GET').toUpperCase()
    const sc = F.scenarios[state.scenario] as { before: Snap; after?: Snap }
    const snap = state.passed && sc.after ? sc.after : sc.before

    if (method === 'GET') {
      const raw = snap[path]
      if (raw === undefined) return reply({ detail: 'not in demo' }, 404)
      const out = clone(raw) as Record<string, unknown>
      const base = Date.parse(String((sc.before['/device/view'] as { generated_at: string }).generated_at))
      const moved = shift(out, Date.now() - base) as Record<string, unknown>
      if (path === '/device/view') {
        const v = moved as { settings: { language: string }; generated_at: string; valid_until: string }
        v.settings.language = state.language
        v.generated_at = new Date().toISOString()
        v.valid_until = new Date(Date.now() + 3600_000).toISOString()
      }
      if (path === '/device/commissary') (moved as { balance_cents: number }).balance_cents = state.balance
      return reply(moved)
    }

    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {}
    if (/\/lessons\/.+\/complete$/.test(path)) return reply({ ok: true })
    if (path.endsWith('/quiz')) {
      const r = clone(F.quiz_response) as { passed: boolean }
      if (state.scenario === 'gina' && !state.passed) state.passed = true
      return reply(r)
    }
    if (path === '/device/calls') {
      const id = Date.now()
      started.set(id, Date.now())
      return reply({ ...clone(F.call_started), call_id: id, started_at: new Date().toISOString() })
    }
    const end = path.match(/^\/device\/calls\/(\d+)\/end$/)
    if (end) {
      const t0 = started.get(Number(end[1])) ?? Date.now()
      return reply({
        ...clone(F.call_ended),
        call_id: Number(end[1]),
        duration_seconds: Math.round((Date.now() - t0) / 1000),
      })
    }
    if (path === '/device/commissary/orders') {
      const items = (sc.before['/device/commissary'] as { items: { code: string; price_cents: number }[] }).items
      const lines = (body.lines ?? {}) as Record<string, number>
      const total = Object.entries(lines).reduce(
        (s, [code, q]) => s + (items.find((i) => i.code === code)?.price_cents ?? 0) * q,
        0,
      )
      if (total > state.balance) return reply({ detail: { code: 'INSUFFICIENT_FUNDS' } }, 409)
      state.balance -= total
      return reply({ balance_cents: state.balance })
    }
    return reply({ ok: true })
  }
}
