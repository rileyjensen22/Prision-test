import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import '../../i18n'
import { makeView } from '../fixtures'
import { ResidentCtx } from '../ResidentContext'
import type { Ctx } from '../ResidentContext'
import { Reentry } from './Reentry'

const data = (countdown: object | null) => ({
  countdown,
  checklist: [
    {
      code: 'HOUSING',
      title: { en: 'A place to stay', es: 'Un lugar donde vivir' },
      detail: { en: 'Plan it.', es: 'Planéelo.' },
      status: 'done',
    },
    {
      code: 'EMPLOYMENT',
      title: { en: 'Work or training', es: 'Trabajo' },
      detail: { en: 'Finish the course.', es: 'Termine el curso.' },
      status: 'todo',
    },
  ],
  progress: { done: 1, resolved: 1, total: 2 },
  courses: [
    {
      code: 'JOBS101',
      title: { en: 'Job readiness', es: 'Preparación' },
      lessons: 3,
      lessons_done: 1,
      completed: false,
    },
  ],
  resources: [
    {
      code: 'SAMPLE_WORK',
      category: 'employment',
      title: { en: 'Sample Workforce Center', es: 'Centro de ejemplo' },
      description: { en: 'Made up.', es: 'Inventado.' },
      phone: '555-0102',
    },
  ],
})

function show(payload: ReturnType<typeof data>, fail = false) {
  const view = makeView()
  const value: Ctx = {
    status: 'ready',
    view,
    features: view.features,
    online: true,
    stale: false,
    now: Date.now(),
    pending: 0,
    refresh: async () => {},
    request: (async () => {
      if (fail) throw new Error('offline')
      return payload
    }) as Ctx['request'],
    submit: async () => 'sent',
  }
  return render(
    <MemoryRouter>
      <ResidentCtx.Provider value={value}>
        <Reentry />
      </ResidentCtx.Provider>
    </MemoryRouter>,
  )
}

test('shows the countdown, checklist progress, courses and resources', async () => {
  show(data({ release_date: '2027-01-01', days_left: 45, weeks_left: 6 }))
  expect(await screen.findByText('45 days')).toBeInTheDocument()
  expect(screen.getByTestId('reentry-progress')).toHaveTextContent('1 of 2 done')
  expect(screen.getByTestId('reentry-item-HOUSING')).toHaveAttribute('data-status', 'done')
  expect(screen.getByTestId('reentry-item-EMPLOYMENT')).toHaveTextContent('Not started')
  expect(screen.getByRole('link', { name: /Job readiness/ })).toHaveAttribute(
    'href',
    '/resident/course/JOBS101',
  )
  expect(screen.getByTestId('reentry-resources')).toHaveTextContent('555-0102')
})

test('one day is singular, and no date says so without a countdown', async () => {
  show(data({ release_date: '2027-01-01', days_left: 1, weeks_left: 0 }))
  expect(await screen.findByText('1 day')).toBeInTheDocument()
})

test('with no release date the page still works', async () => {
  show(data(null))
  expect(await screen.findByText(/have not set a release date/)).toBeInTheDocument()
  expect(screen.getByTestId('reentry-item-HOUSING')).toBeInTheDocument()
})

test('offline, the last saved copy opens with the countdown recomputed from the device clock', async () => {
  localStorage.clear()
  const future = new Date(Date.now() + 10 * 86_400_000)
  const date = `${future.getFullYear()}-${String(future.getMonth() + 1).padStart(2, '0')}-${String(future.getDate()).padStart(2, '0')}`
  show(data({ release_date: date, days_left: 99, weeks_left: 14 })) // online: saves a copy
  expect(await screen.findByText('99 days')).toBeInTheDocument()
  cleanup()
  show(data(null), true) // offline: the request fails
  expect(await screen.findByTestId('reentry-saved')).toBeInTheDocument()
  expect(screen.getByText('10 days')).toBeInTheDocument()
  expect(screen.getByTestId('reentry-item-HOUSING')).toBeInTheDocument()
})

test('offline with nothing saved says it needs a connection', async () => {
  localStorage.clear()
  show(data(null), true)
  expect(await screen.findByText(/connection|conexión/i)).toBeInTheDocument()
})
