import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { Notice } from '../../ui/Notice'
import { EmptyState } from '../../ui/States'
import { NetworkError } from '../api'
import { BackLink, Card, EndTime } from '../components'
import { useResident } from '../ResidentContext'
import { errorCode, money } from './helpers'

interface Job {
  id: number
  title: string
  task_type: string
  description: string
  pay_per_task_cents: number
  enrolled: boolean
}
interface Data {
  pay_split: { resident_pct: number; facility_pct: number; deductions_pct: number }
  jobs: Job[]
  earnings: { earned_cents: number; paid_cents: number; pending_cents: number }
  suspended: { code: string; ends_at: string; sanction_id: number } | null
}
interface Task {
  task_id: number
  listing_id: number
  kind: string
  pay_cents: number
  task: Record<string, unknown> & { source?: string }
}
interface Log {
  event: string
  job: string
  at: string
}

export function Jobs() {
  const { t, i18n } = useTranslation()
  const { request } = useResident()
  const [data, setData] = useState<Data | null>(null)
  const [log, setLog] = useState<Log[]>([])
  const [working, setWorking] = useState<Job | null>(null)
  const load = useCallback(() => {
    request<Data>('/device/jobs')
      .then(setData)
      .catch(() => {})
    request<Log[]>('/device/jobs/work-log')
      .then(setLog)
      .catch(() => {})
  }, [request])
  useEffect(load, [load])

  async function act(id: number, what: 'join' | 'leave') {
    await request(`/device/jobs/${id}/${what}`, { method: 'POST' }).catch(() => {})
    load()
  }

  if (working)
    return (
      <Work
        job={working}
        onClose={() => {
          setWorking(null)
          load()
        }}
      />
    )

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6">
      <BackLink />
      <h1 className="text-h1 font-bold">{t('jobs.title')}</h1>
      <Card data-testid="jobs-voluntary">
        <p className="font-semibold">{t('jobs.voluntary')}</p>
        <p className="mt-2">{t('jobs.note')}</p>
        {data && (
          <p className="mt-2" data-testid="jobs-split">
            {t('jobs.split', {
              resident: data.pay_split.resident_pct,
              facility: data.pay_split.facility_pct,
              deductions: data.pay_split.deductions_pct,
            })}
          </p>
        )}
      </Card>
      {data && (
        <Card data-testid="jobs-earnings">
          <p>{t('jobs.earned', { amount: money(data.earnings.earned_cents, i18n.language) })}</p>
          <p data-testid="jobs-pending">
            {t('jobs.pending', { amount: money(data.earnings.pending_cents, i18n.language) })}
          </p>
          <p className="text-ink-soft">{t('jobs.payoutNote')}</p>
        </Card>
      )}
      {data?.suspended && (
        <Card data-testid="jobs-suspended">
          <p className="text-label font-bold">{t('jobs.suspended')}</p>
          <p>{t(`code.${data.suspended.code}`, { defaultValue: data.suspended.code })}</p>
          <p>
            <EndTime iso={data.suspended.ends_at} />
          </p>
          <Link
            to={`/resident/appeal/${data.suspended.sanction_id}`}
            className="mt-2 min-h-touch rounded-ctl bg-primary px-6 py-3 text-label font-bold text-primary-ink hover:brightness-110"
          >
            {t('home.appeal')}
          </Link>
        </Card>
      )}
      {data?.jobs.length === 0 && <EmptyState title={t('jobs.none')} />}
      <ul className="space-y-3">
        {(data?.jobs ?? []).map((j) => (
          <li key={j.id}>
            <Card data-testid={`job-${j.id}`} data-enrolled={j.enrolled}>
              <p className="text-label font-bold">{j.title}</p>
              <p>{t(`jobs.type.${j.task_type}`, { defaultValue: j.task_type })}</p>
              <p className="text-ink-soft">{j.description}</p>
              <p className="text-ink-soft">
                {t('jobs.perTask', { amount: money(j.pay_per_task_cents, i18n.language) })}
              </p>
              {j.enrolled ? (
                <div className="mt-2 flex flex-wrap items-center gap-3">
                  <span data-testid="job-joined">✓ {t('jobs.joined')}</span>
                  <button
                    disabled={!!data?.suspended}
                    onClick={() => setWorking(j)}
                    className="min-h-touch rounded-ctl bg-primary px-6 py-3 text-label font-bold text-primary-ink hover:brightness-110 disabled:opacity-40"
                  >
                    {t('jobs.work')}
                  </button>
                  <button
                    onClick={() => void act(j.id, 'leave')}
                    className="min-h-touch rounded-ctl border-2 border-ink bg-surface px-6 py-3 text-label font-bold text-ink hover:bg-surface-2"
                  >
                    {t('jobs.leave')}
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => void act(j.id, 'join')}
                  className="mt-2 min-h-touch rounded-ctl bg-primary px-6 py-3 text-label font-bold text-primary-ink hover:brightness-110"
                >
                  {t('jobs.join')}
                </button>
              )}
            </Card>
          </li>
        ))}
      </ul>
      {log.length > 0 && (
        <Card data-testid="work-log">
          <h2 className="mb-2 text-h2 font-bold">{t('jobs.history')}</h2>
          <ul className="space-y-1">
            {log.slice(0, 8).map((e, i) => (
              <li key={i}>
                {t(`jobs.event.${e.event}`)} · {e.job} ·{' '}
                {new Date(e.at).toLocaleString(i18n.language, {
                  dateStyle: 'medium',
                  timeStyle: 'short',
                })}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}

function Work({ job, onClose }: { job: Job; onClose: () => void }) {
  const { t, i18n } = useTranslation()
  const { request } = useResident()
  const [task, setTask] = useState<Task | null>(null)
  const [answer, setAnswer] = useState('')
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const fetchTask = useCallback(async () => {
    setResult(null)
    setMessage(null)
    try {
      const next = await request<Task>(`/device/jobs/${job.id}/task`)
      setTask(next)
      setAnswer(next.kind === 'transcription_public_domain' ? String(next.task.scan ?? '') : '')
    } catch (e) {
      setTask(null)
      setMessage(
        e instanceof NetworkError
          ? t('calls.needsConnection')
          : t(`jobs.err.${errorCode(e)}`, { defaultValue: t('jobs.err.ERROR') }),
      )
    }
  }, [request, job.id, t])
  useEffect(() => {
    void fetchTask()
  }, [fetchTask])

  async function submit() {
    if (!task) return
    try {
      const r = await request<{ accepted: boolean; reason: string; earned_cents: number }>(
        `/device/jobs/tasks/${task.task_id}/submit`,
        { method: 'POST', body: JSON.stringify({ answer }) },
      )
      setResult({
        ok: r.accepted,
        text: r.accepted
          ? t('jobs.accepted', { amount: money(r.earned_cents, i18n.language) })
          : t(`jobs.refused.${r.reason}`, { defaultValue: t('jobs.refused.DEFAULT') }),
      })
      setTask(null)
    } catch (e) {
      setMessage(
        e instanceof NetworkError
          ? t('calls.needsConnection')
          : t(`jobs.err.${errorCode(e)}`, { defaultValue: t('jobs.err.ERROR') }),
      )
    }
  }

  const field = 'w-full rounded-ctl border-2 border-ink bg-surface p-3 text-body'
  const spec = task?.task ?? {}
  return (
    <div className="mx-auto w-full max-w-5xl space-y-6">
      <button
        onClick={onClose}
        className="min-h-touch rounded-ctl border-2 border-ink bg-surface px-6 py-3 text-label font-bold text-ink hover:bg-surface-2"
      >
        ← {t('jobs.stop')}
      </button>
      <h1 className="text-h1 font-bold">{job.title}</h1>
      <p>{t('jobs.voluntary')}</p>
      {message && (
        <Notice tone="danger" role="alert" data-testid="work-message">
          {message}
        </Notice>
      )}
      {result && (
        <Card data-testid="work-result" data-accepted={result.ok}>
          <p className="text-label font-bold">{result.text}</p>
          <button
            onClick={() => void fetchTask()}
            className="mt-3 min-h-touch rounded-ctl bg-primary px-6 py-3 text-label font-bold text-primary-ink hover:brightness-110"
          >
            {t('jobs.nextTask')}
          </button>
        </Card>
      )}
      {task && (
        <Card data-testid="work-task" data-kind={task.kind}>
          <p className="text-ink-soft">
            {t('jobs.worth', { amount: money(task.pay_cents, i18n.language) })} ·{' '}
            {t('jobs.source', { source: String(spec.source ?? '') })}
          </p>
          {task.kind === 'transcription_public_domain' && (
            <>
              <p className="mt-3 font-semibold">{t('jobs.fixScan')}</p>
              <textarea
                aria-label={t('jobs.yourAnswer')}
                className={field}
                rows={3}
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
              />
            </>
          )}
          {task.kind === 'captioning' && (
            <>
              <p className="mt-3 text-label" data-testid="work-scene">
                {String(spec.scene)}
              </p>
              <p className="mt-3 font-semibold">{t('jobs.writeCaption')}</p>
              <input
                aria-label={t('jobs.yourAnswer')}
                className={field}
                maxLength={140}
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
              />
            </>
          )}
          {task.kind === 'labeling_non_personal' && (
            <>
              <p className="mt-3 text-label" data-testid="work-item">
                “{String(spec.item)}”
              </p>
              <fieldset className="mt-3 space-y-2">
                <legend className="font-semibold">{t('jobs.pickLabel')}</legend>
                {((spec.options as string[]) ?? []).map((o) => (
                  <label key={o} className="flex items-center gap-3 text-label">
                    <input
                      type="radio"
                      name="label"
                      checked={answer === o}
                      onChange={() => setAnswer(o)}
                    />
                    {t(`jobs.label.${o}`, { defaultValue: o })}
                  </label>
                ))}
              </fieldset>
            </>
          )}
          <button
            disabled={!answer.trim()}
            onClick={() => void submit()}
            className="mt-4 min-h-touch rounded-ctl bg-primary px-6 py-3 text-label font-bold text-primary-ink hover:brightness-110 disabled:opacity-40"
          >
            {t('jobs.handIn')}
          </button>
        </Card>
      )}
    </div>
  )
}
