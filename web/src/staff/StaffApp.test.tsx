import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, vi } from 'vitest'

import '../i18n'
import StaffApp from './StaffApp'

function mount(path = '/staff') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/staff/*" element={<StaffApp />} />
      </Routes>
    </MemoryRouter>,
  )
}

function fakeApi(role: string) {
  return vi.fn(async (url: string) => {
    const body: unknown = url.endsWith('/auth/me')
      ? { id: 1, username: `u_${role}`, role }
      : url.includes('/staff/summary')
        ? {
            residents: 3,
            pending_confirmations: 2,
            open_appeals: 1,
            overdue_appeals: 0,
            offline_devices: 0,
            outlier_flags: role === 'officer' ? null : 0,
          }
        : []
    return new Response(JSON.stringify(body), { status: 200 })
  })
}

beforeEach(() => sessionStorage.clear())
afterEach(() => vi.unstubAllGlobals())

test('signed-out staff see the sign-in form, not the dashboard', () => {
  mount()
  expect(screen.getByRole('heading', { name: 'Staff sign in' })).toBeInTheDocument()
  expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
})

test.each([
  [
    'officer',
    ['Dashboard', 'Roster', 'Config'],
    ['Confirmations', 'Appeals', 'Outliers', 'Audit log'],
  ],
  ['supervisor', ['Dashboard', 'Confirmations', 'Appeals', 'Outliers'], ['Audit log']],
  ['auditor', ['Confirmations', 'Outliers', 'Audit log'], []],
])('%s sees only the pages their role allows', async (role, shown, hidden) => {
  sessionStorage.setItem('isd.staffToken', 'tok')
  vi.stubGlobal('fetch', fakeApi(role))
  mount()
  await waitFor(() => expect(screen.getByTestId('whoami')).toHaveTextContent(role))
  const nav = screen.getByRole('navigation', { name: 'Main' })
  for (const label of shown) expect(nav).toHaveTextContent(label)
  for (const label of hidden) expect(nav).not.toHaveTextContent(label)
})

test('a role-restricted page is blocked even when opened by address', async () => {
  sessionStorage.setItem('isd.staffToken', 'tok')
  vi.stubGlobal('fetch', fakeApi('officer'))
  mount('/staff/outliers')
  expect(await screen.findByRole('alert')).toHaveTextContent('Your role cannot open this page')
})
