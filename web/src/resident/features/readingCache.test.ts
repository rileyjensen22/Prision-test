import { beforeEach, describe, expect, it } from 'vitest'

import {
  MAX_SAVED_BOOKS,
  loadBook,
  mergeProgress,
  offlineCatalog,
  readerAllowed,
  saveBook,
  savedIds,
} from './readingCache'
import type { Book, CatalogItem } from './readingCache'
import { makeView } from '../fixtures'
import { effectiveFeatures } from '../snapshot'

function memory() {
  const m = new Map<string, string>()
  return {
    getItem: (k: string) => m.get(k) ?? null,
    setItem: (k: string, v: string) => void m.set(k, v),
    removeItem: (k: string) => void m.delete(k),
    size: () => m.size,
  }
}

const book = (id: string, page = 0): Book => ({
  id,
  title: id,
  author: 'A',
  language: 'en',
  pages: ['one', 'two', 'three'],
  page,
  completed: false,
  bookmarks: [],
})

const item = (id: string, feature: string): CatalogItem => ({
  id,
  title: id,
  author: 'A',
  catalog: 'general',
  feature,
  language: 'en',
  pages: 3,
  page: 0,
  completed: false,
  bookmarks: 0,
  allowed: true,
  reasons: [],
})

describe('saved books', () => {
  let store: ReturnType<typeof memory>
  beforeEach(() => {
    store = memory()
  })

  it('round-trips a book and lists it as saved', () => {
    saveBook(book('a', 2), store)
    expect(loadBook('a', store)?.page).toBe(2)
    expect(savedIds(store)).toEqual(['a'])
  })

  it('keeps only the most recently opened books', () => {
    for (let i = 0; i < MAX_SAVED_BOOKS + 3; i++) saveBook(book(`b${i}`), store)
    expect(savedIds(store)).toHaveLength(MAX_SAVED_BOOKS)
    expect(loadBook('b0', store)).toBeNull()
    expect(loadBook(`b${MAX_SAVED_BOOKS + 2}`, store)).not.toBeNull()
  })

  it('re-opening a book moves it to the front instead of duplicating it', () => {
    saveBook(book('a'), store)
    saveBook(book('b'), store)
    saveBook(book('a', 1), store)
    expect(savedIds(store)).toEqual(['a', 'b'])
  })

  it('survives storage that throws', () => {
    const broken = {
      getItem: () => {
        throw new Error('blocked')
      },
      setItem: () => {
        throw new Error('blocked')
      },
      removeItem: () => {
        throw new Error('blocked')
      },
    }
    expect(() => saveBook(book('a'), broken)).not.toThrow()
    expect(loadBook('a', broken)).toBeNull()
  })
})

describe('progress merge', () => {
  it('never moves backward when the server is behind queued offline progress', () => {
    expect(mergeProgress(book('a', 2), book('a', 0)).page).toBe(2)
    expect(mergeProgress(book('a', 0), book('a', 2)).page).toBe(2)
    expect(mergeProgress(null, book('a', 1)).page).toBe(1)
  })
})

describe('offline gating', () => {
  const allowed = { allowed: true, baseline: false, limits: {}, reasons: [] }
  const locked = { allowed: false, baseline: false, limits: {}, reasons: [] }

  it('fails closed when the feature is missing or locked', () => {
    expect(readerAllowed('reading_general', {})).toBe(false)
    expect(readerAllowed('reading_general', { reading_general: locked })).toBe(false)
    expect(readerAllowed('reading_general', { reading_general: allowed })).toBe(true)
  })

  it('only offers saved texts that are still allowed', () => {
    const items = [
      item('a', 'reading_general'),
      item('b', 'reading_general'),
      item('c', 'legal_materials'),
    ]
    const out = offlineCatalog(items, ['a', 'c'], {
      reading_general: locked,
      legal_materials: allowed,
    })
    expect(out.map((i) => [i.id, i.allowed])).toEqual([
      ['a', false], // saved, but a lock arrived first
      ['b', false], // never saved
      ['c', true], // baseline text, saved, open
    ])
  })

  it('an expired snapshot closes general reading but not the legal and religious texts', () => {
    const base = { allowed: true, baseline: false, limits: {}, reasons: [] }
    const view = makeView({
      features: {
        reading_general: base,
        legal_materials: { ...base, baseline: true },
        religious_texts: { ...base, baseline: true },
      },
    })
    const later = Date.parse(view.valid_until) + 60_000
    const stale = effectiveFeatures(view, later)
    expect(readerAllowed('reading_general', stale)).toBe(false)
    expect(readerAllowed('legal_materials', stale)).toBe(true)
    expect(readerAllowed('religious_texts', stale)).toBe(true)
  })
})
