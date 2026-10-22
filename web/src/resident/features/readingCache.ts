/** Books saved on the device so reading works offline. Entitlements are still checked offline. */
import type { Feature } from '../types'

export interface CatalogItem {
  id: string
  title: string
  author: string
  catalog: 'general' | 'expanded' | 'legal' | 'religious'
  feature: string
  language: string
  pages: number
  page: number
  completed: boolean
  bookmarks: number
  allowed: boolean
  reasons: { code: string; params: Record<string, string | number> }[]
}

export interface Book {
  id: string
  title: string
  author: string
  language: string
  pages: string[]
  page: number
  completed: boolean
  bookmarks: number[]
}

type Store = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

const CATALOG_KEY = 'isd.reading.catalog'
const INDEX_KEY = 'isd.reading.index'
const BOOK_PREFIX = 'isd.reading.book.'
export const MAX_SAVED_BOOKS = 20

function read<T>(store: Store, key: string, fallback: T): T {
  try {
    const raw = store.getItem(key)
    return raw === null ? fallback : (JSON.parse(raw) as T)
  } catch {
    return fallback
  }
}

function write(store: Store, key: string, value: unknown) {
  try {
    store.setItem(key, JSON.stringify(value))
  } catch {
    // storage full or blocked: reading still works online
  }
}

export const loadCatalog = (store: Store = localStorage): CatalogItem[] | null =>
  read<CatalogItem[] | null>(store, CATALOG_KEY, null)

export const saveCatalog = (items: CatalogItem[], store: Store = localStorage) =>
  write(store, CATALOG_KEY, items)

export const loadBook = (id: string, store: Store = localStorage): Book | null =>
  read<Book | null>(store, BOOK_PREFIX + id, null)

export const savedIds = (store: Store = localStorage): string[] =>
  read<string[]>(store, INDEX_KEY, [])

/** Saves a book, keeping the most recently opened ones. Returns the ids that were dropped. */
export function saveBook(book: Book, store: Store = localStorage): string[] {
  const ids = [book.id, ...savedIds(store).filter((i) => i !== book.id)]
  const dropped = ids.slice(MAX_SAVED_BOOKS)
  for (const id of dropped) {
    try {
      store.removeItem(BOOK_PREFIX + id)
    } catch {
      // ignore
    }
  }
  write(store, BOOK_PREFIX + book.id, book)
  write(store, INDEX_KEY, ids.slice(0, MAX_SAVED_BOOKS))
  return dropped
}

/** Progress only moves forward; bookmarks come from whichever side is given last. */
export function mergeProgress(local: Book | null, server: Book): Book {
  if (!local) return server
  const page = Math.max(local.page, server.page)
  return { ...server, page, completed: server.completed || local.completed }
}

/**
 * Whether a text may be opened right now. Uses the (fail-closed) entitlement snapshot, so a lock
 * that arrived before the device went offline still applies, and an expired snapshot locks.
 */
export function readerAllowed(feature: string, features: Record<string, Feature>): boolean {
  return features[feature]?.allowed === true
}

/** The list shown while offline: only saved texts can be opened, and only if still allowed. */
export function offlineCatalog(
  items: CatalogItem[],
  saved: string[],
  features: Record<string, Feature>,
): (CatalogItem & { savedOffline: boolean })[] {
  return items.map((i) => {
    const savedOffline = saved.includes(i.id)
    return { ...i, savedOffline, allowed: savedOffline && readerAllowed(i.feature, features) }
  })
}

export const TEXT_SCALES = [1, 1.25, 1.5, 2] as const
