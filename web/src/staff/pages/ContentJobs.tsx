import { useState } from 'react'

import { errorText, post } from '../api'
import { useAuth } from '../auth'
import { Badge, Btn, ErrorLine, Notice, Page, Panel, Table, Td, Th, useLoad } from '../ui'

interface Source {
  id: number
  name: string
  kind: string
  base_url: string | null
  active: boolean
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
    <Page title="Content sources and jobs">
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      <Panel title="Approved content sources">
        <p className="mb-2 text-sm text-gray-600">
          Nothing outside this list can be shown to residents. External sources must use https.
        </p>
        <ErrorLine error={sources.error} />
        <Table data-testid="sources">
          <thead>
            <tr>
              <Th>Name</Th>
              <Th>Kind</Th>
              <Th>Address</Th>
              <Th>Status</Th>
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
                  {admin && (
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
              aria-label="Source name"
              placeholder="Name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="rounded border px-2 py-1"
            />
            <input
              aria-label="Source address"
              placeholder="https://…"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="rounded border px-2 py-1"
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
              Add external source
            </Btn>
          </div>
        )}
      </Panel>

      <Panel title="Job listings">
        <p className="mb-2 text-sm text-gray-600">
          Jobs are voluntary and never change a resident’s tier, points or privileges. Only the
          number of participants is shown here, never who. Wages, deductions and voluntariness need
          a compliance review before real use.
        </p>
        <ErrorLine error={jobs.error} />
        <Table data-testid="job-listings">
          <thead>
            <tr>
              <Th>Code</Th>
              <Th>Title</Th>
              <Th>Task type</Th>
              <Th>Participants</Th>
              <Th>Status</Th>
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
              aria-label="Job code"
              placeholder="Code"
              value={job.code}
              onChange={(e) => setJob({ ...job, code: e.target.value })}
              className="rounded border px-2 py-1"
            />
            <input
              aria-label="Job title"
              placeholder="Title"
              value={job.title}
              onChange={(e) => setJob({ ...job, title: e.target.value })}
              className="rounded border px-2 py-1"
            />
            <select
              aria-label="Task type"
              value={job.task_type}
              onChange={(e) => setJob({ ...job, task_type: e.target.value })}
              className="rounded border px-2 py-1"
            >
              {TYPES.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
            <input
              aria-label="Job description"
              placeholder="Description"
              value={job.description}
              onChange={(e) => setJob({ ...job, description: e.target.value })}
              className="rounded border px-2 py-1"
            />
            <Btn
              disabled={job.code.length < 2 || job.title.length < 3 || !job.description}
              onClick={() => void run(() => post('/staff/jobs', job), 'Job added.')}
            >
              Add job
            </Btn>
          </div>
        )}
      </Panel>
    </Page>
  )
}
