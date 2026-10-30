import { expect, test } from '@playwright/test'

import { apiHeaders, openKiosk, staffLogin } from './helpers'

const day = (offset = 0) => new Date(Date.now() + offset * 86_400_000).toISOString().slice(0, 10)

async function residentId(
  request: import('@playwright/test').APIRequestContext,
  headers: Record<string, string>,
  code: string,
) {
  const r = await request.get('/api/staff/roster', { headers })
  return (await r.json()).find((x: { code: string }) => x.code === code).resident_id as number
}

test('intake: a supervisor admits a resident with contacts, a category and a release date', async ({
  page,
}) => {
  await staffLogin(page, 'e2e_sup1', '/staff/intake')
  const form = page.getByTestId('intake-form')
  await form.getByLabel('Name', { exact: true }).fill('Synthetic Admit')
  await form.getByLabel('Cell').selectOption('E2E-FREE-1')
  await form.getByLabel('Device').selectOption('E2E-DEV-FREE-1')
  await form.getByLabel('Language').selectOption('es')
  await form.getByLabel('Prior returns').fill('2')
  await form.getByLabel('Source of that number').fill('synthetic records')
  await form.getByLabel('Release date').fill(day(90))
  await form.getByLabel(/SEX_OFFENSE/).check()
  await form.getByRole('button', { name: 'Add contact' }).click()
  await form.getByLabel('Contact 1 name').fill('Pat Family')
  await form.getByLabel('Contact 1 number').fill('555-0142')
  await form.getByLabel('Reason for admission').fill('new admission')
  await form.getByRole('button', { name: 'Admit resident' }).click()

  await expect(page.getByTestId('notice')).toContainText('Admitted as RES-')
  await page.getByRole('link', { name: 'Open the resident' }).click()
  await expect(page.getByTestId('release-date')).toContainText(day(90))
  await expect(page.getByTestId('resident-summary')).toContainText('prior returns 2')

  // the same cell cannot be given twice
  await page.goto('/staff/intake')
  await expect(page.getByLabel('Cell')).not.toContainText('E2E-FREE-1')
})

test('intake is for supervisors and admins only', async ({ page }) => {
  await staffLogin(page, 'e2e_officer', '/staff/intake')
  await expect(page.getByRole('alert')).toContainText('Your role cannot open this page')
})

test('reentry: the release date, checklist and resources reach the resident', async ({
  context,
  request,
}) => {
  const sup = await apiHeaders(request, 'e2e_sup1')
  const rid = await residentId(request, sup, 'E2E-REX')

  const staff = await context.newPage()
  await staffLogin(staff, 'e2e_sup1', `/staff/residents/${rid}`)
  const panel = staff.getByTestId('reentry-panel')
  await panel.getByLabel('Release date', { exact: true }).fill(day(30))
  await panel.getByLabel('Reason for the date').fill('sentence end')
  await panel.getByRole('button', { name: 'Save date' }).click()
  await expect(panel.getByTestId('release-date')).toContainText(day(30))
  await panel.getByLabel('Status for HOUSING').selectOption('done')
  await expect(panel.getByTestId('staff-item-HOUSING')).toContainText('done')

  const kiosk = await context.newPage()
  await openKiosk(kiosk, 'rex')
  await expect(kiosk.getByTestId('release-countdown')).toContainText('30 days')
  await kiosk.getByTestId('release-countdown').click()
  await expect(kiosk.getByTestId('reentry-item-HOUSING')).toHaveAttribute('data-status', 'done')
  await expect(kiosk.getByTestId('reentry-progress')).toContainText('1 of 5 done')
  await expect(kiosk.getByTestId('reentry-resources')).toContainText('Sample Housing Help Line')
  await expect(kiosk.getByTestId('reentry-resources')).toContainText('555-01')
})

test('outcomes: aggregates only, small groups hidden, export is off until enabled', async ({
  context,
}) => {
  const admin = await context.newPage()
  await staffLogin(admin, 'e2e_admin', '/staff/outcomes')
  await expect(admin.getByTestId('outcomes-note')).toContainText('There are no individual scores')
  await expect(admin.getByTestId('cohort-table')).not.toContainText('E2E-')
  await admin.getByLabel('Reason for export').fill('evaluation study')
  await admin.getByRole('button', { name: 'Export' }).click()
  await expect(admin.getByTestId('notice')).toContainText('turned off')

  const auditor = await context.newPage()
  await staffLogin(auditor, 'e2e_auditor', '/staff/outcomes')
  await expect(auditor.getByTestId('cohort-table')).toBeVisible()
  await expect(auditor.getByText('Enter an outcome from customer records')).toHaveCount(0)
})
