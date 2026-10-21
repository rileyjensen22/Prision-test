import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

import '../../i18n'
import { makeView } from '../fixtures'
import { ResidentCtx } from '../ResidentContext'
import type { Ctx } from '../ResidentContext'
import { Jobs } from './Jobs'
import { Texting } from './Texting'

function withRequest(request: Ctx['request'], ui: React.ReactNode) {
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
    request,
    submit: async () => 'sent',
  }
  return render(
    <MemoryRouter>
      <ResidentCtx.Provider value={value}>{ui}</ResidentCtx.Provider>
    </MemoryRouter>,
  )
}

test('jobs: voluntary notice, pay split, join and leave', async () => {
  let enrolled = false
  const calls: string[] = []
  const request = vi.fn(async (path: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      calls.push(path)
      enrolled = path.endsWith('/join')
    }
    return {
      pay_split: { resident_pct: 60, facility_pct: 30, deductions_pct: 10 },
      jobs: [
        {
          id: 1,
          title: 'Transcribe books',
          task_type: 'transcription_public_domain',
          description: 'Type pages',
          enrolled,
        },
      ],
    }
  }) as unknown as Ctx['request']
  withRequest(request, <Jobs />)
  expect(await screen.findByTestId('jobs-voluntary')).toHaveTextContent(
    'never changes your tier, points, or privileges',
  )
  expect(screen.getByTestId('jobs-split')).toHaveTextContent('you receive $60')
  await userEvent.click(await screen.findByRole('button', { name: 'Join' }))
  expect(await screen.findByTestId('job-joined')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Leave' }))
  await waitFor(() => expect(screen.queryByTestId('job-joined')).not.toBeInTheDocument())
  expect(calls).toEqual(['/device/jobs/1/join', '/device/jobs/1/leave'])
})

test('texting: attorney threads say messages are private and show no text', async () => {
  const request = vi.fn(async (path: string) => {
    if (path === '/device/contacts')
      return [
        { id: 1, name: 'Aunt Synthetic', type: 'family', available: true },
        { id: 2, name: 'Counsel Synthetic', type: 'attorney', available: true },
      ]
    if (path.startsWith('/device/messages?contact_id=2'))
      return [{ id: 9, direction: 'out', body: null, private: true }]
    return []
  }) as unknown as Ctx['request']
  withRequest(request, <Texting />)
  await userEvent.click(await screen.findByTestId('text-contact-attorney'))
  expect(screen.getByTestId('text-notice')).toHaveTextContent('not stored or read')
  expect(await screen.findByTestId('msg-out')).toHaveTextContent('Sent privately')
  await userEvent.click(screen.getByRole('button', { name: /←/ }))
  await userEvent.click(screen.getByTestId('text-contact-family'))
  expect(screen.getByTestId('text-notice')).toHaveTextContent('may be monitored')
})
