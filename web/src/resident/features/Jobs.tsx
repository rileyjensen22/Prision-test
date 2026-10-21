import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { BackLink, Card } from '../components'
import { useResident } from '../ResidentContext'

interface Job {
  id: number
  title: string
  task_type: string
  description: string
  enrolled: boolean
}
interface Data {
  pay_split: { resident_pct: number; facility_pct: number; deductions_pct: number }
  jobs: Job[]
}

export function Jobs() {
  const { t } = useTranslation()
  const { request } = useResident()
  const [data, setData] = useState<Data | null>(null)
  const load = () =>
    request<Data>('/device/jobs')
      .then(setData)
      .catch(() => {})
  useEffect(() => {
    void load()
  }, [request])

  async function act(id: number, what: 'join' | 'leave') {
    await request(`/device/jobs/${id}/${what}`, { method: 'POST' }).catch(() => {})
    await load()
  }

  return (
    <div className="space-y-6">
      <BackLink />
      <h1 className="text-3xl font-bold">{t('jobs.title')}</h1>
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
      {data?.jobs.length === 0 && <p>{t('jobs.none')}</p>}
      <ul className="space-y-3">
        {(data?.jobs ?? []).map((j) => (
          <li key={j.id}>
            <Card data-testid={`job-${j.id}`} data-enrolled={j.enrolled}>
              <p className="text-xl font-semibold">{j.title}</p>
              <p>{t(`jobs.type.${j.task_type}`, { defaultValue: j.task_type })}</p>
              <p className="opacity-80">{j.description}</p>
              {j.enrolled ? (
                <div className="mt-2 flex items-center gap-3">
                  <span data-testid="job-joined">✓ {t('jobs.joined')}</span>
                  <button
                    onClick={() => void act(j.id, 'leave')}
                    className="min-h-14 rounded-lg border-2 border-white px-6 py-3"
                  >
                    {t('jobs.leave')}
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => void act(j.id, 'join')}
                  className="mt-2 min-h-14 rounded-lg bg-green-700 px-6 py-3 font-semibold"
                >
                  {t('jobs.join')}
                </button>
              )}
            </Card>
          </li>
        ))}
      </ul>
    </div>
  )
}
