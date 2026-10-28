import { expect, test } from '@playwright/test'

import { apiHeaders, staffLogin } from './helpers'

test('the dashboard groups the facility by hub, line and floor, and a floor opens its roster', async ({
  context,
}) => {
  const sup = await context.newPage()
  await staffLogin(sup, 'e2e_sup1', '/staff')
  const overview = sup.getByTestId('facility-overview')
  await expect(overview).toBeVisible()
  await overview.getByText('Line H1-L1').click()
  await expect(overview.getByTestId('floor-H1-L1-1')).toContainText('1 of 3 cells in use')
  await overview.getByTestId('floor-H1-L1-1').click()
  await expect(sup).toHaveURL(/hub=H1&line=H1-L1&floor=1/)
  await expect(sup.getByTestId('row-E2E-CHA')).toBeVisible()
  await expect(sup.getByTestId('row-E2E-CHB')).toHaveCount(0) // that one is on the other line
})

test('the roster searches by code and the device list filters by line', async ({ context }) => {
  const sup = await context.newPage()
  await staffLogin(sup, 'e2e_sup1', '/staff/roster')
  await sup.getByPlaceholder('Code or cell, then Enter').fill('E2E-FAY')
  await sup.keyboard.press('Enter')
  await expect(sup.getByTestId('row-E2E-FAY')).toBeVisible()
  await expect(sup.getByTestId('row-E2E-CHA')).toHaveCount(0)

  await sup.goto('/staff/devices')
  await sup.getByTestId('device-filters').locator('select').nth(1).selectOption('H1-L2')
  await expect(sup.getByText('E2E-DEV-chb')).toBeVisible()
  await expect(sup.getByText('E2E-DEV-cha')).toHaveCount(0)
})

test('the dashboard numbers agree with the roster', async ({ request }) => {
  const h = await apiHeaders(request, 'e2e_sup1')
  const summary = await (await request.get('/api/staff/summary', { headers: h })).json()
  const roster = await (await request.get('/api/staff/roster', { headers: h })).json()
  const page = await (await request.get('/api/staff/roster/page?limit=500', { headers: h })).json()
  expect(summary.residents).toBe(roster.length)
  expect(page.total).toBe(roster.length)
  const overview = await (await request.get('/api/staff/facility/overview', { headers: h })).json()
  expect(overview.total.cells).toBe(10) // 8 new cells + the two chess residents' own
  expect(overview.total.occupied).toBe(2)
})

test('an officer can see the grouped numbers but nobody outside staff can', async ({ request }) => {
  const officer = await apiHeaders(request, 'e2e_officer')
  expect((await request.get('/api/staff/facility/overview', { headers: officer })).status()).toBe(
    200,
  )
  expect((await request.get('/api/staff/facility/overview')).status()).toBe(401)
})
