import { ShoppingBasket } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '../../ui/Button'
import { Notice } from '../../ui/Notice'
import { ErrorState, LoadingState } from '../../ui/States'
import { NetworkError, newOrderId } from '../api'
import { Card, ScreenFrame } from '../components'
import { Stepper } from '../parts'
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
      <ScreenFrame title={t('commissary.title')}>
        {message ? (
          <ErrorState title={message.text} onRetry={() => void load()} />
        ) : (
          <LoadingState />
        )}
      </ScreenFrame>
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
    <ScreenFrame title={t('commissary.title')}>
      {!cat.allowed && (
        <Notice tone="notice" role="alert" data-testid="commissary-locked">
          {t('commissary.lockedTitle')}
        </Notice>
      )}
      {message && (
        <Notice
          tone={message.kind === 'ok' ? 'ok' : 'danger'}
          role={message.kind === 'ok' ? 'status' : 'alert'}
          data-testid="order-message"
        >
          {message.text}
        </Notice>
      )}
      <div className="grid gap-6 min-[1180px]:grid-cols-[1fr_22rem] min-[1180px]:items-start">
        <ul className="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(20rem,1fr))]">
          {cat.items.map((i) => (
            <li key={i.code}>
              <Card
                data-testid={`item-${i.code}`}
                data-available={i.available}
                className="flex h-full flex-col gap-3"
              >
                <div>
                  <p className="text-label font-bold">{L(i.name, lang)}</p>
                  <p className="text-body text-ink-soft">{money(i.price_cents, lang)}</p>
                  {i.block_reason && (
                    <p className="mt-1 font-bold text-lock" data-testid={`block-${i.code}`}>
                      {t(`commissary.blocked.${i.block_reason}`)}
                    </p>
                  )}
                </div>
                {i.available && (
                  <div className="mt-auto">
                    <Stepper
                      value={cart[i.code] ?? 0}
                      onChange={(n) => setQty(i.code, n)}
                      decLabel={`${t('commissary.remove')} ${L(i.name, lang)}`}
                      incLabel={`${t('commissary.add')} ${L(i.name, lang)}`}
                      testId={`qty-${i.code}`}
                    />
                  </div>
                )}
              </Card>
            </li>
          ))}
        </ul>
        <Card className="space-y-4 min-[1180px]:sticky min-[1180px]:top-6">
          <p data-testid="balance" className="text-label font-bold">
            {t('commissary.balance', { amount: money(cat.balance_cents, lang) })}
          </p>
          {cat.balance_cents === 0 && (
            <p className="text-sm text-ink-soft">{t('commissary.noFunds')}</p>
          )}
          <p data-testid="weekly">
            {t('commissary.weekly', {
              left: money(Math.max(0, cat.weekly_limit_cents - cat.spent_this_week_cents), lang),
              limit: money(cat.weekly_limit_cents, lang),
            })}
          </p>
          <hr className="border-line" />
          <h2 className="text-h3 font-bold">{t('commissary.cart')}</h2>
          {total === 0 ? (
            <p className="text-ink-soft">{t('commissary.empty')}</p>
          ) : (
            <p data-testid="cart-total" className="text-label font-bold">
              {t('commissary.total', { amount: money(total, lang) })}
            </p>
          )}
          <Button
            variant="primary"
            icon={ShoppingBasket}
            disabled={total === 0 || !cat.allowed}
            onClick={() => void place()}
            className="w-full"
          >
            {t('commissary.place')}
          </Button>
        </Card>
      </div>
    </ScreenFrame>
  )
}
