import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { NetworkError, newOrderId } from '../api'
import { BackLink, Card } from '../components'
import { useResident } from '../ResidentContext'
import { L, errorCode, money } from './helpers'
import type { Bi } from './helpers'

interface Item {
  code: string
  name: Bi
  price_cents: number
  available: boolean
  block_reason: string | null
}
interface Catalog {
  allowed: boolean
  balance_cents: number
  weekly_limit_cents: number
  spent_this_week_cents: number
  items: Item[]
}

export function Commissary() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language
  const { request, refresh } = useResident()
  const [cat, setCat] = useState<Catalog | null>(null)
  const [cart, setCart] = useState<Record<string, number>>({})
  const [orderId, setOrderId] = useState(newOrderId)
  const [message, setMessage] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  const load = () =>
    request<Catalog>('/device/commissary')
      .then(setCat)
      .catch(() => setMessage({ kind: 'err', text: t('commissary.needsConnection') }))
  useEffect(() => {
    void load()
  }, [request])

  if (!cat)
    return (
      <div className="space-y-6">
        <BackLink />
        {message && <p>{message.text}</p>}
      </div>
    )
  const total = cat.items.reduce((sum, i) => sum + (cart[i.code] ?? 0) * i.price_cents, 0)
  const setQty = (code: string, n: number) =>
    setCart({ ...cart, [code]: Math.max(0, Math.min(20, n)) })

  async function place() {
    const lines = Object.fromEntries(Object.entries(cart).filter(([, q]) => q > 0))
    try {
      const r = await request<{ balance_cents: number }>('/device/commissary/orders', {
        method: 'POST',
        body: JSON.stringify({ client_id: orderId, lines }),
      })
      setMessage({
        kind: 'ok',
        text: t('commissary.placed', { amount: money(r.balance_cents, lang) }),
      })
      setCart({})
      setOrderId(newOrderId())
      void refresh()
      void load()
    } catch (e) {
      setMessage({
        kind: 'err',
        text:
          e instanceof NetworkError
            ? t('commissary.needsConnection')
            : t(`commissary.err.${errorCode(e)}`, { defaultValue: errorCode(e) }),
      })
    }
  }

  return (
    <div className="space-y-6">
      <BackLink />
      <h1 className="text-3xl font-bold">{t('commissary.title')}</h1>
      <p data-testid="balance">
        {t('commissary.balance', { amount: money(cat.balance_cents, lang) })}
      </p>
      <p data-testid="weekly">
        {t('commissary.weekly', {
          left: money(Math.max(0, cat.weekly_limit_cents - cat.spent_this_week_cents), lang),
          limit: money(cat.weekly_limit_cents, lang),
        })}
      </p>
      {!cat.allowed && (
        <p role="alert" data-testid="commissary-locked">
          {t('commissary.lockedTitle')}
        </p>
      )}
      {message && (
        <p role={message.kind === 'ok' ? 'status' : 'alert'} data-testid="order-message">
          {message.text}
        </p>
      )}
      <ul className="space-y-3">
        {cat.items.map((i) => (
          <li key={i.code}>
            <Card data-testid={`item-${i.code}`} data-available={i.available}>
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xl font-semibold">{L(i.name, lang)}</p>
                  <p>{money(i.price_cents, lang)}</p>
                  {i.block_reason && (
                    <p data-testid={`block-${i.code}`}>
                      {t(`commissary.blocked.${i.block_reason}`)}
                    </p>
                  )}
                </div>
                {i.available && (
                  <div className="flex items-center gap-2">
                    <button
                      aria-label={`${t('commissary.remove')} ${L(i.name, lang)}`}
                      onClick={() => setQty(i.code, (cart[i.code] ?? 0) - 1)}
                      className="h-14 w-14 rounded-lg border-2 border-white text-2xl"
                    >
                      −
                    </button>
                    <span data-testid={`qty-${i.code}`} className="w-8 text-center">
                      {cart[i.code] ?? 0}
                    </span>
                    <button
                      aria-label={`${t('commissary.add')} ${L(i.name, lang)}`}
                      onClick={() => setQty(i.code, (cart[i.code] ?? 0) + 1)}
                      className="h-14 w-14 rounded-lg border-2 border-white text-2xl"
                    >
                      +
                    </button>
                  </div>
                )}
              </div>
            </Card>
          </li>
        ))}
      </ul>
      <Card>
        <h2 className="text-2xl font-bold">{t('commissary.cart')}</h2>
        {total === 0 ? (
          <p>{t('commissary.empty')}</p>
        ) : (
          <p data-testid="cart-total">{t('commissary.total', { amount: money(total, lang) })}</p>
        )}
        <button
          disabled={total === 0 || !cat.allowed}
          onClick={() => void place()}
          className="mt-3 min-h-14 rounded-lg bg-blue-700 px-6 py-3 font-semibold disabled:opacity-40"
        >
          {t('commissary.place')}
        </button>
      </Card>
    </div>
  )
}
