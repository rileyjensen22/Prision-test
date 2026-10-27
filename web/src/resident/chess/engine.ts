/**
 * The chess engine for games against the computer: a small alpha-beta search (negamax with
 * pruning, move ordering and a short capture search) over chess.js. Written for this project (MIT);
 * chess.js is BSD-2-Clause. It runs on the device with no network, so it works offline.
 *
 * Difficulty comes from config: search depth, and the share of moves played at random so that
 * the lower levels can be beaten.
 */
import { Chess } from 'chess.js'
import type { Move, PieceSymbol } from 'chess.js'

export interface Level {
  level: number
  depth: number
  mistake_rate: number
}

const VALUE: Record<PieceSymbol, number> = { p: 100, n: 320, b: 330, r: 500, q: 900, k: 0 }
const MATE = 100_000

// Small centre and development bonuses, from white's point of view (index 0 = a8 ... 63 = h1).
const PAWN = [
  0, 0, 0, 0, 0, 0, 0, 0, 50, 50, 50, 50, 50, 50, 50, 50, 10, 10, 20, 30, 30, 20, 10, 10, 5, 5, 10,
  25, 25, 10, 5, 5, 0, 0, 0, 20, 20, 0, 0, 0, 5, -5, -10, 0, 0, -10, -5, 5, 5, 10, 10, -20, -20, 10,
  10, 5, 0, 0, 0, 0, 0, 0, 0, 0,
]
const KNIGHT = [
  -50, -40, -30, -30, -30, -30, -40, -50, -40, -20, 0, 0, 0, 0, -20, -40, -30, 0, 10, 15, 15, 10, 0,
  -30, -30, 5, 15, 20, 20, 15, 5, -30, -30, 0, 15, 20, 20, 15, 0, -30, -30, 5, 10, 15, 15, 10, 5,
  -30, -40, -20, 0, 5, 5, 0, -20, -40, -50, -40, -30, -30, -30, -30, -40, -50,
]
const CENTRE = [
  -20, -10, -10, -10, -10, -10, -10, -20, -10, 0, 0, 0, 0, 0, 0, -10, -10, 0, 5, 10, 10, 5, 0, -10,
  -10, 5, 5, 10, 10, 5, 5, -10, -10, 0, 10, 10, 10, 10, 0, -10, -10, 10, 10, 10, 10, 10, 10, -10,
  -10, 5, 0, 0, 0, 0, 5, -10, -20, -10, -10, -10, -10, -10, -10, -20,
]
const TABLE: Partial<Record<PieceSymbol, number[]>> = { p: PAWN, n: KNIGHT, b: CENTRE, q: CENTRE }

function bonus(type: PieceSymbol, index: number, white: boolean): number {
  const table = TABLE[type]
  if (!table) return 0
  return table[white ? index : 63 - index]
}

/** Score from the side to move's point of view. */
function evaluate(game: Chess): number {
  let score = 0
  const board = game.board()
  for (let r = 0; r < 8; r++) {
    for (let f = 0; f < 8; f++) {
      const piece = board[r][f]
      if (!piece) continue
      const white = piece.color === 'w'
      const v = VALUE[piece.type] + bonus(piece.type, r * 8 + f, white)
      score += white ? v : -v
    }
  }
  return game.turn() === 'w' ? score : -score
}

function ordered(moves: Move[]): Move[] {
  const rank = (m: Move) =>
    (m.captured ? 10 * VALUE[m.captured] - VALUE[m.piece] : 0) + (m.promotion ? 800 : 0)
  return [...moves].sort((a, b) => rank(b) - rank(a))
}

interface Budget {
  until: number
  nodes: number
}

class TimeUp extends Error {}

/** Thinking time per move. A slow kiosk searches less deep rather than making a resident wait. */
export const THINK_MS = 1500

function quiesce(game: Chess, alpha: number, beta: number, depth: number, b: Budget): number {
  if ((++b.nodes & 127) === 0 && performance.now() > b.until) throw new TimeUp()
  const stand = evaluate(game)
  if (depth === 0 || stand >= beta) return stand
  alpha = Math.max(alpha, stand)
  for (const m of ordered(game.moves({ verbose: true }).filter((x) => x.captured))) {
    game.move(m)
    const score = -quiesce(game, -beta, -alpha, depth - 1, b)
    game.undo()
    if (score >= beta) return score
    alpha = Math.max(alpha, score)
  }
  return alpha
}

function search(game: Chess, depth: number, alpha: number, beta: number, ply: number, b: Budget) {
  if (game.isCheckmate()) return -MATE + ply // sooner mates score higher
  if (game.isDraw()) return 0
  if (depth === 0) return quiesce(game, alpha, beta, 2, b)
  if ((++b.nodes & 127) === 0 && performance.now() > b.until) throw new TimeUp()
  let best = -Infinity
  for (const m of ordered(game.moves({ verbose: true }))) {
    game.move(m)
    const score = -search(game, depth - 1, -beta, -alpha, ply + 1, b)
    game.undo()
    if (score > best) best = score
    alpha = Math.max(alpha, score)
    if (alpha >= beta) break
  }
  return best
}

/**
 * The best move found within `depth` plies and `thinkMs`. It searches one ply deeper at a time and
 * keeps the last complete answer, so the time limit never leaves it without a move.
 */
export function bestMove(fen: string, depth: number, thinkMs = THINK_MS): string | null {
  const game = new Chess(fen)
  const moves = ordered(game.moves({ verbose: true }))
  if (!moves.length) return null
  const b: Budget = { until: performance.now() + thinkMs, nodes: 0 }
  let best = moves[0]
  let order = moves
  for (let d = 1; d <= depth; d++) {
    let bestHere = order[0]
    let bestScore = -Infinity
    try {
      for (const m of order) {
        game.move(m)
        let score: number
        try {
          score = -search(game, d - 1, -MATE, MATE, 1, b)
        } finally {
          game.undo()
        }
        if (score > bestScore) {
          bestScore = score
          bestHere = m
        }
      }
    } catch (e) {
      if (e instanceof TimeUp) break
      throw e
    }
    best = bestHere
    order = [bestHere, ...order.filter((m) => m !== bestHere)]
    if (bestScore > MATE - 100) break // a forced mate is found; searching deeper cannot improve it
  }
  return best.lan
}

/** The move the engine plays at a level: usually the best one, sometimes a random legal move. */
export function chooseMove(
  fen: string,
  level: Level,
  random: () => number = Math.random,
  thinkMs = THINK_MS,
): string | null {
  const game = new Chess(fen)
  const legal = game.moves({ verbose: true })
  if (!legal.length) return null
  if (random() < level.mistake_rate) return legal[Math.floor(random() * legal.length)].lan
  return bestMove(fen, level.depth, thinkMs)
}
