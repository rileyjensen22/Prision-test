import { Chess } from 'chess.js'
import type { Square } from 'chess.js'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { cn } from '../../ui/cn'

// Filled glyphs for both colours; the colour comes from the style. The ︎ asks for text form.
const GLYPH: Record<string, string> = {
  k: '♚︎',
  q: '♛︎',
  r: '♜︎',
  b: '♝︎',
  n: '♞︎',
  p: '♟︎',
}
const FILES = 'abcdefgh'

interface Props {
  fen: string
  orientation: 'white' | 'black'
  /** Who may move now: the squares only respond when it is this colour's turn. */
  canMove: boolean
  lastMove?: string | null
  /** Called with a move like e2e4 (a pawn reaching the last rank becomes a queen). */
  onMove: (lan: string) => void
}

/** The board: tap a piece, then a highlighted square. Large targets, no dragging, no text input. */
export function Board({ fen, orientation, canMove, lastMove, onMove }: Props) {
  const { t } = useTranslation()
  const [from, setFrom] = useState<Square | null>(null)
  const game = useMemo(() => new Chess(fen), [fen])
  const turn = game.turn()
  const targets = useMemo(
    () =>
      from ? new Set(game.moves({ square: from, verbose: true }).map((m) => m.to)) : new Set(),
    [from, game],
  )
  const checkSquare = useMemo(() => {
    if (!game.inCheck()) return null
    for (const row of game.board())
      for (const p of row) if (p && p.type === 'k' && p.color === turn) return p.square
    return null
  }, [game, turn])

  const ranks = orientation === 'white' ? [8, 7, 6, 5, 4, 3, 2, 1] : [1, 2, 3, 4, 5, 6, 7, 8]
  const files = orientation === 'white' ? [...FILES] : [...FILES].reverse()

  function tap(sq: Square) {
    if (!canMove) return
    if (from && targets.has(sq)) {
      const piece = game.get(from)
      const promote = piece?.type === 'p' && (sq[1] === '8' || sq[1] === '1')
      onMove(`${from}${sq}${promote ? 'q' : ''}`)
      setFrom(null)
      return
    }
    const piece = game.get(sq)
    setFrom(piece && piece.color === turn && sq !== from ? sq : null)
  }

  return (
    <div
      role="grid"
      aria-label={t('chess.board')}
      data-testid="chess-board"
      className="grid aspect-square w-full max-w-[min(100%,34rem)] grid-cols-8 overflow-hidden rounded-card border-2 border-ink"
    >
      {ranks.flatMap((rank) =>
        files.map((file) => {
          const sq = `${file}${rank}` as Square
          const piece = game.get(sq)
          const dark = (FILES.indexOf(file) + rank) % 2 === 1
          const name = piece
            ? t('chess.pieceOn', {
                color: t(`chess.${piece.color === 'w' ? 'white' : 'black'}`),
                piece: t(`chess.piece.${piece.type}`),
                square: sq,
              })
            : t('chess.emptySquare', { square: sq })
          return (
            <button
              key={sq}
              type="button"
              role="gridcell"
              aria-label={name}
              aria-pressed={from === sq}
              data-testid={`sq-${sq}`}
              onClick={() => tap(sq)}
              className={cn(
                'relative flex aspect-square items-center justify-center text-[clamp(1.6rem,6vw,3.2rem)] leading-none',
                dark ? 'bg-primary-soft' : 'bg-surface',
                lastMove &&
                  (lastMove.slice(0, 2) === sq || lastMove.slice(2, 4) === sq) &&
                  'bg-notice-soft',
                checkSquare === sq && 'ring-4 ring-inset ring-danger',
                from === sq && 'ring-4 ring-inset ring-primary',
              )}
            >
              {piece && (
                <span
                  aria-hidden="true"
                  className={cn(
                    '[font-family:"Noto_Sans_Symbols_2","DejaVu_Sans","Segoe_UI_Symbol",sans-serif]',
                    piece.color === 'w'
                      ? 'text-white [text-shadow:0_0_2px_#000,0_0_2px_#000,0_0_3px_#000]'
                      : 'text-black [text-shadow:0_0_1px_#fff]',
                  )}
                >
                  {GLYPH[piece.type]}
                </span>
              )}
              {targets.has(sq) && (
                <span
                  aria-hidden="true"
                  className="absolute size-1/4 rounded-full bg-primary opacity-70"
                />
              )}
            </button>
          )
        }),
      )}
    </div>
  )
}
