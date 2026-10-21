import { beforeEach, expect, test } from 'vitest'

import { resolveDeviceToken } from './api'

beforeEach(() => {
  localStorage.clear()
  window.history.replaceState(null, '', '/resident')
})

test('the device token comes from the URL fragment, is saved, and is removed from the address', () => {
  window.history.replaceState(null, '', '/resident/tier#device=tok-123')
  expect(resolveDeviceToken()).toBe('tok-123')
  expect(localStorage.getItem('isd.deviceToken')).toBe('tok-123')
  expect(window.location.hash).toBe('')
  expect(window.location.pathname).toBe('/resident/tier')
  expect(resolveDeviceToken()).toBe('tok-123') // later loads use the saved one
})

test('a token in the query string is ignored and removed (it would be written to server logs)', () => {
  window.history.replaceState(null, '', '/resident?device=leaky-token')
  expect(resolveDeviceToken()).toBeNull()
  expect(localStorage.getItem('isd.deviceToken')).toBeNull()
  expect(window.location.search).toBe('')
})

test('no token at all means the device is not set up', () => {
  expect(resolveDeviceToken()).toBeNull()
})
