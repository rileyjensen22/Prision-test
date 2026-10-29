import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { api, errorText, post } from '../api'
import { Btn, ErrorLine, Notice, Page, Panel, useLoad } from '../ui'

interface Options {
  vacant_cells: { code: string; unit: string }[]
  free_devices: string[]
  offense_categories: { code: string; reason_text: string }[]
  contact_types: string[]
}
interface ContactRow {
  name: string
  type: string
  phone: string
}
interface SeparateRow {
  resident_code: string
  reason: string
}

const input = 'rounded-ctl border px-2 py-1'

export default function Intake() {
  const { t: tr } = useTranslation()

  const { data: options, error } = useLoad<Options>('/staff/intake/options')
  const [name, setName] = useState('')
  const [cell, setCell] = useState('')
  const [device, setDevice] = useState('')
  const [language, setLanguage] = useState('en')
  const [textSize, setTextSize] = useState('normal')
  const [readingLevel, setReadingLevel] = useState('standard')
  const [captions, setCaptions] = useState(false)
  const [prior, setPrior] = useState(0)
  const [ceilingTier, setCeilingTier] = useState<number | null>(null)
  const [source, setSource] = useState('')
  const [release, setRelease] = useState('')
  const [categories, setCategories] = useState<string[]>([])
  const [contacts, setContacts] = useState<ContactRow[]>([])
  const [separate, setSeparate] = useState<SeparateRow[]>([])
  const [reason, setReason] = useState('')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string; id?: number } | null>(null)

  useEffect(() => {
    if (prior > 0) {
      api<{ ceiling_tier: number }>(`/staff/intake/ceiling?prior_returns=${prior}`)
        .then((r) => setCeilingTier(r.ceiling_tier))
        .catch(() => setCeilingTier(null))
    } else {
      setCeilingTier(10)
    }
  }, [prior])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    try {
      const r = await post<{ resident_id: number; code: string }>('/staff/intake', {
        display_name: name,
        cell_code: cell,
        device_code: device,
        language,
        text_size: textSize,
        reading_level: readingLevel,
        captions,
        prior_returns: prior,
        prior_returns_source: prior ? source : null,
        release_date: release || null,
        offense_categories: categories,
        contacts,
        keep_separate: separate,
        reason,
      })
      setMsg({ kind: 'ok', text: `Admitted as ${r.code}.`, id: r.resident_id })
    } catch (err) {
      setMsg({ kind: 'err', text: errorText(err) })
    }
  }

  return (
    <Page title={tr('staff.pages.Intake.intake')}>
      <ErrorLine error={error} />
      {msg && (
        <>
          <Notice kind={msg.kind}>{msg.text}</Notice>
          {msg.id && (
            <Link className="text-primary underline" to={`/staff/residents/${msg.id}`}>
              {tr('staff.pages.Intake.openTheResident')}
            </Link>
          )}
        </>
      )}
      <form onSubmit={(e) => void submit(e)} className="space-y-4" data-testid="intake-form">
        <Panel title={tr('staff.pages.Intake.whoAndWhere')}>
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="block text-sm">
              {tr('staff.pages.Intake.name')}
              <input
                className={input + ' w-full'}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label className="block text-sm">
              {tr('staff.pages.Intake.cell')}
              <select
                className={input + ' w-full'}
                value={cell}
                onChange={(e) => setCell(e.target.value)}
              >
                <option value="">{tr('staff.pages.Intake.choose')}</option>
                {options?.vacant_cells.map((c) => (
                  <option key={c.code} value={c.code}>
                    {tr('staff.msg.vacantCell', { code: c.code, unit: c.unit })}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              {tr('staff.pages.Intake.device')}
              <select
                className={input + ' w-full'}
                value={device}
                onChange={(e) => setDevice(e.target.value)}
              >
                <option value="">{tr('staff.pages.Intake.choose')}</option>
                {options?.free_devices.map((d) => (
                  <option key={d}>{d}</option>
                ))}
              </select>
            </label>
          </div>
        </Panel>

        <Panel title={tr('staff.pages.Intake.settingsTheResidentCannot')}>
          <div className="flex flex-wrap gap-3 text-sm">
            <label>
              {tr('staff.pages.Intake.language')}
              <select
                className={input + ' ml-2'}
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
              >
                <option value="en">{tr('staff.pages.Intake.english')}</option>
                <option value="es">{tr('staff.pages.Intake.spanish')}</option>
              </select>
            </label>
            <label>
              {tr('staff.pages.Intake.textSize')}
              <select
                className={input + ' ml-2'}
                value={textSize}
                onChange={(e) => setTextSize(e.target.value)}
              >
                <option>{tr('staff.pages.Intake.normal')}</option>
                <option>{tr('staff.pages.Intake.large')}</option>
                <option>{tr('staff.pages.Intake.xlarge')}</option>
              </select>
            </label>
            <label>
              {tr('staff.pages.Intake.readingLevel')}
              <select
                className={input + ' ml-2'}
                value={readingLevel}
                onChange={(e) => setReadingLevel(e.target.value)}
              >
                <option>{tr('staff.pages.Intake.standard')}</option>
                <option>{tr('staff.pages.Intake.simple')}</option>
              </select>
            </label>
            <label>
              <input
                type="checkbox"
                checked={captions}
                onChange={(e) => setCaptions(e.target.checked)}
              />{' '}
              {tr('staff.msg.captions')}
            </label>
          </div>
        </Panel>

        <Panel title={tr('staff.pages.Intake.historyAndRelease')}>
          <div className="flex flex-wrap gap-3 text-sm">
            <label>
              {tr('staff.pages.Intake.priorReturns')}
              <input
                type="number"
                min={0}
                className={input + ' ml-2 w-20'}
                value={prior}
                onChange={(e) => setPrior(Number(e.target.value))}
              />
            </label>
            {prior > 0 && (
              <label>
                {tr('staff.pages.Intake.sourceOfThatNumber')}
                <input
                  className={input + ' ml-2'}
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                />
              </label>
            )}
            {ceilingTier !== null && (
              <p className="text-sm text-ink-soft">
                {tr('staff.pages.Intake.tierCeilingPreview', { tier: ceilingTier })}
              </p>
            )}
            <label>
              {tr('staff.pages.Intake.releaseDate')}
              <input
                type="date"
                className={input + ' ml-2'}
                value={release}
                onChange={(e) => setRelease(e.target.value)}
              />
            </label>
          </div>
        </Panel>

        <Panel title={tr('staff.pages.Intake.offenseCategoriesRestrictionsCome')}>
          {options?.offense_categories.map((c) => (
            <label key={c.code} className="block text-sm">
              <input
                type="checkbox"
                checked={categories.includes(c.code)}
                onChange={(e) =>
                  setCategories(
                    e.target.checked
                      ? [...categories, c.code]
                      : categories.filter((x) => x !== c.code),
                  )
                }
              />{' '}
              {c.code} <span className="text-ink-soft">— {c.reason_text}</span>
            </label>
          ))}
        </Panel>

        <Panel title={tr('staff.pages.Intake.approvedContacts')}>
          {contacts.map((c, i) => (
            <div key={i} className="mb-2 flex flex-wrap gap-2">
              <input
                aria-label={`Contact ${i + 1} name`}
                className={input}
                placeholder={tr('staff.pages.Intake.name')}
                value={c.name}
                onChange={(e) =>
                  setContacts(
                    contacts.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)),
                  )
                }
              />
              <select
                aria-label={`Contact ${i + 1} type`}
                className={input}
                value={c.type}
                onChange={(e) =>
                  setContacts(
                    contacts.map((x, j) => (j === i ? { ...x, type: e.target.value } : x)),
                  )
                }
              >
                {options?.contact_types.map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
              <input
                aria-label={`Contact ${i + 1} number`}
                className={input}
                placeholder={tr('staff.pages.Intake.number')}
                value={c.phone}
                onChange={(e) =>
                  setContacts(
                    contacts.map((x, j) => (j === i ? { ...x, phone: e.target.value } : x)),
                  )
                }
              />
              <Btn
                type="button"
                kind="plain"
                onClick={() => setContacts(contacts.filter((_, j) => j !== i))}
              >
                {tr('staff.pages.Intake.remove')}
              </Btn>
            </div>
          ))}
          <Btn
            type="button"
            kind="plain"
            onClick={() => setContacts([...contacts, { name: '', type: 'family', phone: '' }])}
          >
            {tr('staff.pages.Intake.addContact')}
          </Btn>
        </Panel>

        <Panel title={tr('staff.pages.Intake.keepSeparateFrom')}>
          {separate.map((s, i) => (
            <div key={i} className="mb-2 flex flex-wrap gap-2">
              <input
                aria-label={`Keep-separate ${i + 1} code`}
                className={input}
                placeholder={tr('staff.pages.Intake.residentCode')}
                value={s.resident_code}
                onChange={(e) =>
                  setSeparate(
                    separate.map((x, j) => (j === i ? { ...x, resident_code: e.target.value } : x)),
                  )
                }
              />
              <input
                aria-label={`Keep-separate ${i + 1} reason`}
                className={input}
                placeholder={tr('staff.pages.Intake.reasonStaffOnly')}
                value={s.reason}
                onChange={(e) =>
                  setSeparate(
                    separate.map((x, j) => (j === i ? { ...x, reason: e.target.value } : x)),
                  )
                }
              />
              <Btn
                type="button"
                kind="plain"
                onClick={() => setSeparate(separate.filter((_, j) => j !== i))}
              >
                {tr('staff.pages.Intake.remove')}
              </Btn>
            </div>
          ))}
          <Btn
            type="button"
            kind="plain"
            onClick={() => setSeparate([...separate, { resident_code: '', reason: '' }])}
          >
            {tr('staff.pages.Intake.addEntry')}
          </Btn>
        </Panel>

        <Panel>
          <label className="block text-sm">
            {tr('staff.pages.Intake.reasonForAdmissionRecorded')}
            <input
              className={input + ' w-full'}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          <div className="mt-3">
            <Btn type="submit">{tr('staff.pages.Intake.admitResident')}</Btn>
          </div>
        </Panel>
      </form>
    </Page>
  )
}
