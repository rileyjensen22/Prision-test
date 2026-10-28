/** The reentry page saved on the device, so it still opens offline. Information only. */
type Store = Pick<Storage, 'getItem' | 'setItem'>

const KEY = 'isd.reentry'

export interface Saved<T> {
  data: T
  saved_at: string
}

export function saveReentry<T>(data: T, now: Date = new Date(), store: Store = localStorage) {
  try {
    store.setItem(KEY, JSON.stringify({ data, saved_at: now.toISOString() }))
  } catch {
    // storage full or blocked: the page still works online
  }
}

export function loadReentry<T>(store: Store = localStorage): Saved<T> | null {
  try {
    const raw = store.getItem(KEY)
    return raw ? (JSON.parse(raw) as Saved<T>) : null
  } catch {
    return null
  }
}

/** Days and weeks to the release date, counted from the device clock so a saved page stays right. */
export function countdownFrom(releaseDate: string, now: Date = new Date()) {
  const release = new Date(`${releaseDate}T00:00:00`)
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const days = Math.max(0, Math.round((release.getTime() - start.getTime()) / 86_400_000))
  return { release_date: releaseDate, days_left: days, weeks_left: Math.floor(days / 7) }
}
