import { expect, test } from '@playwright/test'

import {
  allAuditEntries,
  apiHeaders,
  auditCountExcludingLogins,
  openKiosk,
  staffLogin,
  token,
} from './helpers'

test('reading: general texts at tier 1, expanded at tier 4', async ({ page }) => {
  await openKiosk(page, 'fay', '/resident/feature/reading_general')
  await expect(page.getByTestId('reading-tortoise-hare')).toHaveAttribute('data-allowed', 'true')
  await expect(page.getByTestId('reading-preamble')).toHaveAttribute('data-allowed', 'false')
  await expect(page.getByTestId('reading-preamble')).toContainText('Unlocks at Tier 4')

  await openKiosk(page, 'tess', '/resident/feature/reading_expanded')
  await page.getByTestId('reading-preamble').getByRole('button', { name: 'Read' }).click()
  await expect(page.getByTestId('reading-text')).toContainText('We the People')
  await page.getByRole('button', { name: /Back to the list/ }).click()
  await expect(page.getByTestId('reading-gettysburg')).toHaveAttribute('data-allowed', 'true')
})

test('jobs are optional and joining or leaving changes nothing about the resident', async ({
  page,
  request,
}) => {
  const auditor = await apiHeaders(request, 'e2e_auditor')
  const auditCount = () => auditCountExcludingLogins(request, auditor)
  const before = await auditCount()

  await openKiosk(page, 'tess')
  const tier = await page.getByTestId('tier-label').innerText()
  const lockCount = await page.getByTestId('lock').count()
  await page.getByTestId('jobs-link').click()
  await expect(page.getByTestId('jobs-voluntary')).toContainText(
    'never changes your tier, points, or privileges',
  )
  await expect(page.getByTestId('jobs-split')).toContainText('you receive $60')
  const job = page.locator('[data-testid^="job-"][data-enrolled]').first()
  await job.getByRole('button', { name: 'Join' }).click()
  await expect(job.getByTestId('job-joined')).toBeVisible()
  await job.getByRole('button', { name: 'Leave' }).click()
  await expect(job.getByRole('button', { name: 'Join' })).toBeVisible()

  await page.getByRole('link', { name: '← Back' }).click()
  await expect(page.getByTestId('tier-label')).toHaveText(tier)
  await expect(page.getByTestId('lock')).toHaveCount(lockCount)
  expect(await auditCount()).toBe(before) // no audit entry, points or sanction event was created
})

test('texting: monitored messages are shown; attorney messages are never stored', async ({
  page,
  context,
}) => {
  await openKiosk(page, 'tess', '/resident/feature/texting')
  await expect(page.getByTestId('texts-left')).toContainText('messages left today')

  await page.getByTestId('text-contact-attorney').click()
  await expect(page.getByTestId('text-notice')).toContainText('not stored or read')
  await page.getByLabel('Write a message').fill('Please bring the sealed documents')
  await page.getByRole('button', { name: 'Send' }).click()
  await expect(page.getByTestId('thread')).toContainText('Sent privately')
  await expect(page.getByTestId('thread')).not.toContainText('sealed')
  await page.getByRole('button', { name: /←/ }).click()

  await page.getByTestId('text-contact-family').click()
  await expect(page.getByTestId('text-notice')).toContainText('may be monitored')
  await page.getByLabel('Write a message').fill('hello from the unit')
  await page.getByRole('button', { name: 'Send' }).click()
  await expect(page.getByTestId('msg-out')).toContainText('hello from the unit')
  await expect(page.getByTestId('msg-in')).toContainText('mock reply')

  // Staff can see that messages happened, never what they said.
  const sup = await context.newPage()
  await staffLogin(sup, 'e2e_sup1', '/staff/roster')
  await sup.getByRole('link', { name: 'E2E-TESS' }).click()
  await sup.getByLabel('Reason for viewing activity').fill('routine welfare review')
  await sup.getByRole('button', { name: 'View activity' }).click()
  const table = sup.getByTestId('timeline')
  await expect(table).toContainText('text message')
  await expect(table).toContainText('attorney')
  await expect(table).not.toContainText('hello from the unit')
  await expect(table).not.toContainText('sealed')
})

test('rec time: baseline slots for everyone, outdoor needs a high tier', async ({ page }) => {
  await openKiosk(page, 'ivy')
  await page.getByTestId('tile-out_of_cell_minimum').click()
  await expect(page.getByTestId('rec-baseline')).toContainText('at least 60 minutes')
  await expect(page.getByTestId('slot-10:00')).toHaveAttribute('data-allowed', 'false')
  const slot = page.getByTestId('slot-09:00')
  await slot.getByRole('button', { name: 'Book' }).click()
  await expect(slot).toHaveAttribute('data-booked', 'true')
  await slot.getByRole('button', { name: 'Cancel' }).click()
  await expect(slot).toHaveAttribute('data-booked', 'false')
})

test('welfare: a resident who went quiet is flagged, and a check-in is recorded', async ({
  context,
}) => {
  const staff = await context.newPage()
  await staffLogin(staff, 'e2e_officer', '/staff/welfare')
  const panel = staff.getByTestId('welfare-E2E-WES')
  await expect(panel.getByTestId('flag-no_contact')).toContainText('days since any contact')
  await expect(panel.getByTestId('flag-usage_drop')).toContainText('Usually')
  await expect(staff.getByTestId('welfare-E2E-TESS')).toHaveCount(0) // a recently active resident
  await staff.getByRole('link', { name: 'Dashboard' }).click()
  await expect(staff.getByTestId('stat-welfare')).toContainText('Welfare flags')

  await staff
    .getByRole('navigation', { name: 'Main' })
    .getByRole('link', { name: 'Welfare' })
    .click()
  await panel.getByTestId('flag-no_contact').getByRole('button', { name: 'I checked in…' }).click()
  await expect(panel.getByRole('button', { name: 'Record check-in' })).toBeDisabled()
  await panel
    .getByLabel('What was done')
    .fill('Spoke with the resident at the door; they were unwell')
  await panel.getByRole('button', { name: 'Record check-in' }).click()
  await expect(staff.getByTestId('notice')).toContainText('Recorded')
  await expect(panel.getByTestId('flag-no_contact')).toHaveCount(0)
  await expect(panel.getByTestId('flag-usage_drop')).toBeVisible() // other flags remain
})

test('out-of-cell time below the minimum is recorded and flagged', async ({ context }) => {
  const sup = await context.newPage()
  await staffLogin(sup, 'e2e_sup1', '/staff/roster')
  await sup.getByRole('link', { name: 'E2E-ZED' }).click()
  await expect(sup.getByTestId('ooc-days')).toContainText('—') // nothing recorded yet
  await sup.getByLabel('Minutes out of cell').fill('25')
  await sup.getByRole('button', { name: 'Record', exact: true }).click()
  await expect(sup.getByTestId('notice')).toContainText('Recorded')
  await expect(sup.getByTestId('ooc-days')).toContainText('25')

  await sup.getByRole('link', { name: 'Welfare' }).click()
  await expect(
    sup.getByTestId('welfare-E2E-ZED').getByTestId('flag-out_of_cell_below'),
  ).toContainText('Lowest recent day: 25 minutes (minimum 60)')
})

test('activity timeline: supervisors and up only, reason required, access is logged', async ({
  context,
  request,
}) => {
  const officer = await context.newPage()
  await staffLogin(officer, 'e2e_officer', '/staff/roster')
  await officer.getByRole('link', { name: 'E2E-ALICE' }).click()
  await expect(officer.getByTestId('activity-panel')).toHaveCount(0)

  const aud = await context.newPage()
  await staffLogin(aud, 'e2e_auditor', '/staff/roster')
  await aud.getByRole('link', { name: 'E2E-ALICE' }).click()
  await expect(aud.getByRole('button', { name: 'View activity' })).toBeDisabled()
  await aud.getByLabel('Reason for viewing activity').fill('quarterly compliance audit')
  await aud.getByRole('button', { name: 'View activity' }).click()
  await expect(aud.getByTestId('timeline')).toContainText('sanction')
  const entries = await allAuditEntries(request, await apiHeaders(request, 'e2e_auditor'))
  expect(
    entries.some(
      (e) => e.action === 'monitoring_access' && e.payload.reason === 'quarterly compliance audit',
    ),
  ).toBe(true)
})

test('video: covering the camera ends the call and a supervisor decides', async ({
  context,
  request,
}) => {
  const dev = { 'X-Device-Token': token('vic') }
  const contacts = await (await request.get('/api/device/contacts', { headers: dev })).json()
  const call = await (
    await request.post('/api/device/video-calls', {
      headers: dev,
      data: { contact_id: contacts[0].id },
    })
  ).json()
  expect(call.max_seconds).toBe(30 * 60)
  const tamper = await (
    await request.post(`/api/device/video-calls/${call.call_id}/tamper`, {
      headers: dev,
      data: { signal: 'dark', covered_ms: 3000 },
    })
  ).json()
  expect(tamper.status).toBe('pending')

  const kiosk = await context.newPage()
  await openKiosk(kiosk, 'vic')
  await expect(kiosk.getByTestId('lock')).toHaveCount(0) // not locked until a supervisor confirms

  const sup = await context.newPage()
  await staffLogin(sup, 'e2e_sup2', '/staff/confirmations')
  const row = sup.locator('[data-testid^="pending-"]', { hasText: 'E2E-VIC' })
  await expect(row).toContainText('DEVICE_TAMPER')
  await expect(row).toContainText('System event video-call-')
  await expect(row).toContainText('system')
  await row.getByRole('button', { name: 'Confirm' }).click()
  await kiosk.reload()
  await expect(kiosk.getByTestId('lock-title')).toHaveText('Device camera covered during a call')
  await expect(kiosk.getByTestId('tile-video')).toHaveAttribute('data-allowed', 'false')
  await expect(kiosk.getByTestId('tile-calls')).toHaveAttribute('data-allowed', 'true')
})

test('facility cell-camera events become pending sanctions, never automatic ones', async ({
  context,
  request,
}) => {
  const admin = await apiHeaders(request, 'e2e_admin')
  const eventId = `evt-${Date.now()}`
  const body = { event_id: eventId, type: 'camera_obstruction', payload: { cell: 'E2E-cam' } }
  const first = await (
    await request.post('/api/mock/facility-events', { headers: admin, data: body })
  ).json()
  const again = await (
    await request.post('/api/mock/facility-events', { headers: admin, data: body })
  ).json()
  expect(first.result).toMatch(/^sanction:\d+:pending$/)
  expect(again).toEqual(first)

  const kiosk = await context.newPage()
  await openKiosk(kiosk, 'cam')
  await expect(kiosk.getByTestId('lock')).toHaveCount(0)
  const sup = await context.newPage()
  await staffLogin(sup, 'e2e_sup1', '/staff/confirmations')
  const row = sup.locator('[data-testid^="pending-"]', { hasText: 'E2E-CAM' })
  await expect(row).toContainText(`System event ${eventId}`)
})

test('content sources and jobs: admins manage the allow-list; switching it off blocks reading', async ({
  context,
}) => {
  const admin = await context.newPage()
  await staffLogin(admin, 'e2e_admin', '/staff/content')
  await expect(admin.getByTestId('sources')).toContainText('Bundled public-domain texts')
  await expect(admin.getByTestId('job-listings')).toContainText('transcription_public_domain')
  await admin.getByLabel('Source name').fill('Approved state library')
  await admin.getByLabel('Source address').fill('http://not-secure.example')
  await admin.getByRole('button', { name: 'Add external source' }).click()
  await expect(admin.getByTestId('notice')).toContainText('https')
  await admin.getByLabel('Source address').fill('https://library.example')
  await admin.getByRole('button', { name: 'Add external source' }).click()
  await expect(admin.getByTestId('sources')).toContainText('Approved state library')

  const bundled = admin
    .getByTestId('sources')
    .locator('tr', { hasText: 'Bundled public-domain texts' })
  await bundled.getByRole('button', { name: 'Turn off' }).click()
  const kiosk = await context.newPage()
  await openKiosk(kiosk, 'tess', '/resident/feature/reading_general')
  await expect(kiosk.getByTestId('reading-tortoise-hare')).toHaveAttribute('data-allowed', 'false')
  await bundled.getByRole('button', { name: 'Approve' }).click()
  await kiosk.reload()
  await expect(kiosk.getByTestId('reading-tortoise-hare')).toHaveAttribute('data-allowed', 'true')

  const sup = await context.newPage()
  await staffLogin(sup, 'e2e_sup1', '/staff/content')
  await expect(sup.getByLabel('Source name')).toHaveCount(0) // read-only for non-admins
})
