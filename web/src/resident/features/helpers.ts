/** Bilingual content from the API: {en, es}. Falls back to English. */
export type Bi = { en: string; es: string }

export const L = (text: Bi | undefined, lang: string): string =>
  text ? (lang === 'es' ? text.es : text.en) || text.en : ''

export const money = (cents: number, lang: string): string =>
  new Intl.NumberFormat(lang, { style: 'currency', currency: 'USD' }).format(cents / 100)

export const remainingSeconds = (startedAtIso: string, maxSeconds: number, nowMs: number): number =>
  Math.max(0, Math.ceil(maxSeconds - (nowMs - Date.parse(startedAtIso)) / 1000))

export const clock = (seconds: number): string => {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

export const errorCode = (e: unknown): string => {
  const body = (e as { body?: { detail?: { code?: string } } })?.body
  return body?.detail?.code ?? 'ERROR'
}
