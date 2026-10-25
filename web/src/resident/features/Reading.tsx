import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { BackLink, Card, reasonTitle } from '../components'
import { NetworkError } from '../api'
import { useResident } from '../ResidentContext'
import {
  TEXT_SCALES,
  loadBook,
  loadCatalog,
  mergeProgress,
  offlineCatalog,
  readerAllowed,
  saveBook,
  saveCatalog,
  savedIds,
} from './readingCache'
import type { Book, CatalogItem } from './readingCache'

const SIZE_KEY = 'isd.reading.size'

function initialSize(): number {
  try {
    const n = Number(localStorage.getItem(SIZE_KEY))
    return Number.isInteger(n) && n >= 0 && n < TEXT_SCALES.length ? n : 0
  } catch {
    return 0
  }
}

type Shown = CatalogItem & { savedOffline?: boolean }

export function Reading() {
  const { t } = useTranslation()
  const { request, online, features } = useResident()
  const [items, setItems] = useState<CatalogItem[] | null>(loadCatalog())
  const [open, setOpen] = useState<{ book: Book; feature: string } | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const load = useCallback(() => {
    request<CatalogItem[]>('/device/reading')
      .then((list) => {
        saveCatalog(list)
        setItems(list)
      })
      .catch(() => {}) // offline: keep showing the saved list
  }, [request])
  useEffect(load, [load, online])

  async function read(item: CatalogItem) {
    setNotice(null)
    const local = loadBook(item.id)
    try {
      const fresh = await request<Book>(`/device/reading/${item.id}`)
      const book = mergeProgress(local, fresh)
      saveBook(book)
      setOpen({ book, feature: item.feature })
    } catch (e) {
      if (!(e instanceof NetworkError)) {
        setNotice(t('reading.cannotOpen'))
        return
      }
      if (local) setOpen({ book: local, feature: item.feature })
      else setNotice(t('reading.notSaved'))
    }
  }

  if (open)
    return (
      <Reader
        book={open.book}
        feature={open.feature}
        onClose={() => {
          setOpen(null)
          load()
        }}
      />
    )

  const shown: Shown[] =
    items === null ? [] : online ? items : offlineCatalog(items, savedIds(), features)

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6">
      <BackLink />
      <h1 className="text-h1 font-bold">{t('reading.title')}</h1>
      {!online && <p data-testid="reading-offline">{t('reading.offline')}</p>}
      {notice && <p role="alert">{notice}</p>}
      {items === null && online === false && <p>{t('reading.notSaved')}</p>}
      {items?.length === 0 && <p>{t('reading.none')}</p>}
      <ul className="space-y-3">
        {shown.map((i) => (
          <li key={i.id}>
            <Card data-testid={`reading-${i.id}`} data-allowed={i.allowed}>
              <p className="text-label font-bold">{i.title}</p>
              <p className="text-ink-soft">{t('reading.by', { author: i.author })}</p>
              <p className="text-ink-soft" data-testid={`reading-progress-${i.id}`}>
                {i.completed
                  ? t('reading.finishedShort')
                  : t('reading.progress', { page: i.page + 1, total: i.pages })}
                {i.bookmarks > 0 && ` · ${t('reading.bookmarkCount', { count: i.bookmarks })}`}
              </p>
              {i.allowed ? (
                <button
                  onClick={() => void read(i)}
                  className="mt-2 min-h-touch rounded-ctl bg-primary px-6 py-3 text-label font-bold text-primary-ink hover:brightness-110"
                >
                  {i.page > 0 && !i.completed ? t('reading.continue') : t('reading.read')}
                </button>
              ) : (
                <p data-testid="reading-locked" className="mt-2">
                  🔒{' '}
                  {i.reasons[0]
                    ? reasonTitle(t, i.reasons[0])
                    : !online && i.savedOffline === false
                      ? t('reading.notSaved')
                      : t('reading.lockedHint')}
                </p>
              )}
            </Card>
          </li>
        ))}
      </ul>
    </div>
  )
}

function Reader({
  book: initial,
  feature,
  onClose,
}: {
  book: Book
  feature: string
  onClose: () => void
}) {
  const { t } = useTranslation()
  const { submit, features } = useResident()
  const [book, setBook] = useState(initial)
  const [page, setPage] = useState(initial.page)
  const [size, setSize] = useState(initialSize)
  const sent = useRef<Promise<unknown>>(Promise.resolve())
  const last = book.pages.length - 1
  const marked = book.bookmarks.includes(page)
  const allowed = readerAllowed(feature, features)
  const lock = features[feature]?.reasons[0]

  async function close() {
    await sent.current
    onClose()
  }

  function keep(next: Book) {
    setBook(next)
    saveBook(next)
  }

  // Events go out in order, and closing the reader waits for them so the list shows the result.
  function send(ev: Parameters<typeof submit>[0]) {
    sent.current = sent.current.then(() => submit(ev)).catch(() => {})
  }

  function go(to: number) {
    const target = Math.max(0, Math.min(to, last))
    setPage(target)
    if (target > book.page || (target === last && !book.completed))
      keep({
        ...book,
        page: Math.max(book.page, target),
        completed: book.completed || target === last,
      })
    send({ type: 'reading_progress', payload: { item_id: book.id, page: target } })
  }

  // Being on the last page counts as reaching it, even for a one-page text.
  useEffect(() => {
    if (initial.page === last && !initial.completed) go(initial.page)
  }, [])

  function toggleBookmark() {
    const on = !marked
    const bookmarks = on
      ? [...book.bookmarks, page].sort((a, b) => a - b)
      : book.bookmarks.filter((p) => p !== page)
    keep({ ...book, bookmarks })
    send({ type: 'reading_bookmark', payload: { item_id: book.id, page, on } })
  }

  function resize(delta: number) {
    const next = Math.max(0, Math.min(size + delta, TEXT_SCALES.length - 1))
    setSize(next)
    try {
      localStorage.setItem(SIZE_KEY, String(next))
    } catch {
      // not remembered; still applies now
    }
  }

  const button =
    'min-h-touch rounded-ctl border-2 border-ink bg-surface px-6 py-3 text-label font-bold text-ink hover:bg-surface-2 disabled:opacity-40'

  if (!allowed)
    return (
      <div className="mx-auto w-full max-w-5xl space-y-6">
        <button onClick={close} className={button}>
          ← {t('reading.back')}
        </button>
        <p data-testid="reading-locked">
          🔒 {lock ? reasonTitle(t, lock) : t('reading.lockedHint')}
        </p>
      </div>
    )

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <button onClick={close} className={button}>
          ← {t('reading.back')}
        </button>
        <button
          onClick={() => resize(-1)}
          disabled={size === 0}
          aria-label={t('reading.textSmaller')}
          className={button}
        >
          A−
        </button>
        <button
          onClick={() => resize(1)}
          disabled={size === TEXT_SCALES.length - 1}
          aria-label={t('reading.textLarger')}
          className={button}
        >
          A+
        </button>
      </div>
      <article data-testid="reading-text" className="space-y-3">
        <h1 className="text-h1 font-bold">{book.title}</h1>
        <p className="text-ink-soft">{t('reading.by', { author: book.author })}</p>
        <p
          data-testid="reading-page-text"
          data-scale={TEXT_SCALES[size]}
          className="leading-relaxed"
          style={{ fontSize: `${TEXT_SCALES[size]}em` }}
        >
          {book.pages[page]}
        </p>
      </article>
      <p data-testid="reading-position" className="text-ink-soft">
        {t('reading.position', { page: page + 1, total: book.pages.length })}
      </p>
      {page === last && <p data-testid="reading-finished">{t('reading.finished')}</p>}
      <div className="flex flex-wrap gap-3">
        <button onClick={() => go(page - 1)} disabled={page === 0} className={button}>
          {t('reading.prev')}
        </button>
        <button onClick={() => go(page + 1)} disabled={page === last} className={button}>
          {t('reading.next')}
        </button>
        <button onClick={toggleBookmark} aria-pressed={marked} className={button}>
          {marked ? t('reading.removeBookmark') : t('reading.addBookmark')}
        </button>
      </div>
      {book.bookmarks.length > 0 && (
        <div>
          <h2 className="text-label font-bold">{t('reading.bookmarks')}</h2>
          <ul className="mt-2 flex flex-wrap gap-2">
            {book.bookmarks.map((p) => (
              <li key={p}>
                <button onClick={() => go(p)} className={button}>
                  {t('reading.pageN', { page: p + 1 })}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
