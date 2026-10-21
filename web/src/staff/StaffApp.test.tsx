import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import '../i18n'
import StaffApp from './StaffApp'

test('staff surface renders', () => {
  render(
    <MemoryRouter initialEntries={['/staff']}>
      <Routes>
        <Route path="/staff/*" element={<StaffApp />} />
      </Routes>
    </MemoryRouter>,
  )
  expect(screen.getByText('Staff Dashboard')).toBeInTheDocument()
})
