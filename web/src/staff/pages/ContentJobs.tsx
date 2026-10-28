import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { errorText, post } from '../api'
import { useAuth } from '../auth'
import { Badge, Btn, ErrorLine, Notice, Page, Panel, Table, Td, Th, useLoad } from '../ui'

interface Source {
  id: number
  name: string
  kind: string
  base_url: string | null
  active: boolean
  protected: boolean
}
interface Job {
  id: number
  code: string
  title: string
  task_type: string
  active: boolean
  participants: number
}

const TYPES = ['transcription_public_domain', 'captioning', 'labeling_non_personal']

export default function ContentJobs() {
  const { t: tr } = useTranslation()

  const { user } = useAuth()
  const admin = user?.role === 'admin'
  const sources = useLoad<Source[]>('/staff/content-sources')
  const jobs = useLoad<Job[]>('/staff/jobs')
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [job, setJob] = useState({ code: '', title: '', task_type: TYPES[0], description: '' })
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  async function run(fn: () => Promise<unknown>, ok: string) {
    try {
      await fn()
      setMsg({ kind: 'ok', text: ok })
      await Promise.all([sources.reload(), jobs.reload()])
    } catch (e) {
      setMsg({ kind: 'err', text: errorText(e) })
    }
  }

  return (
    <Page title={tr('staff.pages.ContentJobs.contentSourcesAndJobs')}>
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      <Panel title={tr('staff.pages.ContentJobs.approvedContentSources')}>
        <p className="mb-2 text-sm text-ink-soft">
          {tr('staff.pages.ContentJobs.nothingOutsideThisList')}
        </p>
        <ErrorLine error={sources.error} />
        <Table data-testid="sources">
          <thead>
            <tr>
              <Th>{tr('staff.pages.ContentJobs.name')}</Th>
              <Th>{tr('staff.pages.ContentJobs.kind')}</Th>
              <Th>{tr('staff.pages.ContentJobs.address')}</Th>
              <Th>{tr('staff.pages.ContentJobs.status')}</Th>
              <Th></Th>
            </tr>
          </thead>
          <tbody>
            {(sources.data ?? []).map((s) => (
              <tr key={s.id}>
                <Td>{s.name}</Td>
                <Td>{s.kind}</Td>
                <Td>{s.base_url ?? 'built in'}</Td>
                <Td>
                  <Badge tone={s.active ? 'green' : 'gray'}>{s.active ? 'approved' : 'off'}</Badge>
                </Td>
                <Td>
                  {s.protected && (
                    <Badge tone="amber">{tr('staff.pages.ContentJobs.protectedBaseline')}</Badge>
                  )}
                  {admin && !s.protected && (
                    <Btn
                      kind="plain"
                      onClick={() =>
                        void run(
                          () =>
                            post(`/staff/content-sources/${s.id}/active`, { active: !s.active }),
                          'Updated.',
                        )
                      }
                    >
                      {s.active ? 'Turn off' : 'Approve'}
                    </Btn>
                  )}
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
        {admin && (
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <input
              aria-label={tr('staff.pages.ContentJobs.sourceName')}
              placeholder={tr('staff.pages.ContentJobs.name')}
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="rounded-ctl border px-2 py-1"
            />
            <input
              aria-label={tr('staff.pages.ContentJobs.sourceAddress')}
              placeholder={tr('staff.pages.ContentJobs.https')}
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="rounded-ctl border px-2 py-1"
            />
            <Btn
              disabled={name.trim().length < 3}
              onClick={() =>
                void run(
                  () => post('/staff/content-sources', { name, kind: 'external', base_url: url }),
                  'Source added.',
                )
              }
            >
              {tr('staff.pages.ContentJobs.addExternalSource')}
            </Btn>
          </div>
        )}
      </Panel>

      <Panel title={tr('staff.pages.ContentJobs.jobListings')}>
        <p className="mb-2 text-sm text-ink-soft">
          {tr('staff.pages.ContentJobs.jobsAreVoluntaryAnd')}
        </p>
        <ErrorLine error={jobs.error} />
        <Table data-testid="job-listings">
          <thead>
            <tr>
              <Th>{tr('staff.pages.ContentJobs.code')}</Th>
              <Th>{tr('staff.pages.ContentJobs.title')}</Th>
              <Th>{tr('staff.pages.ContentJobs.taskType')}</Th>
              <Th>{tr('staff.pages.ContentJobs.participants')}</Th>
              <Th>{tr('staff.pages.ContentJobs.status')}</Th>
              <Th></Th>
            </tr>
          </thead>
          <tbody>
            {(jobs.data ?? []).map((j) => (
              <tr key={j.id}>
                <Td>{j.code}</Td>
                <Td>{j.title}</Td>
                <Td>{j.task_type}</Td>
                <Td>{j.participants}</Td>
                <Td>
                  <Badge tone={j.active ? 'green' : 'gray'}>{j.active ? 'open' : 'closed'}</Badge>
                </Td>
                <Td>
                  {admin && (
                    <Btn
                      kind="plain"
                      onClick={() =>
                        void run(
                          () => post(`/staff/jobs/${j.id}/active`, { active: !j.active }),
                          'Updated.',
                        )
                      }
                    >
                      {j.active ? 'Close' : 'Reopen'}
                    </Btn>
                  )}
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
        {admin && (
          <div className="mt-3 grid gap-2 md:grid-cols-4">
            <input
              aria-label={tr('staff.pages.ContentJobs.jobCode')}
              placeholder={tr('staff.pages.ContentJobs.code')}
              value={job.code}
              onChange={(e) => setJob({ ...job, code: e.target.value })}
              className="rounded-ctl border px-2 py-1"
            />
            <input
              aria-label={tr('staff.pages.ContentJobs.jobTitle')}
              placeholder={tr('staff.pages.ContentJobs.title')}
              value={job.title}
              onChange={(e) => setJob({ ...job, title: e.target.value })}
              className="rounded-ctl border px-2 py-1"
            />
            <select
              aria-label={tr('staff.pages.ContentJobs.taskType')}
              value={job.task_type}
              onChange={(e) => setJob({ ...job, task_type: e.target.value })}
              className="rounded-ctl border px-2 py-1"
            >
              {TYPES.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
            <input
              aria-label={tr('staff.pages.ContentJobs.jobDescription')}
              placeholder={tr('staff.pages.ContentJobs.description')}
              value={job.description}
              onChange={(e) => setJob({ ...job, description: e.target.value })}
              className="rounded-ctl border px-2 py-1"
            />
            <Btn
              disabled={job.code.length < 2 || job.title.length < 3 || !job.description}
              onClick={() => void run(() => post('/staff/jobs', job), 'Job added.')}
            >
              {tr('staff.pages.ContentJobs.addJob')}
            </Btn>
          </div>
        )}
      </Panel>
    </Page>
  )
}
