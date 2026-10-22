/**
 * Camera-cover detection. It runs on the device, during an active call only, and works on two
 * numbers per sample (average brightness and how much the picture varies). The pixels are read,
 * reduced to those numbers and dropped; no frame is stored or sent (invariant 14). Only a short
 * signal ("dark" or "flat") and how long it lasted goes to the server.
 */

export interface FrameStats {
  mean: number // average brightness, 0 to 255
  variance: number // how much brightness varies across the picture
}
export type TamperSignal = 'dark' | 'flat'

export const SAMPLE_MS = 500
export const COVERED_SAMPLES = 6 // three seconds in a row
export const DARK_MEAN = 20
export const DARK_VARIANCE = 12
export const FLAT_VARIANCE = 3

/** Brightness statistics from RGBA pixels. The array is only read, never kept. */
export function frameStats(rgba: Uint8ClampedArray): FrameStats {
  const n = Math.floor(rgba.length / 4)
  if (n === 0) return { mean: 0, variance: 0 }
  let sum = 0
  let sumSq = 0
  for (let i = 0; i < n; i++) {
    const y = 0.299 * rgba[i * 4] + 0.587 * rgba[i * 4 + 1] + 0.114 * rgba[i * 4 + 2]
    sum += y
    sumSq += y * y
  }
  const mean = sum / n
  return { mean, variance: Math.max(0, sumSq / n - mean * mean) }
}

export function classify(s: FrameStats): TamperSignal | null {
  if (s.variance < FLAT_VARIANCE) return 'flat'
  if (s.mean < DARK_MEAN && s.variance < DARK_VARIANCE) return 'dark'
  return null
}

export interface Verdict {
  covered: boolean
  signal: TamperSignal | null
  coveredMs: number
}

/** Fires once the same signal has held for COVERED_SAMPLES samples in a row. */
export class TamperDetector {
  private run = 0
  private signal: TamperSignal | null = null
  private fired = false

  push(s: FrameStats): Verdict {
    const now = classify(s)
    if (now === null || now !== this.signal) {
      this.run = now === null ? 0 : 1
      this.signal = now
    } else {
      this.run += 1
    }
    const covered = !this.fired && this.signal !== null && this.run >= COVERED_SAMPLES
    if (covered) this.fired = true
    return { covered, signal: this.signal, coveredMs: this.run * SAMPLE_MS }
  }
}

/** Reads a small copy of the current video picture and returns only its statistics. */
export function sampleVideo(video: HTMLVideoElement, canvas: HTMLCanvasElement): FrameStats | null {
  if (video.readyState < 2 || video.videoWidth === 0) return null
  canvas.width = 32
  canvas.height = 24
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  if (!ctx) return null
  ctx.drawImage(video, 0, 0, 32, 24)
  return frameStats(ctx.getImageData(0, 0, 32, 24).data)
}
