import type { Feature, ResidentView } from './types'

/**
 * Offline enforcement. A cached ResidentView is only trusted until `valid_until`
 * (the next sanction boundary, or the snapshot TTL). After that we fail closed:
 * only baseline features stay available until the device can refresh.
 */
export function isStale(view: ResidentView, nowMs: number): boolean {
  return nowMs > Date.parse(view.valid_until)
}

export function effectiveFeatures(view: ResidentView, nowMs: number): Record<string, Feature> {
  if (!isStale(view, nowMs)) return view.features
  const out: Record<string, Feature> = {}
  for (const [name, f] of Object.entries(view.features)) {
    out[name] = f.baseline
      ? f
      : {
          ...f,
          allowed: false,
          limits: {},
          reasons: [
            {
              code: 'OFFLINE_STALE',
              source: 'offline',
              how_to_appeal: 'request_staff',
              ends_at: null,
              detail: '',
              params: {},
              sanction_id: null,
            },
            ...f.reasons,
          ],
        }
  }
  return out
}
