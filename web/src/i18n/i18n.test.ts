import en from './en'
import es from './es'

function keys(o: object, prefix = ''): string[] {
  return Object.entries(o).flatMap(([k, v]) =>
    typeof v === 'object' ? keys(v, `${prefix}${k}.`) : [`${prefix}${k}`],
  )
}

test('English and Spanish have identical keys', () => {
  expect(keys(es).sort()).toEqual(keys(en).sort())
})

test('every infraction code and feature the API can return has a translation', () => {
  for (const code of [
    'DISRUPT',
    'CELL_MESS',
    'STAFF_DISRESPECT',
    'CAM_BLOCK',
    'DEVICE_TAMPER',
    'DEVICE_DAMAGE',
    'OFFENSE_RESTRICTION',
    'TIER_LOCKED',
    'TIER_CEILING',
    'OFFLINE_STALE',
  ])
    expect(en.code).toHaveProperty(code)
  for (const f of [
    'calls',
    'texting',
    'video',
    'commissary',
    'chess_engine',
    'chess_human',
    'reading_general',
    'reading_expanded',
    'advanced_education',
    'outdoor_rec',
    'legal_materials',
    'grievances_appeals',
    'medical_requests',
    'mental_health_requests',
    'request_staff',
    'emergency_contact',
    'religious_texts',
    'basic_education',
    'attorney_calls',
    'out_of_cell_minimum',
  ])
    expect(en.feature).toHaveProperty(f)
})

test('every error code the feature APIs can return is translated', () => {
  for (const c of [
    'FEATURE_LOCKED',
    'LIMIT_REACHED',
    'CONTACT_UNAVAILABLE',
    'CALL_IN_PROGRESS',
    'NOT_FOUND',
  ])
    expect(en.calls.err).toHaveProperty(c)
  for (const c of [
    'FEATURE_LOCKED',
    'INSUFFICIENT_FUNDS',
    'WEEKLY_LIMIT',
    'ITEM_TIER',
    'ITEM_OFFENSE',
    'BAD_QUANTITY',
    'EMPTY_ORDER',
    'UNKNOWN_ITEM',
  ])
    expect(en.commissary.err).toHaveProperty(c)
  for (const c of ['ITEM_TIER', 'ITEM_OFFENSE']) expect(en.commissary.blocked).toHaveProperty(c)
})
