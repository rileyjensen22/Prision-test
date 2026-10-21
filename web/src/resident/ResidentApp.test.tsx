import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, vi } from 'vitest'

import '../i18n'
import { makeView } from './fixtures'
import ResidentApp from './ResidentApp'
import type { ResidentView } from './types'

function mount() {
  return render(
    <MemoryRouter initialEntries={['/resident']}>
      <Routes>
        <Route path="/resident/*" element={<ResidentApp />} />
      </Routes>
    </MemoryRouter>,
  )
}
const respond = (body: ResidentView | null, status = 200) =>
  vi.fn(async () => new Response(JSON.stringify(body), { status }))

beforeEach(() => localStorage.clear())
afterEach(() => vi.unstubAllGlobals())

test('device without a token shows the setup message', () => {
  mount()
  expect(screen.getByTestId('status-message')).toHaveTextContent('not set up')
})

test('home shows tier, lock reason, end time, appeal and the Request staff button', async () => {
  localStorage.setItem('isd.deviceToken', 'tok')
  vi.stubGlobal('fetch', respond(makeView()))
  mount()
  await waitFor(() => expect(screen.getByTestId('tier-label')).toHaveTextContent('Tier 3'))
  expect(screen.getByTestId('lock-title')).toHaveTextContent('Disruptive behavior')
  expect(screen.getByTestId('lock-until').querySelector('time')).toHaveAttribute(
    'datetime',
    '2026-03-03T08:00:00Z',
  )
  expect(screen.getByRole('link', { name: 'Appeal' })).toBeInTheDocument()
  expect(screen.getByTestId('tile-calls')).toHaveAttribute('data-allowed', 'false')
  expect(screen.getByTestId('tile-commissary')).toHaveAttribute('data-allowed', 'true')
  expect(screen.getByTestId('tile-legal_materials')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Request staff' })).toBeEnabled()
})

test('Spanish resident gets Spanish text', async () => {
  localStorage.setItem('isd.deviceToken', 'tok')
  const v = makeView()
  v.settings.language = 'es'
  vi.stubGlobal('fetch', respond(v))
  mount()
  await waitFor(() => expect(screen.getByTestId('tier-label')).toHaveTextContent('Nivel 3'))
  expect(screen.getByRole('button', { name: 'Solicitar personal' })).toBeInTheDocument()
  expect(screen.getByTestId('lock-title')).toHaveTextContent('Conducta perturbadora')
})

test('offline request is queued, not lost', async () => {
  localStorage.setItem('isd.deviceToken', 'tok')
  const fetchMock = vi.fn()
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(makeView()), { status: 200 }))
  fetchMock.mockRejectedValue(new TypeError('network down'))
  vi.stubGlobal('fetch', fetchMock)
  mount()
  await waitFor(() => screen.getByTestId('tier-label'))
  await userEvent.click(screen.getByRole('button', { name: 'Request staff' }))
  await userEvent.click(screen.getByRole('button', { name: 'Medical help' }))
  expect(await screen.findByTestId('request-result')).toHaveTextContent('will be sent')
  expect(JSON.parse(localStorage.getItem('isd.queue') ?? '[]')).toHaveLength(1)
})
