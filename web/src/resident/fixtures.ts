import type { Feature, ResidentView } from './types'

const baseline = (): Feature => ({ allowed: true, baseline: true, limits: {}, reasons: [] })
const open = (limits = {}): Feature => ({ allowed: true, baseline: false, limits, reasons: [] })

export function makeView(over: Partial<ResidentView> = {}): ResidentView {
  const generated = new Date()
  return {
    resident_code: 'R-1',
    settings: { language: 'en', text_size: 'normal', reading_level: 'standard', captions: false },
    tier: {
      earned: 3,
      ceiling: 10,
      effective: 3,
      points: 400,
      next_tier: 4,
      points_to_next: 50,
      capped_by_ceiling: false,
      max_tier_override: null,
    },
    features: {
      calls: {
        allowed: false,
        baseline: false,
        limits: {},
        reasons: [
          {
            code: 'DISRUPT',
            source: 'sanction',
            how_to_appeal: 'appeal',
            ends_at: '2026-03-03T08:00:00Z',
            detail: '',
            params: {},
            sanction_id: 7,
          },
        ],
      },
      commissary: open({ dollars_per_week: 40 }),
      legal_materials: baseline(),
      attorney_calls: baseline(),
    },
    allowances: [{ feature: 'commissary', period: 'week', unit: 'dollars', limit: 40, used: 0 }],
    locks: [
      {
        key: 'sanction:7:',
        code: 'DISRUPT',
        source: 'sanction',
        features: ['calls'],
        ends_at: '2026-03-03T08:00:00Z',
        detail: '',
        params: {},
        how_to_appeal: 'appeal',
        sanction_id: 7,
        appeal_open: false,
      },
    ],
    generated_at: generated.toISOString(),
    valid_until: new Date(generated.getTime() + 60 * 60 * 1000).toISOString(),
    simulation: false,
    ui: { inactivity_return_home_seconds: 90 },
    ...over,
  }
}
