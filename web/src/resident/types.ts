export interface Reason {
  code: string
  source: string
  how_to_appeal: 'appeal' | 'request_staff'
  ends_at: string | null
  detail: string
  params: Record<string, string | number>
  sanction_id: number | null
}

export interface Feature {
  allowed: boolean
  baseline: boolean
  limits: Record<string, number>
  reasons: Reason[]
}

export interface Lock {
  key: string
  code: string
  source: string
  features: string[]
  ends_at: string | null
  detail: string
  params: Record<string, string | number>
  how_to_appeal: 'appeal' | 'request_staff'
  sanction_id: number | null
  appeal_open: boolean
}

export interface Tier {
  earned: number
  ceiling: number
  effective: number
  points: number
  next_tier: number | null
  points_to_next: number | null
  capped_by_ceiling: boolean
}

export interface Allowance {
  feature: string
  period: 'day' | 'week'
  unit: string
  limit: number
  used: number
}

export interface ResidentView {
  resident_code: string
  settings: {
    language: 'en' | 'es'
    text_size: 'normal' | 'large' | 'xlarge'
    reading_level: string
    captions: boolean
  }
  tier: Tier
  features: Record<string, Feature>
  allowances: Allowance[]
  locks: Lock[]
  generated_at: string
  valid_until: string
  simulation: boolean
  ui: {
    inactivity_return_home_seconds: number
    /** Optional night-mode window; the kiosk falls back to 21:00 to 06:00 until the API sends it. */
    night_mode?: { start: string; end: string }
  }
  reentry?: { release_date: string; days_left: number; weeks_left: number } | null
}
