import { isNight } from './nightMode'

const at = (h: number, m = 0) => new Date(2026, 0, 5, h, m)

describe('isNight', () => {
  it('wraps past midnight with the default window', () => {
    expect(isNight(at(20, 59))).toBe(false)
    expect(isNight(at(21))).toBe(true)
    expect(isNight(at(3))).toBe(true)
    expect(isNight(at(5, 59))).toBe(true)
    expect(isNight(at(6))).toBe(false)
    expect(isNight(at(12))).toBe(false)
  })
  it('handles a same-day window and an empty one', () => {
    expect(isNight(at(14), { start: '13:00', end: '15:00' })).toBe(true)
    expect(isNight(at(16), { start: '13:00', end: '15:00' })).toBe(false)
    expect(isNight(at(2), { start: '08:00', end: '08:00' })).toBe(false)
  })
})
