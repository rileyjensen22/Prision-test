import { expect, test } from '@playwright/test'

import { openKiosk, staffLogin } from './helpers'

test('sign in, wrong password, sign out', async ({ page }) => {
  await page.goto('/staff')
  await page.getByLabel('Username').fill('e2e_officer')
  await page.getByLabel('Password').fill('wrong')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('alert')).toBeVisible()
  await staffLogin(page, 'e2e_officer')
  await expect(page.getByTestId('whoami')).toHaveText('e2e_officer (officer)')
  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(page.getByRole('heading', { name: 'Staff sign in' })).toBeVisible()
})

test('full flow: record, confirm, resident appeals, other supervisor overturns, audit verifies', async ({
  context,
}) => {
  const kiosk = await context.newPage()
  const officer = await context.newPage()
  const sup1 = await context.newPage()
  const sup2 = await context.newPage()
  const auditor = await context.newPage()

  // 1. An officer records a significant infraction with a second person's report as evidence.
  await staffLogin(officer, 'e2e_officer')
  await expect(officer.getByRole('navigation', { name: 'Main' })).not.toContainText('Confirmations')
  await officer.getByRole('link', { name: 'Roster' }).click()
  await officer.getByRole('link', { name: 'E2E-JO' }).click()
  await officer.getByLabel('Infraction').selectOption('CAM_BLOCK')
  await expect(officer.getByTestId('infraction-help')).toContainText(
    'Needs evidence and a supervisor',
  )
  await expect(officer.getByRole('button', { name: 'Submit' })).toBeDisabled() // evidence is required
  await officer.getByLabel('Reported by').selectOption({ label: 'e2e_colleague (officer)' })
  await officer.getByRole('button', { name: 'Submit' }).click()
  await expect(officer.getByTestId('notice')).toContainText('sent for supervisor confirmation')
  await expect(officer.getByTestId('sanction-history')).toContainText('pending')

  // Nothing is locked for the resident yet.
  await openKiosk(kiosk, 'jo')
  await expect(kiosk.getByTestId('tile-calls')).toHaveAttribute('data-allowed', 'true')
  await expect(kiosk.getByTestId('lock')).toHaveCount(0)

  // 2. A supervisor sees the evidence and confirms.
  await staffLogin(sup1, 'e2e_sup1', '/staff/confirmations')
  const pending = sup1.locator('[data-testid^="pending-"]', { hasText: 'E2E-JO' })
  await expect(pending).toContainText('CAM_BLOCK')
  await expect(pending).toContainText('e2e_officer')
  await expect(pending).toContainText('Report from e2e_colleague')
  await pending.getByRole('button', { name: 'Confirm' }).click()
  await expect(sup1.getByTestId('notice')).toContainText('Confirmed')
  await expect(sup1.locator('[data-testid^="pending-"]', { hasText: 'E2E-JO' })).toHaveCount(0)

  // 3. The resident now sees the lock, its reason and end time; baseline services stay open.
  await kiosk.reload()
  await expect(kiosk.getByTestId('lock-title')).toHaveText('Cell camera blocked')
  await expect(kiosk.getByTestId('tile-calls')).toHaveAttribute('data-allowed', 'false')
  await expect(kiosk.getByTestId('tile-commissary')).toHaveAttribute('data-allowed', 'false')
  for (const f of ['attorney_calls', 'legal_materials', 'medical_requests', 'basic_education'])
    await expect(kiosk.getByTestId(`tile-${f}`)).toHaveAttribute('data-allowed', 'true')
  await kiosk.getByTestId('lock').getByRole('link', { name: 'Appeal' }).click()
  await kiosk.getByRole('button', { name: 'Send appeal' }).click()
  await expect(kiosk.getByTestId('appeal-result')).toContainText('Your appeal was sent')

  // 4. A different supervisor reviews and overturns.
  await staffLogin(sup2, 'e2e_sup2', '/staff/appeals')
  const appeal = sup2.locator('tr[data-testid^="appeal-"]', { hasText: 'E2E-JO' })
  await expect(appeal).toContainText('e2e_officer')
  await appeal.getByRole('button', { name: 'Review…' }).click()
  await appeal.getByLabel('Outcome').selectOption('overturned')
  await appeal.getByLabel('Review note').fill('camera was bumped, not covered')
  await appeal.getByRole('button', { name: 'Submit decision' }).click()
  await expect(sup2.getByTestId('notice')).toContainText('Overturned')

  // 5. The lock is gone on the device.
  await kiosk.goto('/resident')
  await expect(kiosk.getByTestId('lock')).toHaveCount(0)
  await expect(kiosk.getByTestId('tile-calls')).toHaveAttribute('data-allowed', 'true')

  // 6. The auditor sees every step and the chain verifies.
  await staffLogin(auditor, 'e2e_auditor', '/staff/audit')
  await auditor.getByRole('button', { name: 'Verify chain' }).click()
  await expect(auditor.getByTestId('verify-result')).toContainText('Chain verified')
  const table = auditor.getByTestId('audit-table')
  for (const action of ['sanction issued', 'sanction confirmed', 'appeal filed', 'appeal reviewed'])
    await expect(table).toContainText(action)
})

test('a supervisor cannot confirm their own sanction', async ({ context }) => {
  const sup1 = await context.newPage()
  const sup2 = await context.newPage()
  await staffLogin(sup1, 'e2e_sup1', '/staff/roster')
  await sup1.getByRole('link', { name: 'E2E-KIM' }).click()
  await sup1.getByLabel('Infraction').selectOption('DEVICE_DAMAGE')
  await sup1.getByLabel('Reported by').selectOption({ label: 'e2e_colleague (officer)' })
  await sup1.getByRole('button', { name: 'Submit' }).click()
  await expect(sup1.getByTestId('notice')).toContainText('sent for supervisor confirmation')

  await sup1.getByRole('link', { name: 'Confirmations' }).click()
  const row = sup1.locator('[data-testid^="pending-"]', { hasText: 'E2E-KIM' })
  await expect(row.getByTestId('own-sanction')).toContainText('another supervisor must confirm')
  await expect(row.getByRole('button', { name: 'Confirm' })).toHaveCount(0)

  await staffLogin(sup2, 'e2e_sup2', '/staff/confirmations')
  const other = sup2.locator('[data-testid^="pending-"]', { hasText: 'E2E-KIM' })
  await expect(other.getByRole('button', { name: 'Confirm' })).toBeVisible()
  await other.getByRole('button', { name: 'Reject…' }).click()
  await other.getByLabel('Reason for rejecting').fill('not enough evidence')
  await other.getByRole('button', { name: 'Reject', exact: true }).click()
  await expect(sup2.getByTestId('notice')).toContainText('Rejected')
})

test('roster shows tiers, locks, pending items and offline devices', async ({ page }) => {
  await staffLogin(page, 'e2e_officer', '/staff/roster')
  await expect(page.getByTestId('row-E2E-ALICE')).toContainText('DISRUPT')
  await expect(page.getByTestId('row-E2E-CARLA')).toContainText('ceiling 2')
  await expect(page.getByTestId('row-E2E-ZED')).toContainText('CELL_MESS')
  await expect(page.getByTestId('row-E2E-ZED').getByTestId('offline-badge')).toBeVisible() // device never synced
  await page.getByRole('link', { name: 'Dashboard' }).click()
  await expect(page.getByTestId('stat-outliers')).toHaveCount(0) // officers do not see peer comparisons
  await expect(page.getByTestId('event-feed')).toContainText('sanction issued')
})

test('outlier view flags an officer far above their peers (supervisors and up only)', async ({
  context,
}) => {
  const officer = await context.newPage()
  await staffLogin(officer, 'e2e_officer', '/staff/outliers')
  await expect(officer.getByRole('alert')).toContainText('Your role cannot open this page')

  const sup = await context.newPage()
  await staffLogin(sup, 'e2e_sup1', '/staff/outliers')
  await expect(sup.getByTestId('outlier-e2e_heavy')).toContainText('Infractions recorded')
  await expect(sup.getByTestId('outlier-e2e_colleague')).not.toContainText('Infractions recorded')
  await sup.getByRole('link', { name: 'Dashboard' }).click()
  await expect(sup.getByTestId('stat-outliers')).toContainText('Staff outlier flags')
})

test('config editor: admins edit with a reason and get a new version; others read only', async ({
  context,
}) => {
  const admin = await context.newPage()
  await staffLogin(admin, 'e2e_admin', '/staff/config')
  const box = admin.getByTestId('config-json')
  await expect(box).toHaveValue(/"baseline_out_of_cell_minutes": 60/)
  const text = (await box.inputValue()).replace(
    '"baseline_out_of_cell_minutes": 60',
    '"baseline_out_of_cell_minutes": 75',
  )
  await box.fill(text)
  await expect(admin.getByRole('button', { name: 'Save new version' })).toBeDisabled() // reason required
  await admin.getByLabel('Reason for change').fill('longer out-of-cell minimum for pilot')
  await admin.getByRole('button', { name: 'Save new version' }).click()
  await expect(admin.getByTestId('notice')).toContainText('Saved as version')
  await expect(admin.getByTestId('versions')).toContainText('longer out-of-cell minimum for pilot')

  // invalid config is refused by the server and nothing is saved
  await box.fill(text.replace('"promotion_thresholds": [', '"promotion_thresholds": [5, '))
  await admin.getByLabel('Reason for change').fill('try a bad value')
  await admin.getByRole('button', { name: 'Save new version' }).click()
  await expect(admin.getByTestId('notice')).toContainText('promotion_thresholds')

  // the repeat-return curve preview comes from the engine
  await admin.getByLabel('N', { exact: true }).fill('6')
  await admin.getByLabel('p', { exact: true }).fill('2')
  const preview = admin.getByTestId('curve-preview').locator('tbody tr')
  await expect(preview).toHaveCount(8)
  await expect(preview.last()).toContainText('7')
  await expect(preview.last()).toContainText('1')

  const auditor = await context.newPage()
  await staffLogin(auditor, 'e2e_auditor', '/staff/config')
  await expect(auditor.getByTestId('config-json')).not.toBeEditable()
  await expect(auditor.getByRole('button', { name: 'Save new version' })).toHaveCount(0)
})

test('staff change a resident’s settings (with a reason); the kiosk follows', async ({
  context,
}) => {
  const staff = await context.newPage()
  await staffLogin(staff, 'e2e_officer', '/staff/roster')
  await staff.getByRole('link', { name: 'E2E-FAY' }).click()
  await staff.getByLabel('Text size').selectOption('xlarge')
  await expect(staff.getByRole('button', { name: 'Save settings' })).toBeDisabled()
  await staff.getByLabel('Reason for change').fill('resident asked for bigger text')
  await staff.getByRole('button', { name: 'Save settings' }).click()
  await expect(staff.getByTestId('notice')).toContainText('text_size')

  const kiosk = await context.newPage()
  await openKiosk(kiosk, 'fay')
  await expect(kiosk.getByTestId('kiosk')).toHaveClass(/--scale:1.5/)
})
