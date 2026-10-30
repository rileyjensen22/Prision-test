import { Chess as Rules } from 'chess.js'
import { Flag, Handshake, Monitor, Users } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import { Button } from '../../ui/Button'
import { Notice } from '../../ui/Notice'
import { NetworkError } from '../api'
import { Board } from '../chess/Board'
import { chooseMove } from '../chess/engine'
import type { Level } from '../chess/engine'
import { BackLink, Card } from '../components'
import { useResident } from '../ResidentContext'
import { errorCode } from './helpers'

// Used when the device cannot reach the server for the level list. Same values as config/chess.yaml.
const FALLBACK_LEVELS: Level[] = [
  { level: 1, depth: 1, mistake_rate: 0.4 },
  { level: 2, depth: 2, mistake_rate: 0.2 },
  { level: 3, depth: 2, mistake_rate: 0.05 },
  { level: 4, depth: 3, mistake_rate: 0 },
  { level: 5, depth: 4, mistake_rate: 0 },
]

interface MatchView {
  id: number
  status: 'waiting' | 'active' | 'finished'
  you: 'white' | 'black'
  your_handle: string
  opponent_handle: string | null
  fen: string
  turn: 'white' | 'black'
  moves: { ply: number; move: string }[]
  result: 'white' | 'black' | 'draw' | null
  reason: string | null
  draw_offer: 'you' | 'them' | null
}

type Mode = 'menu' | 'engine' | 'human'

export function Chess() {
  const { t } = useTranslation()
  const { features } = useResident()
  const navigate = useNavigate()
  const [mode, setMode] = useState<Mode>('menu')
  const [level, setLevel] = useState(2)
  const engineOk = features['chess']?.allowed === true
  const humanOk = features['chess_human']?.allowed === true

  useEffect(() => {
    if (features['chess'] && !engineOk && !humanOk)
      navigate('/resident/locks?feature=chess', { replace: true })
  }, [features, engineOk, humanOk, navigate])

  if (mode === 'engine') return <EngineGame level={level} onExit={() => setMode('menu')} />
  if (mode === 'human') return <HumanGame onExit={() => setMode('menu')} />

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6">
      <BackLink />
      <h1 className="text-h1 font-bold">{t('chess.title')}</h1>
      <Card>
        <h2 className="text-h2 font-bold">{t('chess.vsComputer')}</h2>
        <p className="mt-1 text-ink-soft">{t('chess.vsComputerHelp')}</p>
        <div className="mt-3 flex flex-wrap gap-2" role="radiogroup" aria-label={t('chess.level')}>
          {FALLBACK_LEVELS.map((l) => (
            <button
              key={l.level}
              role="radio"
              aria-checked={level === l.level}
              data-testid={`level-${l.level}`}
              onClick={() => setLevel(l.level)}
              className={`min-h-touch min-w-touch rounded-ctl border-2 px-5 py-3 text-label font-bold ${
                level === l.level ? 'border-primary bg-primary-soft' : 'border-line bg-surface'
              }`}
            >
              {l.level}
            </button>
          ))}
        </div>
        <p className="mt-2 text-sm text-ink-soft">{t('chess.levelHelp')}</p>
        <Button
          className="mt-4"
          variant="primary"
          icon={Monitor}
          disabled={!engineOk}
          onClick={() => setMode('engine')}
          data-testid="play-engine"
        >
          {t('chess.playComputer')}
        </Button>
      </Card>
      <Card>
        <h2 className="text-h2 font-bold">{t('chess.vsPerson')}</h2>
        <p className="mt-1 text-ink-soft">{t('chess.vsPersonHelp')}</p>
        <Button
          className="mt-4"
          variant="primary"
          icon={Users}
          disabled={!humanOk}
          onClick={() => setMode('human')}
          data-testid="play-human"
        >
          {humanOk ? t('chess.playPerson') : t('chess.personLocked')}
        </Button>
      </Card>
    </div>
  )
}

function resultText(
  t: (k: string, o?: Record<string, unknown>) => string,
  result: string | null,
  reason: string | null,
  you: 'white' | 'black',
): string {
  if (!result) return t(`chess.reason.${reason ?? 'cancelled'}`)
  const outcome = result === 'draw' ? 'draw' : result === you ? 'won' : 'lost'
  return `${t(`chess.result.${outcome}`)} ${t(`chess.reason.${reason ?? 'agreed'}`)}`
}

// ---------------- against the computer: the whole game is on the device ----------------
function EngineGame({ level, onExit }: { level: number; onExit: () => void }) {
  const { t } = useTranslation()
  const { request, features } = useResident()
  const game = useRef(new Rules())
  const [fen, setFen] = useState(game.current.fen())
  const [last, setLast] = useState<string | null>(null)
  const [thinking, setThinking] = useState(false)
  const [ended, setEnded] = useState<{ result: 'white' | 'black' | 'draw'; reason: string } | null>(
    null,
  )
  const logId = useRef<number | null>(null)
  const levels = useRef<Level[]>(FALLBACK_LEVELS)
  const allowed = features['chess']?.allowed === true

  useEffect(() => {
    // Logging and the level list are best effort: the game itself never needs the network.
    request<{ levels: Level[] }>('/device/chess/config')
      .then((c) => (levels.current = c.levels))
      .catch(() => {})
    request<{ id: number }>('/device/chess', {
      method: 'POST',
      body: JSON.stringify({ opponent: 'engine', level }),
    })
      .then((g) => (logId.current = g.id))
      .catch(() => {})
  }, [request, level])

  const finish = useCallback(
    (result: 'white' | 'black' | 'draw', reason: string) => {
      setEnded({ result, reason })
      if (logId.current !== null)
        void request(`/device/chess/${logId.current}/result`, {
          method: 'POST',
          body: JSON.stringify({ result, reason }),
        }).catch(() => {})
    },
    [request],
  )

  const checkEnd = useCallback((): boolean => {
    const g = game.current
    if (g.isCheckmate()) finish(g.turn() === 'w' ? 'black' : 'white', 'checkmate')
    else if (g.isStalemate()) finish('draw', 'stalemate')
    else if (g.isInsufficientMaterial()) finish('draw', 'insufficient')
    else if (g.isThreefoldRepetition()) finish('draw', 'repetition')
    else if (g.isDraw()) finish('draw', 'seventy_five')
    else return false
    return true
  }, [finish])

  function play(lan: string) {
    const g = game.current
    try {
      g.move({ from: lan.slice(0, 2), to: lan.slice(2, 4), promotion: lan[4] })
    } catch {
      return
    }
    setLast(lan)
    setFen(g.fen())
    if (checkEnd()) return
    setThinking(true)
    // Let the board repaint before the search starts.
    setTimeout(() => {
      const cfg = levels.current.find((l) => l.level === level) ?? FALLBACK_LEVELS[1]
      const reply = chooseMove(g.fen(), cfg)
      if (reply) {
        g.move({ from: reply.slice(0, 2), to: reply.slice(2, 4), promotion: reply[4] })
        setLast(reply)
        setFen(g.fen())
        checkEnd()
      }
      setThinking(false)
    }, 40)
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-4">
      <h1 className="text-h2 font-bold">{t('chess.vsComputerLevel', { level })}</h1>
      {!allowed && <Notice tone="notice">{t('chess.lockedNow')}</Notice>}
      <Status
        text={
          ended
            ? resultText(t, ended.result, ended.reason, 'white')
            : thinking
              ? t('chess.thinking')
              : t('chess.yourTurn')
        }
      />
      <Board
        fen={fen}
        orientation="white"
        canMove={allowed && !ended && !thinking}
        lastMove={last}
        onMove={play}
      />
      <div className="flex flex-wrap gap-3">
        {!ended && (
          <Button icon={Flag} onClick={() => finish('black', 'resigned')} data-testid="resign">
            {t('chess.resign')}
          </Button>
        )}
        <Button variant="primary" onClick={onExit} data-testid="chess-exit">
          {ended ? t('chess.done') : t('chess.leave')}
        </Button>
      </div>
    </div>
  )
}

function Status({ text }: { text: string }) {
  return (
    <p role="status" data-testid="chess-status" className="text-label font-bold">
      {text}
    </p>
  )
}

// ---------------- against another resident: the server keeps the match ----------------
function HumanGame({ onExit }: { onExit: () => void }) {
  const { t } = useTranslation()
  const { request, online, features } = useResident()
  const [match, setMatch] = useState<MatchView | null>(null)
  const [error, setError] = useState<string | null>(null)
  const started = useRef(false)
  const allowed = features['chess_human']?.allowed === true

  const fail = useCallback(
    (e: unknown) =>
      setError(
        e instanceof NetworkError
          ? t('chess.needsConnection')
          : t(`chess.err.${errorCode(e)}`, { defaultValue: t('chess.err.ERROR') }),
      ),
    [t],
  )

  useEffect(() => {
    if (started.current) return
    started.current = true
    request<MatchView>('/device/chess', {
      method: 'POST',
      body: JSON.stringify({ opponent: 'human' }),
    })
      .then(setMatch)
      .catch(fail)
  }, [request, fail])

  // Wait for the other player: ask again every few seconds while the match is open.
  useEffect(() => {
    if (!match || match.status === 'finished') return
    const waiting = match.status === 'waiting' || match.turn !== match.you
    const id = setInterval(
      () =>
        request<MatchView>(`/device/chess/${match.id}`)
          .then(setMatch)
          .catch(() => {}),
      waiting ? 2500 : 6000,
    )
    return () => clearInterval(id)
  }, [match, request])

  async function send(path: string, body?: unknown) {
    if (!match) return
    setError(null)
    try {
      setMatch(
        await request<MatchView>(`/device/chess/${match.id}/${path}`, {
          method: 'POST',
          ...(body ? { body: JSON.stringify(body) } : {}),
        }),
      )
    } catch (e) {
      fail(e)
    }
  }

  if (!match)
    return (
      <div className="mx-auto w-full max-w-3xl space-y-4">
        <h1 className="text-h2 font-bold">{t('chess.vsPerson')}</h1>
        {error ? <Notice tone="danger">{error}</Notice> : <Status text={t('chess.finding')} />}
        <Button onClick={onExit}>{t('chess.back')}</Button>
      </div>
    )

  const last = match.moves.length ? match.moves[match.moves.length - 1].move : null
  const myTurn = match.status === 'active' && match.turn === match.you

  return (
    <div className="mx-auto w-full max-w-3xl space-y-4">
      <h1 className="text-h2 font-bold">{t('chess.vsPerson')}</h1>
      {error && (
        <Notice tone="danger" role="alert">
          {error}
        </Notice>
      )}
      {!online && <Notice tone="notice">{t('chess.needsConnection')}</Notice>}
      {!allowed && match.status === 'active' && (
        <Notice tone="notice">{t('chess.lockedNow')}</Notice>
      )}
      {match.status === 'waiting' ? (
        <>
          <Status text={t('chess.waiting')} />
          <Button onClick={() => void send('resign').then(onExit)} data-testid="cancel-wait">
            {t('chess.cancelWait')}
          </Button>
        </>
      ) : (
        <>
          <p data-testid="handles">
            {t('chess.you', { handle: match.your_handle, color: t(`chess.${match.you}`) })}
            {' · '}
            {t('chess.opponent', { handle: match.opponent_handle })}
          </p>
          <Status
            text={
              match.status === 'finished'
                ? resultText(t, match.result, match.reason, match.you)
                : myTurn
                  ? t('chess.yourTurn')
                  : t('chess.theirTurn')
            }
          />
          <Board
            fen={match.fen}
            orientation={match.you}
            canMove={myTurn && allowed}
            lastMove={last}
            onMove={(lan) => void send('moves', { move: lan })}
          />
          {match.status === 'active' && (
            <div className="flex flex-wrap gap-3">
              {match.draw_offer === 'them' ? (
                <>
                  <Button
                    icon={Handshake}
                    onClick={() => void send('draw', { action: 'accept' })}
                    data-testid="draw-accept"
                  >
                    {t('chess.acceptDraw')}
                  </Button>
                  <Button onClick={() => void send('draw', { action: 'decline' })}>
                    {t('chess.declineDraw')}
                  </Button>
                </>
              ) : (
                <Button
                  icon={Handshake}
                  disabled={match.draw_offer === 'you'}
                  onClick={() => void send('draw', { action: 'offer' })}
                  data-testid="draw-offer"
                >
                  {match.draw_offer === 'you' ? t('chess.drawOffered') : t('chess.offerDraw')}
                </Button>
              )}
              <Button icon={Flag} onClick={() => void send('resign')} data-testid="resign">
                {t('chess.resign')}
              </Button>
            </div>
          )}
          <p className="text-sm text-ink-soft">{t('chess.noPenalty')}</p>
        </>
      )}
      {match.status !== 'waiting' && (
        <Button variant="primary" onClick={onExit} data-testid="chess-exit">
          {match.status === 'finished' ? t('chess.done') : t('chess.back')}
        </Button>
      )}
    </div>
  )
}
