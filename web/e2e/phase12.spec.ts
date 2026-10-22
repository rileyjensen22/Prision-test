import { expect, test } from '@playwright/test'

import { openKiosk, staffLogin } from './helpers'

test('work: join, do a task, get paid for accepted work only, and leave without consequence', async ({
  page,
}) => {
  await openKiosk(page, 'wren', '/resident/jobs')
  const before = await page.getByTestId('tier-label').count() // not on this screen; just a probe
  expect(before).toBe(0)
  const job = page.locator('[data-testid^="job-"]', { hasText: 'Caption educational clips' })
  await job.getByRole('button', { name: 'Join' }).click()
  await expect(job.getByTestId('job-joined')).toBeVisible()
  await expect(page.getByTestId('jobs-pending')).toContainText('$0.00')

  await job.getByRole('button', { name: 'Work' }).click()
  const scene = await page.getByTestId('work-scene').innerText()
  await page.getByLabel('Your answer').fill(scene) // a caption that matches the scene
  await page.getByRole('button', { name: 'Hand in' }).click()
  await expect(page.getByTestId('work-result')).toContainText('Accepted. You earned $0.12.')

  await page.getByRole('button', { name: 'Next task' }).click()
  await page.getByLabel('Your answer').fill('no idea at all')
  await page.getByRole('button', { name: 'Hand in' }).click()
  await expect(page.getByTestId('work-result')).toContainText('did not match the scene')
  await expect(page.getByTestId('work-result')).toHaveAttribute('data-accepted', 'false')

  await page.getByRole('button', { name: 'Next task' }).click()
  await page.getByLabel('Your answer').fill('coins piles 404-555-0134')
  await page.getByRole('button', { name: 'Hand in' }).click()
  await expect(page.getByTestId('work-result')).toContainText('Do not write names, numbers')

  await page.getByRole('button', { name: '← Stop working' }).click()
  await expect(page.getByTestId('jobs-pending')).toContainText('$0.12')
  await expect(page.getByTestId('work-log')).toContainText('Task accepted')
  await expect(page.getByTestId('work-log')).toContainText('Task not accepted')
  await job.getByRole('button', { name: 'Leave' }).click()
  await expect(job.getByRole('button', { name: 'Join' })).toBeVisible()

  // leaving changed nothing about the resident
  await page.goto('/resident')
  await expect(page.getByTestId('tier-label')).toHaveText('Tier 1')
  await expect(page.getByTestId('lock')).toHaveCount(0)
})

test('work: a text-correction task and a labeling task can be handed in', async ({ page }) => {
  await openKiosk(page, 'wren', '/resident/jobs')
  for (const [title, kind] of [
    ['Transcribe public-domain books', 'transcription_public_domain'],
    ['Label sentences', 'labeling_non_personal'],
  ]) {
    const job = page.locator('[data-testid^="job-"]', { hasText: title })
    await expect(job).toBeVisible()
    if (await job.getByRole('button', { name: 'Join' }).count())
      await job.getByRole('button', { name: 'Join' }).click()
    await job.getByRole('button', { name: 'Work' }).click()
    await expect(page.getByTestId('work-task')).toHaveAttribute('data-kind', kind)
    if (kind === 'labeling_non_personal') await page.getByLabel('A question').check()
    await page.getByRole('button', { name: 'Hand in' }).click()
    await expect(page.getByTestId('work-result')).toBeVisible() // accepted or not, it is answered
    await page.getByRole('button', { name: '← Stop working' }).click()
  }
})

test('finance: staff see partner totals without names, and reconciliation passes', async ({
  context,
}) => {
  const sup = await context.newPage()
  await staffLogin(sup, 'e2e_sup1', '/staff/finance')
  const row = sup.getByTestId('partner-CAPTION')
  await expect(row).toBeVisible()
  await expect(sup.getByTestId('partner-dashboard')).not.toContainText('E2E-')
  await expect(sup.getByRole('button', { name: 'Run now' })).toHaveCount(0) // admins only

  const admin = await context.newPage()
  await staffLogin(admin, 'e2e_admin', '/staff/finance')
  await admin.getByRole('button', { name: 'Run now' }).click()
  await expect(admin.getByTestId('notice')).toContainText('every balance matches')
  await expect(admin.getByTestId('ledger-status')).toContainText('all balances match')
  await admin.goto('/staff')
  await expect(admin.getByTestId('ledger-alert')).toHaveCount(0)

  const officer = await context.newPage()
  await staffLogin(officer, 'e2e_officer', '/staff/finance')
  await expect(officer.getByRole('alert')).toContainText('cannot open')
})
