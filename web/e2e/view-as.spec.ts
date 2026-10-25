import { expect, test } from '@playwright/test'

import { apiHeaders, auditCountExcludingLogins, openKiosk, staffLogin } from './helpers'

const sim = (page: import('@playwright/test').Page) => page.getByTestId('sim-screen')

test('sandbox: override tier, sanctions and language; nothing is written anywhere', async ({
  context,
  request,
}) => {
  const auditor = await apiHeaders(request, 'e2e_auditor')
  const auditCount = () => auditCountExcludingLogins(request, auditor)
  const appealsFor = async () =>
    (
      await (
        await request.get('/api/staff/appeals?include_closed=true', { headers: auditor })
      ).json()
    ).filter((a: { resident_code: string }) => a.resident_code === 'E2E-FAY').length
  const before = { audit: await auditCount(), appeals: await appealsFor() }

  const staff = await context.newPage()
  await staffLogin(staff, 'e2e_officer', '/staff/view-as')
  await expect(staff.getByTestId('sandbox-note')).toContainText('SIMULATION')
  await staff.getByLabel('Resident').selectOption({ label: 'E2E-FAY (tier 1)' })
  await expect(sim(staff).getByTestId('tier-label')).toHaveText('Tier 1')
  await expect(sim(staff)).toContainText('SIMULATION')

  await staff.getByLabel('Tier', { exact: true }).selectOption('6')
  await expect(sim(staff).getByTestId('tier-label')).toHaveText('Tier 6')
  await expect(sim(staff).getByTestId('allowance-calls')).toContainText('45 of 45 minutes left')

  await staff.getByLabel('Add sanction').selectOption('DISRUPT')
  await staff.getByLabel('Hours left').fill('10')
  await staff.getByRole('button', { name: 'Add', exact: true }).click()
  await expect(sim(staff).getByTestId('lock-title')).toHaveText('Disruptive behavior')
  await expect(sim(staff).getByTestId('tile-calls')).toHaveAttribute('data-allowed', 'false')
  await expect(sim(staff).getByTestId('tile-legal_materials')).toHaveAttribute(
    'data-allowed',
    'true',
  )

  await staff.getByLabel('Language').selectOption('es')
  await expect(sim(staff).getByTestId('tier-label')).toHaveText('Nivel 6')
  await expect(staff.getByRole('link', { name: 'Dashboard' })).toBeVisible() // staff UI stays English

  // The buttons in the simulation work visually but send nothing.
  await sim(staff).getByRole('link', { name: 'Apelar' }).click()
  await sim(staff).getByRole('button', { name: 'Enviar apelación' }).click()
  await expect(sim(staff).getByTestId('appeal-result')).toBeVisible()

  // The real resident and the real records are untouched.
  expect(await auditCount()).toBe(before.audit)
  expect(await appealsFor()).toBe(before.appeals)
  const kiosk = await context.newPage()
  await openKiosk(kiosk, 'fay')
  await expect(kiosk.getByTestId('tier-label')).toHaveText('Tier 1')
  await expect(kiosk.getByTestId('lock')).toHaveCount(0)
})

test('sandbox: time travel and the repeat-return ceiling', async ({ page }) => {
  await staffLogin(page, 'e2e_officer', '/staff/view-as')
  await page.getByLabel('Resident').selectOption({ label: 'E2E-ALICE (tier 3)' })
  await expect(sim(page).getByTestId('lock-title')).toHaveText('Disruptive behavior') // real lock, ~22h left

  const inTwoDays = new Date(Date.now() + 2 * 24 * 3600 * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  const local = `${inTwoDays.getFullYear()}-${pad(inTwoDays.getMonth() + 1)}-${pad(inTwoDays.getDate())}T${pad(inTwoDays.getHours())}:${pad(inTwoDays.getMinutes())}`
  await page.getByLabel('View as of').fill(local)
  await expect(sim(page).getByTestId('lock')).toHaveCount(0)
  await expect(sim(page).getByTestId('tile-calls')).toHaveAttribute('data-allowed', 'true')

  await page.getByLabel('Tier', { exact: true }).selectOption('10')
  await page.getByLabel('Prior returns').fill('10')
  await expect(sim(page).getByTestId('tier-label')).toHaveText('Tier 2')
  await expect(sim(page).getByTestId('next-tier')).toContainText('highest available tier is 2')

  await page.getByRole('button', { name: 'Reset overrides' }).click()
  await expect(sim(page).getByTestId('lock-title')).toHaveText('Disruptive behavior')
})

test('live mirror: logged, read-only, follows the device, hides private screens', async ({
  context,
  request,
}) => {
  const kiosk = await context.newPage()
  await openKiosk(kiosk, 'hal', '/resident/tier')
  await expect(
    kiosk.getByTestId('ceiling-card').or(kiosk.getByRole('heading', { name: 'Tier 1' })),
  ).toBeVisible()

  const officer = await context.newPage()
  await staffLogin(officer, 'e2e_officer')
  await expect(officer.getByRole('navigation', { name: 'Main' })).not.toContainText('Live mirror')

  const sup = await context.newPage()
  await staffLogin(sup, 'e2e_sup1', '/staff/mirror')
  await expect(sup.getByRole('button', { name: 'Start mirror' })).toBeDisabled()
  await sup.getByLabel('Resident').selectOption({ label: 'E2E-HAL' })
  await sup.getByLabel('Reason for mirroring').fill('welfare check requested by shift lead')
  await sup.getByRole('button', { name: 'Start mirror' }).click()

  const live = sup.getByTestId('mirror-live')
  await expect(live).toContainText('LIVE MIRROR · read-only')
  await expect(sup.getByTestId('mirror-target')).toHaveText('E2E-HAL')
  await expect(sup.getByTestId('mirror-screen')).toContainText('/resident/tier', {
    timeout: 10_000,
  })
  await expect(sup.getByTestId('sim-body')).toHaveClass(/pointer-events-none/)
  await expect(sup.getByTestId('sim-screen')).not.toContainText('SIMULATION')

  // The mirror follows the resident to the home screen...
  await kiosk.getByRole('link', { name: 'Back' }).click()
  await expect(sup.getByTestId('mirror-screen')).toContainText(/Screen: \/resident( |\()/, {
    timeout: 10_000,
  })
  await expect(sup.getByTestId('tier-label')).toBeVisible()

  // ...but never into private screens.
  await kiosk.getByTestId('tile-legal_materials').click()
  await expect(sup.getByTestId('mirror-redacted')).toContainText('Private screen', {
    timeout: 10_000,
  })
  await expect(sup.getByTestId('sim-screen')).toHaveCount(0)
  await expect(sup.getByTestId('mirror-redacted')).not.toContainText('legal_materials')

  await kiosk.getByRole('link', { name: 'Back' }).click()
  await expect(sup.getByTestId('sim-screen')).toBeVisible({ timeout: 10_000 })

  await sup.getByRole('button', { name: 'End mirror' }).click()
  await expect(sup.getByTestId('mirror-live')).toHaveCount(0)
  const row = sup.getByTestId('mirror-history').locator('tr', { hasText: 'E2E-HAL' }).first()
  await expect(row).toContainText('welfare check requested by shift lead')
  await expect(row).toContainText('manual')

  // The auditor sees the session and its start/end in the audit log.
  const auditor = await context.newPage()
  await staffLogin(auditor, 'e2e_auditor', '/staff/mirror')
  await expect(auditor.getByRole('button', { name: 'Start mirror' })).toHaveCount(0) // read-only role
  await expect(auditor.getByTestId('mirror-history')).toContainText('e2e_sup1')
  await auditor.getByRole('link', { name: 'Audit log' }).click()
  await expect(auditor.getByTestId('audit-table')).toContainText('mirror started')
  await expect(auditor.getByTestId('audit-table')).toContainText('mirror ended')
  await auditor.getByRole('button', { name: 'Verify chain' }).click()
  await expect(auditor.getByTestId('verify-result')).toContainText('Chain verified')
  void request
})

test('live mirror hides an attorney call completely', async ({ context }) => {
  const kiosk = await context.newPage()
  await openKiosk(kiosk, 'ivy', '/resident/feature/calls')
  const sup = await context.newPage()
  await staffLogin(sup, 'e2e_sup2', '/staff/mirror')
  await sup.getByLabel('Resident').selectOption({ label: 'E2E-IVY' })
  await sup.getByLabel('Reason for mirroring').fill('checking the call screen works')
  await sup.getByRole('button', { name: 'Start mirror' }).click()
  await expect(sup.getByTestId('mirror-screen')).toContainText('/resident/feature/calls', {
    timeout: 10_000,
  })

  await kiosk.getByTestId('contact-attorney').getByRole('button', { name: 'Call' }).click()
  await expect(kiosk.getByTestId('call-notice')).toContainText('not recorded')
  await expect(sup.getByTestId('mirror-redacted')).toContainText('private attorney call', {
    timeout: 10_000,
  })
  await expect(sup.getByTestId('sim-screen')).toHaveCount(0)

  await kiosk.getByRole('button', { name: 'End call' }).click()
  await expect(sup.getByTestId('sim-screen')).toBeVisible({ timeout: 10_000 })
  await sup.getByRole('button', { name: 'End mirror' }).click()
})
