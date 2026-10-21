import { makeView } from './fixtures'
import { effectiveFeatures, isStale } from './snapshot'

const view = makeView()
const valid = Date.parse(view.valid_until)

test('fresh snapshot is used as-is, locks included', () => {
  expect(isStale(view, valid - 1)).toBe(false)
  const f = effectiveFeatures(view, valid - 1)
  expect(f.calls.allowed).toBe(false)
  expect(f.commissary.allowed).toBe(true)
})

test('expired snapshot fails closed: only baseline stays available', () => {
  expect(isStale(view, valid + 1)).toBe(true)
  const f = effectiveFeatures(view, valid + 1)
  expect(f.commissary.allowed).toBe(false)
  expect(f.commissary.reasons[0].code).toBe('OFFLINE_STALE')
  expect(f.calls.reasons.map((r) => r.code)).toEqual(['OFFLINE_STALE', 'DISRUPT'])
  expect(f.legal_materials.allowed).toBe(true)
  expect(f.attorney_calls.allowed).toBe(true)
})
