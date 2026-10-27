import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SimulatedResident } from '../../resident/SimulatedResident'
import type { ResidentView } from '../../resident/types'
import { errorText, post } from '../api'
import { Btn, ErrorLine, Page, Panel, SimulationBanner, useLoad } from '../ui'

interface RosterRow {
  resident_id: number
  code: string
  cell: string | null
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

const sel = 'mt-1 block w-full rounded-ctl border px-2 py-1.5'

export default function ViewAs() {
  const { t } = useTranslation()

  const roster = useLoad<RosterRow[]>('/staff/residents/lookup?limit=500')
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
    <Page title={t('staff.pages.ViewAs.viewAsResident')}>
      <SimulationBanner testId="sandbox-note">
        {t('staff.pages.ViewAs.simulationAReadOnly')}
      </SimulationBanner>
      <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
        <Panel title={t('staff.pages.ViewAs.whatToSimulate')}>
          <div className="space-y-3 text-sm">
            <label className="block">
              {t('staff.pages.ViewAs.resident')}
              <select
                aria-label={t('staff.pages.ViewAs.resident')}
                className={sel}
                value={residentId}
                onChange={(e) => {
                  setResidentId(e.target.value)
                  setView(null)
                }}
              >
                <option value="">{t('staff.pages.ViewAs.choose')}</option>
                {(roster.data ?? []).map((r) => (
                  <option key={r.resident_id} value={r.resident_id}>
                    {r.code}
                    {r.cell ? ` (${r.cell})` : ''}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              {t('staff.pages.ViewAs.tier')}
              <select
                aria-label={t('staff.pages.ViewAs.tier')}
                className={sel}
                value={tier}
                onChange={(e) => setTier(e.target.value)}
              >
                <option value="">{t('staff.pages.ViewAs.realTier')}</option>
                {Array.from({ length: 10 }, (_, i) => (
                  <option key={i + 1} value={i + 1}>
                    {t('staff.msg.tierN', { n: i + 1 })}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              {t('staff.pages.ViewAs.priorReturnsChangesThe')}
              <input
                aria-label={t('staff.pages.ViewAs.priorReturns')}
                type="number"
                min={0}
                max={60}
                className={sel}
                value={priorReturns}
                placeholder={t('staff.pages.ViewAs.realValue')}
                onChange={(e) => setPriorReturns(e.target.value)}
              />
            </label>
            <div className="grid grid-cols-2 gap-2">
              <label className="block">
                {t('staff.pages.ViewAs.language')}
                <select
                  aria-label={t('staff.pages.ViewAs.language')}
                  className={sel}
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                >
                  <option value="">{t('staff.pages.ViewAs.real')}</option>
                  <option value="en">{t('staff.pages.ViewAs.english')}</option>
                  <option value="es">{t('staff.pages.ViewAs.spanish')}</option>
                </select>
              </label>
              <label className="block">
                {t('staff.pages.ViewAs.textSize')}
                <select
                  aria-label={t('staff.pages.ViewAs.textSize')}
                  className={sel}
                  value={textSize}
                  onChange={(e) => setTextSize(e.target.value)}
                >
                  <option value="">{t('staff.pages.ViewAs.real')}</option>
                  <option>{t('staff.pages.ViewAs.normal')}</option>
                  <option>{t('staff.pages.ViewAs.large')}</option>
                  <option>{t('staff.pages.ViewAs.xlarge')}</option>
                </select>
              </label>
            </div>
            <fieldset className="rounded-ctl border p-2">
              <legend className="px-1">{t('staff.pages.ViewAs.offenseRestrictions')}</legend>
              <label className="block">
                <input
                  type="checkbox"
                  checked={overrideOffenses}
                  onChange={(e) => setOverrideOffenses(e.target.checked)}
                />{' '}
                {t('staff.msg.replaceReal')}
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
            <fieldset className="rounded-ctl border p-2">
              <legend className="px-1">{t('staff.pages.ViewAs.sanctions')}</legend>
              <label className="block">
                <input
                  type="checkbox"
                  checked={clearReal}
                  onChange={(e) => setClearReal(e.target.checked)}
                />{' '}
                {t('staff.msg.ignoreReal')}
              </label>
              <div className="mt-2 flex gap-2">
                <select
                  aria-label={t('staff.pages.ViewAs.addSanction')}
                  className="w-full rounded-ctl border px-2 py-1.5"
                  value={newCode}
                  onChange={(e) => setNewCode(e.target.value)}
                >
                  <option value="">{t('staff.pages.ViewAs.addASanction')}</option>
                  {(infractions.data ?? []).map((i) => (
                    <option key={i.code} value={i.code}>
                      {i.code} ({i.duration_hours}h)
                    </option>
                  ))}
                </select>
                <input
                  aria-label={t('staff.pages.ViewAs.hoursLeft')}
                  type="number"
                  min={1}
                  placeholder={t('staff.pages.ViewAs.hrsLeft')}
                  className="w-24 rounded-ctl border px-2 py-1.5"
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
                {t('staff.pages.ViewAs.add')}
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
              {t('staff.pages.ViewAs.timeTravelTheView')}
              <input
                aria-label={t('staff.pages.ViewAs.viewAsOf')}
                type="datetime-local"
                className={sel}
                value={when}
                onChange={(e) => setWhen(e.target.value)}
              />
            </label>
            <Btn kind="plain" onClick={reset}>
              {t('staff.pages.ViewAs.resetOverrides')}
            </Btn>
          </div>
        </Panel>
        <div>
          <ErrorLine error={error} />
          {!residentId && (
            <p className="text-ink-soft">{t('staff.pages.ViewAs.chooseAResidentTo')}</p>
          )}
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
