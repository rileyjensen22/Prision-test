import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { BackLink, Card, reasonTitle } from '../components'
import { useResident } from '../ResidentContext'

interface Item {
  id: string
  title: string
  author: string
  catalog: 'general' | 'expanded'
  allowed: boolean
  reasons: { code: string; params: Record<string, string | number> }[]
}
interface Text {
  id: string
  title: string
  author: string
  text: string
}

export function Reading() {
  const { t } = useTranslation()
  const { request } = useResident()
  const [items, setItems] = useState<Item[] | null>(null)
  const [open, setOpen] = useState<Text | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    request<Item[]>('/device/reading')
      .then(setItems)
      .catch(() => setError(true))
  }, [request])

  async function read(id: string) {
    setOpen(await request<Text>(`/device/reading/${id}`))
  }

  if (open)
    return (
      <div className="space-y-6">
        <button
          onClick={() => setOpen(null)}
          className="rounded-lg border-2 border-white px-6 py-4"
        >
          ← {t('reading.back')}
        </button>
        <article data-testid="reading-text" className="space-y-3">
          <h1 className="text-3xl font-bold">{open.title}</h1>
          <p className="opacity-80">{t('reading.by', { author: open.author })}</p>
          <p className="leading-relaxed">{open.text}</p>
        </article>
      </div>
    )

  return (
    <div className="space-y-6">
      <BackLink />
      <h1 className="text-3xl font-bold">{t('reading.title')}</h1>
      {error && <p>{t('calls.needsConnection')}</p>}
      {items?.length === 0 && <p>{t('reading.none')}</p>}
      <ul className="space-y-3">
        {(items ?? []).map((i) => (
          <li key={i.id}>
            <Card data-testid={`reading-${i.id}`} data-allowed={i.allowed}>
              <p className="text-xl font-semibold">{i.title}</p>
              <p className="opacity-80">{t('reading.by', { author: i.author })}</p>
              {i.allowed ? (
                <button
                  onClick={() => void read(i.id)}
                  className="mt-2 min-h-14 rounded-lg bg-blue-700 px-6 py-3 font-semibold"
                >
                  {t('reading.read')}
                </button>
              ) : (
                <p data-testid="reading-locked" className="mt-2">
                  🔒 {i.reasons[0] ? reasonTitle(t, i.reasons[0]) : t('reading.lockedHint')}
                </p>
              )}
            </Card>
          </li>
        ))}
      </ul>
    </div>
  )
}
