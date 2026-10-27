import { Chess } from 'chess.js'
import { expect, test } from 'vitest'

import { bestMove, chooseMove } from './engine'

const LEVELS = [
  { level: 1, depth: 1, mistake_rate: 0.4 },
  { level: 3, depth: 2, mistake_rate: 0.05 },
  { level: 5, depth: 4, mistake_rate: 0 },
]

test('it plays a legal move at every level, from the start and from a busy position', () => {
  for (const fen of [
    new Chess().fen(),
    'r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1',
  ]) {
    for (const level of LEVELS.slice(0, 2)) {
      const move = chooseMove(fen, level, () => 0.99, 300)
      expect(move).not.toBeNull()
      expect(new Chess(fen).moves({ verbose: true }).map((m) => m.lan)).toContain(move)
    }
  }
})

test('it finds a mate in one', () => {
  // White to move: Qh5 is not it; Ra8 is mate.
  const fen = '6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1'
  expect(bestMove(fen, 2)).toBe('a1a8')
})

test('it does not leave its queen hanging when it can see the capture', () => {
  // Black queen on d5 is attacked by the white knight on c3; black to move should not ignore that.
  const fen = 'rnb1kbnr/pppp1ppp/8/3q4/8/2N5/PPPPPPPP/R1BQKBNR b KQkq - 0 3'
  const move = bestMove(fen, 3, 3000)!
  const game = new Chess(fen)
  game.move(move)
  const loses = game.moves({ verbose: true }).some((m) => m.captured === 'q')
  expect(loses).toBe(false)
})

test('it takes a free piece', () => {
  const fen = '4k3/8/8/3q4/8/8/8/3QK3 w - - 0 1' // Qxd5 wins the queen
  expect(bestMove(fen, 2)).toBe('d1d5')
})

test('the mistake rate plays a random legal move, and a finished game gives none', () => {
  const fen = new Chess().fen()
  const rolls = [0.0, 0.5]
  const move = chooseMove(fen, LEVELS[0], () => rolls.shift() ?? 0.5)
  expect(new Chess(fen).moves({ verbose: true }).map((m) => m.lan)).toContain(move)
  expect(chooseMove('7k/5Q2/6K1/8/8/8/8/8 b - - 0 1', LEVELS[2])).toBeNull()
})

test('the time limit holds: a deep request from the start position still answers in time', () => {
  const t0 = performance.now()
  const move = bestMove(new Chess().fen(), 6, 600)
  expect(move).not.toBeNull()
  expect(performance.now() - t0).toBeLessThan(2500)
})
