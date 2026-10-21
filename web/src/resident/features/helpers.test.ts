import { L, clock, errorCode, money, remainingSeconds } from './helpers'

test('bilingual text picks the language and falls back to English', () => {
  expect(L({ en: 'Hello', es: 'Hola' }, 'es')).toBe('Hola')
  expect(L({ en: 'Hello', es: '' }, 'es')).toBe('Hello')
  expect(L({ en: 'Hello', es: 'Hola' }, 'en')).toBe('Hello')
  expect(L(undefined, 'en')).toBe('')
})

test('money is shown in dollars from cents', () => {
  expect(money(425, 'en')).toBe('$4.25')
  expect(money(2000, 'en')).toBe('$20.00')
})

test('call countdown never goes negative and rounds up', () => {
  const start = '2026-03-02T09:00:00Z'
  const t0 = Date.parse(start)
  expect(remainingSeconds(start, 900, t0)).toBe(900)
  expect(remainingSeconds(start, 900, t0 + 100_500)).toBe(800)
  expect(remainingSeconds(start, 900, t0 + 10_000_000)).toBe(0)
  expect(clock(800)).toBe('13:20')
  expect(clock(5)).toBe('0:05')
})

test('error codes are read from API error bodies', () => {
  expect(errorCode({ body: { detail: { code: 'WEEKLY_LIMIT' } } })).toBe('WEEKLY_LIMIT')
  expect(errorCode(new Error('x'))).toBe('ERROR')
})
