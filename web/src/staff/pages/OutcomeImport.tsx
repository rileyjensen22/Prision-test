import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { errorText, post } from '../api'
import { Btn, ErrorLine, FIELD, Notice, Panel, Table, Td, Th } from '../ui'

interface Result {
  dry_run: boolean
  rows: number
  counts: { new: number; correction: number; unchanged: number }
  problems: { line: number; code: string; message: string }[]
  preview: {
    line: number
    resident_code: string
    window_months: number
    outcome: string
    action: string
  }[]
  imported: boolean
  batch_id?: number
}

/** Admin CSV import of outcomes: always previews first, and only applies a file with no problems. */
export function OutcomeImport({ onImported }: { onImported: () => void }) {
  const { t } = useTranslation()
  const [text, setText] = useState('')
  const [source, setSource] = useState('')
  const [preview, setPreview] = useState<Result | null>(null)
  const [done, setDone] = useState<Result | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function run(dry: boolean) {
    setError(null)
    try {
      const out = await post<Result>('/staff/outcomes/import', {
        csv_text: text,
        source,
        label: 'upload',
        dry_run: dry,
      })
      if (dry) {
        setPreview(out)
        setDone(null)
      } else {
        setDone(out)
        setPreview(null)
        setText('')
        onImported()
      }
    } catch (e) {
      setError(errorText(e))
    }
  }

  async function pick(file: File | undefined) {
    if (!file) return
    setText(await file.text())
    setPreview(null)
    setDone(null)
  }

  const clean = preview && preview.problems.length === 0 && preview.rows > 0

  return (
    <Panel title={t('staff.outcomeImport.title')}>
      <p className="mb-2 text-sm">{t('staff.outcomeImport.help')}</p>
      <ErrorLine error={error} />
      <div className="flex flex-wrap gap-2">
        <input
          type="file"
          accept=".csv,text/csv"
          aria-label={t('staff.outcomeImport.file')}
          onChange={(e) => void pick(e.target.files?.[0])}
        />
        <input
          aria-label={t('staff.outcomeImport.source')}
          placeholder={t('staff.outcomeImport.source')}
          className={`${FIELD} max-w-xs`}
          value={source}
          onChange={(e) => setSource(e.target.value)}
        />
        <Btn disabled={!text || source.trim().length < 3} onClick={() => void run(true)}>
          {t('staff.outcomeImport.preview')}
        </Btn>
      </div>
      {done && (
        <Notice kind="ok" data-testid="import-done">
          {t('staff.outcomeImport.done', { n: done.counts.new + done.counts.correction })}
        </Notice>
      )}
      {preview && (
        <div className="mt-3 space-y-2" data-testid="import-preview">
          <p>
            {t('staff.outcomeImport.counts', {
              rows: preview.rows,
              added: preview.counts.new,
              corrections: preview.counts.correction,
              unchanged: preview.counts.unchanged,
            })}
          </p>
          {preview.problems.length > 0 && (
            <Notice kind="err" data-testid="import-problems">
              {t('staff.outcomeImport.problems')}{' '}
              {preview.problems.map((p) => `${p.line}: ${p.code}`).join(', ')}
            </Notice>
          )}
          <Table>
            <thead>
              <tr>
                <Th>{t('staff.outcomeImport.line')}</Th>
                <Th>{t('staff.outcomeImport.resident')}</Th>
                <Th>{t('staff.outcomeImport.window')}</Th>
                <Th>{t('staff.outcomeImport.outcome')}</Th>
                <Th>{t('staff.outcomeImport.action')}</Th>
              </tr>
            </thead>
            <tbody>
              {preview.preview.map((p) => (
                <tr key={p.line}>
                  <Td>{p.line}</Td>
                  <Td>{p.resident_code}</Td>
                  <Td>{p.window_months}</Td>
                  <Td>{p.outcome}</Td>
                  <Td>{t(`staff.outcomeImport.actions.${p.action}`)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <Btn disabled={!clean} onClick={() => void run(false)} data-testid="import-apply">
            {t('staff.outcomeImport.apply')}
          </Btn>
        </div>
      )}
    </Panel>
  )
}
