import { describe, expect, it } from 'vitest'

import { COVERED_SAMPLES, SAMPLE_MS, TamperDetector, classify, frameStats } from './tamper'

const pixels = (rgb: [number, number, number][]): Uint8ClampedArray =>
  Uint8ClampedArray.from(rgb.flatMap(([r, g, b]) => [r, g, b, 255]))

describe('frameStats', () => {
  it('is zero for an empty picture and exact for a flat one', () => {
    expect(frameStats(new Uint8ClampedArray())).toEqual({ mean: 0, variance: 0 })
    const grey = frameStats(pixels(Array(50).fill([100, 100, 100])))
    expect(grey.mean).toBeCloseTo(100, 5)
    expect(grey.variance).toBeCloseTo(0, 5)
  })

  it('sees variation when there is a bright and a dark half', () => {
    const s = frameStats(pixels([...Array(25).fill([0, 0, 0]), ...Array(25).fill([255, 255, 255])]))
    expect(s.mean).toBeCloseTo(127.5, 1)
    expect(s.variance).toBeGreaterThan(10_000)
  })
})

describe('classify', () => {
  it('a normal lit room is fine, a black or blank picture is not', () => {
    expect(classify({ mean: 110, variance: 900 })).toBeNull()
    expect(classify({ mean: 6, variance: 2 })).toBe('flat') // a finger over the lens
    expect(classify({ mean: 12, variance: 8 })).toBe('dark') // a dark cloth, a little noise
    expect(classify({ mean: 90, variance: 1 })).toBe('flat') // a blank card held up
    expect(classify({ mean: 15, variance: 400 })).toBeNull() // a dim room with real detail
  })
})

describe('TamperDetector', () => {
  const covered = { mean: 5, variance: 1 }
  const fine = { mean: 120, variance: 800 }

  it('needs the picture to stay covered for several samples in a row', () => {
    const d = new TamperDetector()
    for (let i = 0; i < COVERED_SAMPLES - 1; i++) expect(d.push(covered).covered).toBe(false)
    const v = d.push(covered)
    expect(v).toEqual({ covered: true, signal: 'flat', coveredMs: COVERED_SAMPLES * SAMPLE_MS })
  })

  it('a blink or a passing hand resets it', () => {
    const d = new TamperDetector()
    for (let i = 0; i < COVERED_SAMPLES - 1; i++) d.push(covered)
    d.push(fine)
    for (let i = 0; i < COVERED_SAMPLES - 1; i++) expect(d.push(covered).covered).toBe(false)
  })

  it('reports once and then stays quiet', () => {
    const d = new TamperDetector()
    const fired = Array.from({ length: COVERED_SAMPLES + 5 }, () => d.push(covered).covered)
    expect(fired.filter(Boolean)).toHaveLength(1)
  })

  it('switching between dark and flat restarts the count', () => {
    const d = new TamperDetector()
    for (let i = 0; i < COVERED_SAMPLES - 1; i++) d.push(covered)
    expect(d.push({ mean: 12, variance: 8 }).covered).toBe(false)
  })
})
