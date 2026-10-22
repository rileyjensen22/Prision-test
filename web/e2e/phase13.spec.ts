import { expect, test } from '@playwright/test'

import { apiHeaders, openKiosk, staffLogin } from './helpers'

const day = (offset = 0) => new Date(Date.now() + offset * 86_400_000).toISOString().slice(0, 10)

test('out of cell: tap residents out and in together, and see who is out', async ({ context }) => {
  const officer = await context.newPage()
  await staffLogin(officer, 'e2e_officer', '/staff/out-of-cell')
  await expect(officer.getByTestId('nobody-out')).toBeVisible()
  await officer.getByLabel('Select E2E-UMA').check()
  await officer.getByLabel('Select E2E-VAL').check()
  await officer.getByLabel('Out for').selectOption('program')
  await officer.getByRole('button', { name: /Tap out 2 selected/ }).click()
  await expect(officer.getByTestId('notice')).toContainText('2 resident(s) tapped out')
  await expect(officer.getByTestId('out-E2E-UMA')).toContainText('program')
  await expect(officer.getByTestId('out-E2E-VAL')).toBeVisible()
  await expect(officer.getByLabel('Select E2E-UMA')).toBeDisabled() // already out

  // a second tap-out for someone already out is reported, not silently ignored
  await officer.getByRole('button', { name: 'Tap everyone in' }).click()
  await expect(officer.getByTestId('notice')).toContainText('tapped in')
  await expect(officer.getByTestId('nobody-out')).toBeVisible()
})

test('out of cell: residents below the minimum surface on the dashboard and the report', async ({
  context,
  request,
}) => {
  const officerHeaders = await apiHeaders(request, 'e2e_officer')
  const r = await request.get('/api/staff/roster', { headers: officerHeaders })
  const val = (await r.json()).find((x: { code: string }) => x.code === 'E2E-VAL')
  const rec = await request.post('/api/staff/out-of-cell', {
    headers: officerHeaders,
    data: { resident_id: val.resident_id, day: day(-1), minutes: 15 },
  })
  expect(rec.status()).toBe(201)

  const sup = await context.newPage()
  await staffLogin(sup, 'e2e_sup1', '/staff')
  await expect(sup.getByTestId('stat-below-minimum')).toContainText('Below out-of-cell minimum')
  await sup.getByTestId('stat-below-minimum').click()
  await expect(sup.getByTestId('below-E2E-VAL')).toContainText('15')
  await sup.getByLabel('Report day').fill(day(-1))
  await expect(sup.getByTestId('day-E2E-VAL')).toContainText('below minimum')
})

test('schedule: a unit’s day can be changed and only that unit sees it', async ({
  context,
  page,
}) => {
  const sup = await context.newPage()
  await staffLogin(sup, 'e2e_sup1', '/staff/schedule')
  await sup.getByLabel('Unit').selectOption('B')
  await expect(sup.getByTestId('schedule-blocks')).toContainText('Family visiting')
  await sup.getByLabel('Title').fill('Evening study')
  await sup.getByLabel('Start time').fill('20:15')
  await sup.getByLabel('Reason', { exact: true }).fill('unit B asked for an evening study hour')
  await sup.getByRole('button', { name: 'Add block' }).click()
  await expect(sup.getByTestId('notice')).toContainText('Block added')
  await expect(sup.getByTestId('block-20:15-program')).toContainText('Evening study')

  await openKiosk(page, 'uma', '/resident/feature/outdoor_rec')
  await expect(page.getByTestId('slot-20:15')).toContainText('Evening study')
  await expect(page.getByTestId('slot-20:15')).toHaveAttribute('data-kind', 'program')
  const other = await context.newPage() // a device in unit A
  await openKiosk(other, 'wren', '/resident/feature/outdoor_rec')
  await expect(other.getByTestId('slot-09:00')).toBeVisible()
  await expect(other.getByTestId('slot-20:15')).toHaveCount(0)

  await sup.getByLabel('Reason for cancelling').fill('the teacher is ill today')
  await sup.getByTestId('block-20:15-program').getByRole('button', { name: 'Cancel' }).click()
  await expect(sup.getByTestId('notice')).toContainText('Block cancelled')
  await openKiosk(page, 'uma', '/resident') // the other device shares this browser's storage
  await page.goto('/resident/feature/outdoor_rec')
  await expect(page.getByTestId('slot-20:15')).toContainText('cancelled')
})

test('schedule: a resident can sign up for a visit or program, and outdoor stays locked at tier 1', async ({
  page,
}) => {
  await openKiosk(page, 'val', '/resident/feature/outdoor_rec')
  await expect(page.getByTestId('slot-10:00')).toHaveAttribute('data-allowed', 'false') // outdoor
  await expect(page.getByTestId('slot-09:00')).toHaveAttribute('data-allowed', 'true') // indoor
  await expect(page.getByTestId('slot-16:30')).toHaveAttribute('data-allowed', 'false') // advanced
  const visit = page.getByTestId('slot-14:00')
  await expect(visit).toContainText('Family visiting')
  await visit.getByRole('button', { name: 'Book' }).click()
  await expect(visit).toHaveAttribute('data-booked', 'true')
})
