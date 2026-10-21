import { useEffect, useState } from 'react'

import { SimulatedResident } from '../../resident/SimulatedResident'
import type { ResidentView } from '../../resident/types'
import { errorText, post } from '../api'
import { Btn, ErrorLine, Page, Panel, useLoad } from '../ui'

interface RosterRow {
  resident_id: number
  code: string
  tier: { effective: number }
}
interface Infraction {
  code: string
  label: string
  duration_hours: number
}
interface Offenses {
  payload: { offense_restrictions: { offense_category: string }[] }
}
interface Sanc {
  code: string
  hours: string
}

const sel = 'mt-1 block w-full rounded border px-2 py-1.5'

export default function ViewAs() {
  const roster = useLoad<RosterRow[]>('/staff/roster')
  const infractions = useLoad<Infraction[]>('/staff/infractions')
  const offenses = useLoad<Offenses>('/config/offenses')
  const [residentId, setResidentId] = useState('')
  const [tier, setTier] = useState('')
  const [priorReturns, setPriorReturns] = useState('')
  const [language, setLanguage] = useState('')
  const [textSize, setTextSize] = useState('')
  const [overrideOffenses, setOverrideOffenses] = useState(false)
  const [cats, setCats] = useState<string[]>([])
  const [clearReal, setClearReal] = useState(false)
  const [added, setAdded] = useState<Sanc[]>([])
  const [newCode, setNewCode] = useState('')
  const [newHours, setNewHours] = useState('')
  const [when, setWhen] = useState('')
  const [view, setView] = useState<ResidentView | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!residentId) return
    const id = setTimeout(async () => {
      try {
        const v = await post<ResidentView>('/staff/sandbox/view', {
          resident_id: Number(residentId),
          at_time: when ? new Date(when).toISOString() : null,
          overrides: {
            tier: tier ? Number(tier) : null,
            prior_returns: priorReturns !== '' ? Number(priorReturns) : null,
            language: language || null,
            text_size: textSize || null,
            offense_categories: overrideOffenses ? cats : null,
            clear_sanctions: clearReal,
            add_sanctions: added.map((s) => ({
              code: s.code,
              hours_remaining: s.hours ? Number(s.hours) : null,
            })),
          },
        })
        setView(v)
        setError(null)
      } catch (e) {
        setError(errorText(e))
      }
    }, 250)
    return () => clearTimeout(id)
  }, [
    residentId,
    tier,
    priorReturns,
    language,
    textSize,
    overrideOffenses,
    cats,
    clearReal,
    added,
    when,
  ])

  function reset() {
    setTier('')
    setPriorReturns('')
    setLanguage('')
    setTextSize('')
    setOverrideOffenses(false)
    setCats([])
    setClearReal(false)
    setAdded([])
    setWhen('')
  }

  return (
    <Page title="View as resident">
      <p
        role="note"
        className="rounded bg-red-50 px-3 py-2 text-sm text-red-900"
        data-testid="sandbox-note"
      >
        SIMULATION: a read-only dry run. Nothing here is saved, sent, or visible to the resident,
        and the database refuses writes while it runs. Buttons inside the simulated screen do
        nothing.
      </p>
      <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
        <Panel title="What to simulate">
          <div className="space-y-3 text-sm">
            <label className="block">
              Resident
              <select
                aria-label="Resident"
                className={sel}
                value={residentId}
                onChange={(e) => {
                  setResidentId(e.target.value)
                  setView(null)
                }}
              >
                <option value="">Choose…</option>
                {(roster.data ?? []).map((r) => (
                  <option key={r.resident_id} value={r.resident_id}>
                    {r.code} (tier {r.tier.effective})
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              Tier
              <select
                aria-label="Tier"
                className={sel}
                value={tier}
                onChange={(e) => setTier(e.target.value)}
              >
                <option value="">Real tier</option>
                {Array.from({ length: 10 }, (_, i) => (
                  <option key={i + 1} value={i + 1}>
                    Tier {i + 1}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              Prior returns (changes the ceiling)
              <input
                aria-label="Prior returns"
                type="number"
                min={0}
                max={60}
                className={sel}
                value={priorReturns}
                placeholder="Real value"
                onChange={(e) => setPriorReturns(e.target.value)}
              />
            </label>
            <div className="grid grid-cols-2 gap-2">
              <label className="block">
                Language
                <select
                  aria-label="Language"
                  className={sel}
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                >
                  <option value="">Real</option>
                  <option value="en">English</option>
                  <option value="es">Spanish</option>
                </select>
              </label>
              <label className="block">
                Text size
                <select
                  aria-label="Text size"
                  className={sel}
                  value={textSize}
                  onChange={(e) => setTextSize(e.target.value)}
                >
                  <option value="">Real</option>
                  <option>normal</option>
                  <option>large</option>
                  <option>xlarge</option>
                </select>
              </label>
            </div>
            <fieldset className="rounded border p-2">
              <legend className="px-1">Offense restrictions</legend>
              <label className="block">
                <input
                  type="checkbox"
                  checked={overrideOffenses}
                  onChange={(e) => setOverrideOffenses(e.target.checked)}
                />{' '}
                Replace the real ones
              </label>
              {overrideOffenses &&
                (offenses.data?.payload.offense_restrictions ?? []).map((o) => (
                  <label key={o.offense_category} className="block">
                    <input
                      type="checkbox"
                      checked={cats.includes(o.offense_category)}
                      onChange={(e) =>
                        setCats(
                          e.target.checked
                            ? [...cats, o.offense_category]
                            : cats.filter((c) => c !== o.offense_category),
                        )
                      }
                    />{' '}
                    {o.offense_category}
                  </label>
                ))}
            </fieldset>
            <fieldset className="rounded border p-2">
              <legend className="px-1">Sanctions</legend>
              <label className="block">
                <input
                  type="checkbox"
                  checked={clearReal}
                  onChange={(e) => setClearReal(e.target.checked)}
                />{' '}
                Ignore the real ones
              </label>
              <div className="mt-2 flex gap-2">
                <select
                  aria-label="Add sanction"
                  className="w-full rounded border px-2 py-1.5"
                  value={newCode}
                  onChange={(e) => setNewCode(e.target.value)}
                >
                  <option value="">Add a sanction…</option>
                  {(infractions.data ?? []).map((i) => (
                    <option key={i.code} value={i.code}>
                      {i.code} ({i.duration_hours}h)
                    </option>
                  ))}
                </select>
                <input
                  aria-label="Hours left"
                  type="number"
                  min={1}
                  placeholder="hrs left"
                  className="w-24 rounded border px-2 py-1.5"
                  value={newHours}
                  onChange={(e) => setNewHours(e.target.value)}
                />
              </div>
              <Btn
                kind="plain"
                disabled={!newCode}
                onClick={() => {
                  setAdded([...added, { code: newCode, hours: newHours }])
                  setNewCode('')
                  setNewHours('')
                }}
              >
                Add
              </Btn>
              <ul className="mt-2" data-testid="added-sanctions">
                {added.map((s, i) => (
                  <li key={i} className="flex items-center justify-between">
                    {s.code}
                    {s.hours ? `, ${s.hours}h left` : ''}
                    <button
                      aria-label={`Remove ${s.code}`}
                      onClick={() => setAdded(added.filter((_, j) => j !== i))}
                      className="px-2"
                    >
                      ✕
                    </button>
                  </li>
                ))}
              </ul>
            </fieldset>
            <label className="block">
              Time travel (the view as of…)
              <input
                aria-label="View as of"
                type="datetime-local"
                className={sel}
                value={when}
                onChange={(e) => setWhen(e.target.value)}
              />
            </label>
            <Btn kind="plain" onClick={reset}>
              Reset overrides
            </Btn>
          </div>
        </Panel>
        <div>
          <ErrorLine error={error} />
          {!residentId && <p className="text-gray-600">Choose a resident to see their screen.</p>}
          {view && (
            <div className="max-w-xl">
              <SimulatedResident view={view} mode="sandbox" />
            </div>
          )}
        </div>
      </div>
    </Page>
  )
}
