import { useState } from 'react'
import { Link } from 'react-router-dom'

import { errorText, post } from '../api'
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

const input = 'rounded border px-2 py-1'

export default function Intake() {
  const { data: options, error } = useLoad<Options>('/staff/intake/options')
  const [name, setName] = useState('')
  const [cell, setCell] = useState('')
  const [device, setDevice] = useState('')
  const [language, setLanguage] = useState('en')
  const [textSize, setTextSize] = useState('normal')
  const [readingLevel, setReadingLevel] = useState('standard')
  const [captions, setCaptions] = useState(false)
  const [prior, setPrior] = useState(0)
  const [source, setSource] = useState('')
  const [release, setRelease] = useState('')
  const [categories, setCategories] = useState<string[]>([])
  const [contacts, setContacts] = useState<ContactRow[]>([])
  const [separate, setSeparate] = useState<SeparateRow[]>([])
  const [reason, setReason] = useState('')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string; id?: number } | null>(null)

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
    <Page title="Intake">
      <ErrorLine error={error} />
      {msg && (
        <>
          <Notice kind={msg.kind}>{msg.text}</Notice>
          {msg.id && (
            <Link className="text-blue-700 underline" to={`/staff/residents/${msg.id}`}>
              Open the resident
            </Link>
          )}
        </>
      )}
      <form onSubmit={(e) => void submit(e)} className="space-y-4" data-testid="intake-form">
        <Panel title="Who and where">
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="block text-sm">
              Name
              <input
                className={input + ' w-full'}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label className="block text-sm">
              Cell
              <select
                className={input + ' w-full'}
                value={cell}
                onChange={(e) => setCell(e.target.value)}
              >
                <option value="">Choose…</option>
                {options?.vacant_cells.map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.code} (unit {c.unit})
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              Device
              <select
                className={input + ' w-full'}
                value={device}
                onChange={(e) => setDevice(e.target.value)}
              >
                <option value="">Choose…</option>
                {options?.free_devices.map((d) => (
                  <option key={d}>{d}</option>
                ))}
              </select>
            </label>
          </div>
        </Panel>

        <Panel title="Settings the resident cannot change">
          <div className="flex flex-wrap gap-3 text-sm">
            <label>
              Language
              <select
                className={input + ' ml-2'}
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
              >
                <option value="en">English</option>
                <option value="es">Spanish</option>
              </select>
            </label>
            <label>
              Text size
              <select
                className={input + ' ml-2'}
                value={textSize}
                onChange={(e) => setTextSize(e.target.value)}
              >
                <option>normal</option>
                <option>large</option>
                <option>xlarge</option>
              </select>
            </label>
            <label>
              Reading level
              <select
                className={input + ' ml-2'}
                value={readingLevel}
                onChange={(e) => setReadingLevel(e.target.value)}
              >
                <option>standard</option>
                <option>simple</option>
              </select>
            </label>
            <label>
              <input
                type="checkbox"
                checked={captions}
                onChange={(e) => setCaptions(e.target.checked)}
              />{' '}
              Captions
            </label>
          </div>
        </Panel>

        <Panel title="History and release">
          <div className="flex flex-wrap gap-3 text-sm">
            <label>
              Prior returns
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
                Source of that number
                <input
                  className={input + ' ml-2'}
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                />
              </label>
            )}
            <label>
              Release date
              <input
                type="date"
                className={input + ' ml-2'}
                value={release}
                onChange={(e) => setRelease(e.target.value)}
              />
            </label>
          </div>
        </Panel>

        <Panel title="Offense categories (restrictions come from configuration)">
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
              {c.code} <span className="text-gray-600">— {c.reason_text}</span>
            </label>
          ))}
        </Panel>

        <Panel title="Approved contacts">
          {contacts.map((c, i) => (
            <div key={i} className="mb-2 flex flex-wrap gap-2">
              <input
                aria-label={`Contact ${i + 1} name`}
                className={input}
                placeholder="Name"
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
                placeholder="Number"
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
                Remove
              </Btn>
            </div>
          ))}
          <Btn
            type="button"
            kind="plain"
            onClick={() => setContacts([...contacts, { name: '', type: 'family', phone: '' }])}
          >
            Add contact
          </Btn>
        </Panel>

        <Panel title="Keep separate from">
          {separate.map((s, i) => (
            <div key={i} className="mb-2 flex flex-wrap gap-2">
              <input
                aria-label={`Keep-separate ${i + 1} code`}
                className={input}
                placeholder="Resident code"
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
                placeholder="Reason (staff only)"
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
                Remove
              </Btn>
            </div>
          ))}
          <Btn
            type="button"
            kind="plain"
            onClick={() => setSeparate([...separate, { resident_code: '', reason: '' }])}
          >
            Add entry
          </Btn>
        </Panel>

        <Panel>
          <label className="block text-sm">
            Reason for admission (recorded in the audit log)
            <input
              className={input + ' w-full'}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          <div className="mt-3">
            <Btn type="submit">Admit resident</Btn>
          </div>
        </Panel>
      </form>
    </Page>
  )
}
