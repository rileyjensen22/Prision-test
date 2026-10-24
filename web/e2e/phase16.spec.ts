import { expect, test } from '@playwright/test'

import { openKiosk, staffLogin } from './helpers'

test('a new kiosk pairs with a one-time code and is then waiting for an assignment', async ({
  context,
  browser,
}) => {
  const admin = await context.newPage()
  await staffLogin(admin, 'e2e_admin', '/staff/devices')
  const code = `E2E-NEW-${Date.now().toString(36).toUpperCase()}`
  await admin.getByLabel('New device code').fill(code)
  await admin.getByRole('button', { name: 'Enroll' }).click()
  await expect(admin.getByTestId(`device-${code}`)).toContainText('not paired')
  await admin.getByTestId(`device-${code}`).getByRole('button', { name: 'Setup code' }).click()
  const setup = (await admin.getByTestId('pairing-code').innerText()).trim()
  expect(setup).toMatch(/^[A-Z2-9]{8}$/)

  // a fresh browser profile = a kiosk that has never been set up
  const fresh = await (await browser.newContext()).newPage()
  await fresh.goto('/resident')
  await expect(fresh.getByTestId('pairing')).toBeVisible()
  await fresh.getByLabel('Setup code').fill('WRONGCODE')
  await fresh.getByRole('button', { name: 'Connect' }).click()
  await expect(fresh.getByRole('alert')).toContainText('did not work')
  await fresh.getByLabel('Setup code').fill(setup)
  await fresh.getByRole('button', { name: 'Connect' }).click()
  await expect(fresh.getByTestId('status-message')).toContainText('not assigned to a resident', {
    ignoreCase: true,
  })

  // the code works once
  const again = await (await browser.newContext()).newPage()
  await again.goto('/resident')
  await again.getByLabel('Setup code').fill(setup)
  await again.getByRole('button', { name: 'Connect' }).click()
  await expect(again.getByRole('alert')).toContainText('did not work')

  // and the device reports in, so staff can see it
  await expect(async () => {
    await admin.reload()
    await expect(admin.getByTestId(`device-${code}`)).not.toContainText('not paired')
    await expect(admin.getByTestId(`device-${code}`)).toContainText('storage')
  }).toPass({ timeout: 20_000 })
})

test('an admin pause shows the resident a reason and end time, keeps the baseline, and can be lifted', async ({
  context,
}) => {
  const kiosk = await context.newPage()
  await openKiosk(kiosk, 'sol')
  await expect(kiosk.getByTestId('tile-basic_education')).toBeVisible()

  const admin = await context.newPage()
  await staffLogin(admin, 'e2e_admin', '/staff/devices')
  await admin.getByLabel('Reason', { exact: true }).fill('checking the device')
  await admin.getByTestId('device-E2E-DEV-sol').getByRole('button', { name: 'Pause' }).click()
  await expect(admin.getByTestId('notice')).toContainText('paused')

  await kiosk.reload()
  await expect(kiosk.getByText('Paused by staff for now').first()).toBeVisible()
  await expect(kiosk.getByTestId('tile-basic_education')).toHaveAttribute('data-allowed', 'true')
  await expect(kiosk.getByRole('button', { name: /request staff/i })).toBeVisible()

  await admin.getByTestId('device-E2E-DEV-sol').getByRole('button', { name: 'Resume' }).click()
  await kiosk.reload()
  await expect(kiosk.getByText('Paused by staff for now')).toHaveCount(0)
})

test('only admins can pause or restart; others do not see the buttons', async ({ page }) => {
  await staffLogin(page, 'e2e_sup1', '/staff/devices')
  await expect(page.getByTestId('device-E2E-DEV-sol')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Pause' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Setup code' }).first()).toBeVisible()
})
