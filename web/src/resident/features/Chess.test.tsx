import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, test, vi } from 'vitest'

import '../../i18n'
import { makeView } from '../fixtures'
import { ResidentCtx } from '../ResidentContext'
import type { Ctx } from '../ResidentContext'
import { Chess } from './Chess'

afterEach(cleanup)

const open = { allowed: true, baseline: false, limits: {}, reasons: [] }
const shut = { allowed: false, baseline: false, limits: {}, reasons: [] }

function show(
  features: Record<string, typeof open>,
  request: (path: string, init?: RequestInit) => unknown,
) {
  const view = makeView()
  const value: Ctx = {
    status: 'ready',
    view,
    features: { ...view.features, ...features },
    online: true,
    stale: false,
    now: Date.now(),
    pending: 0,
    refresh: async () => {},
    request: (async (path: string, init?: RequestInit) => request(path, init)) as Ctx['request'],
    submit: async () => 'sent',
  }
  return render(
    <MemoryRouter>
      <ResidentCtx.Provider value={value}>
        <Chess />
      </ResidentCtx.Provider>
    </MemoryRouter>,
  )
}

test('the menu offers the computer, and locked human play is a disabled button with a reason', () => {
  show({ chess_engine: open, chess_human: shut }, () => ({}))
  expect(screen.getByTestId('play-engine')).toBeEnabled()
  expect(screen.getByTestId('play-human')).toBeDisabled()
  expect(screen.getByTestId('play-human')).toHaveTextContent('Not available right now')
})

test('against the computer: a move is answered, and the game is logged without a network need', async () => {
  const calls: string[] = []
  show({ chess_engine: open }, (path) => {
    calls.push(path)
    if (path === '/device/chess/config')
      return { levels: [{ level: 1, depth: 1, mistake_rate: 0 }] }
    return { id: 5 }
  })
  fireEvent.click(screen.getByTestId('level-1'))
  fireEvent.click(screen.getByTestId('play-engine'))
  await screen.findByText('Your move')
  fireEvent.click(screen.getByTestId('sq-e2'))
  fireEvent.click(screen.getByTestId('sq-e4'))
  await waitFor(() => expect(screen.getByTestId('chess-status')).toHaveTextContent('thinking'))
  await waitFor(() => expect(screen.getByTestId('chess-status')).toHaveTextContent('Your move'), {
    timeout: 5000,
  })
  expect(screen.getByLabelText('white pawn on e4')).toBeInTheDocument()
  expect(calls).toContain('/device/chess')
})

test('against the computer with no connection: the game still works', async () => {
  show({ chess_engine: open }, () => {
    throw new Error('offline')
  })
  fireEvent.click(screen.getByTestId('play-engine'))
  await screen.findByText('Your move')
  fireEvent.click(screen.getByTestId('sq-d2'))
  fireEvent.click(screen.getByTestId('sq-d4'))
  expect(screen.getByLabelText('white pawn on d4')).toBeInTheDocument()
})

const match = (over: object) => ({
  id: 9,
  status: 'active',
  you: 'white',
  your_handle: 'Quiet Heron 42',
  opponent_handle: 'Steady Otter 17',
  fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
  turn: 'white',
  moves: [],
  result: null,
  reason: null,
  draw_offer: null,
  ...over,
})

test('against a resident: only handles are shown, a move is sent as coordinates, and nothing else is sendable', async () => {
  const sent: { path: string; body: string }[] = []
  show({ chess_human: open, chess_engine: open }, (path, init) => {
    if (init?.method === 'POST') sent.push({ path, body: String(init.body) })
    return match({})
  })
  fireEvent.click(screen.getByTestId('play-human'))
  const handles = await screen.findByTestId('handles')
  expect(handles).toHaveTextContent('Quiet Heron 42')
  expect(handles).toHaveTextContent('Steady Otter 17')
  expect(document.querySelector('input, textarea')).toBeNull() // no text field exists
  fireEvent.click(screen.getByTestId('sq-g1'))
  fireEvent.click(screen.getByTestId('sq-f3'))
  await waitFor(() => expect(sent.some((s) => s.path.endsWith('/moves'))).toBe(true))
  expect(JSON.parse(sent.find((s) => s.path.endsWith('/moves'))!.body)).toEqual({ move: 'g1f3' })
  fireEvent.click(screen.getByTestId('draw-offer'))
  await waitFor(() =>
    expect(JSON.parse(sent.filter((s) => s.path.endsWith('/draw'))[0].body)).toEqual({
      action: 'offer',
    }),
  )
})

test('while waiting for an opponent the resident can stop waiting', async () => {
  show({ chess_human: open, chess_engine: open }, () => match({ status: 'waiting', fen: null }))
  fireEvent.click(screen.getByTestId('play-human'))
  expect(await screen.findByTestId('cancel-wait')).toBeInTheDocument()
  expect(screen.getByTestId('chess-status')).toHaveTextContent('Waiting for another player')
})

test('a draw offer from the other player can be accepted or declined', async () => {
  vi.useRealTimers()
  show({ chess_human: open, chess_engine: open }, () => match({ draw_offer: 'them' }))
  fireEvent.click(screen.getByTestId('play-human'))
  expect(await screen.findByTestId('draw-accept')).toBeInTheDocument()
  await act(async () => {})
})
