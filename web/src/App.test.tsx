import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import App from './App'
import './i18n'

test('resident surface renders with Request staff button', () => {
  render(
    <MemoryRouter initialEntries={['/resident']}>
      <App />
    </MemoryRouter>,
  )
  expect(screen.getByRole('button', { name: 'Request staff' })).toBeInTheDocument()
})

test('staff surface renders', () => {
  render(
    <MemoryRouter initialEntries={['/staff']}>
      <App />
    </MemoryRouter>,
  )
  expect(screen.getByText('Staff Dashboard')).toBeInTheDocument()
})
