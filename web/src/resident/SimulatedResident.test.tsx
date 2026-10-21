import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, vi } from 'vitest'

import i18n, { createI18n } from '../i18n'
import { makeView } from './fixtures'
import { SimulatedResident } from './SimulatedResident'

let fetchSpy: ReturnType<typeof vi.fn>
beforeEach(() => {
  fetchSpy = vi.fn(() => {
    throw new Error('the simulation must not touch the network')
  })
  vi.stubGlobal('fetch', fetchSpy)
  localStorage.clear()
})
afterEach(() => vi.unstubAllGlobals())

test('sandbox shows the SIMULATION banner and the same lock screens, with no network calls', async () => {
  render(<SimulatedResident view={makeView({ simulation: true })} mode="sandbox" />)
  expect(screen.getByText('SIMULATION')).toBeInTheDocument()
  expect(screen.getByTestId('lock-title')).toHaveTextContent('Disruptive behavior')
  expect(screen.getByTestId('tile-calls')).toHaveAttribute('data-allowed', 'false')

  // staff can click around: Appeal opens the appeal screen inside the simulation
  await userEvent.click(screen.getByRole('link', { name: 'Appeal' }))
  await userEvent.click(screen.getByRole('button', { name: 'Send appeal' }))
  expect(await screen.findByTestId('appeal-result')).toBeInTheDocument()
  expect(fetchSpy).not.toHaveBeenCalled() // nothing was sent
  expect(localStorage.length).toBe(0) // nothing was saved on this device either
})

test('mirror is read-only, follows the reported screen, and shows no simulation banner', () => {
  render(<SimulatedResident view={makeView()} mode="mirror" path="/resident/tier" />)
  expect(screen.getByTestId('sim-screen')).toHaveAttribute('data-mode', 'mirror')
  expect(screen.getByTestId('sim-body')).toHaveClass('pointer-events-none')
  expect(screen.getByRole('heading', { name: 'Tier 3' })).toBeInTheDocument() // the tier details screen
  expect(screen.queryByText('SIMULATION')).not.toBeInTheDocument()
})

test('screens with live content show a stand-in instead of fetching anything', () => {
  render(<SimulatedResident view={makeView()} mode="mirror" path="/resident/feature/commissary" />)
  expect(screen.getByTestId('sim-live-screen')).toHaveTextContent('Commissary')
  expect(screen.getByTestId('sim-live-screen')).toHaveTextContent('Live content is not shown')
  expect(fetchSpy).not.toHaveBeenCalled()
})

test('a Spanish simulation does not change the app language', () => {
  const v = makeView()
  v.settings.language = 'es'
  render(<SimulatedResident view={v} mode="sandbox" />)
  expect(screen.getByTestId('lock-title')).toHaveTextContent('Conducta perturbadora')
  expect(i18n.language).toBe('en')
  expect(createI18n('es').t('request.button')).toBe('Solicitar personal')
  expect(i18n.language).toBe('en')
})

test('works inside the staff app, which already has its own router', async () => {
  render(
    <MemoryRouter initialEntries={['/staff/view-as']}>
      <SimulatedResident view={makeView({ simulation: true })} mode="sandbox" />
    </MemoryRouter>,
  )
  expect(await screen.findByTestId('lock-title')).toHaveTextContent('Disruptive behavior')
})
