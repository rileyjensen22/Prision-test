import { expect, test } from '@playwright/test'

import { openKiosk } from './helpers'

test('locks show a reason, an end time and a way to appeal; baseline and Request staff stay available', async ({
  page,
}) => {
  await openKiosk(page, 'alice')
  await expect(page.getByTestId('tier-label')).toHaveText('Tier 3')

  const lock = page.getByTestId('lock')
  await expect(lock).toHaveCount(1)
  await expect(lock.getByTestId('lock-title')).toHaveText('Disruptive behavior')
  const until = await lock.getByTestId('lock-until').locator('time').getAttribute('datetime')
  const hoursLeft = (Date.parse(until!) - Date.now()) / 3_600_000
  expect(hoursLeft).toBeGreaterThan(21)
  expect(hoursLeft).toBeLessThan(24)
  await expect(lock.getByRole('link', { name: 'Appeal' })).toBeVisible()

  for (const f of ['calls', 'texting', 'video'])
    await expect(page.getByTestId(`tile-${f}`)).toHaveAttribute('data-allowed', 'false')
  await expect(page.getByTestId('tile-commissary')).toHaveAttribute('data-allowed', 'true')
  for (const f of [
    'attorney_calls',
    'legal_materials',
    'grievances_appeals',
    'medical_requests',
    'basic_education',
  ])
    await expect(page.getByTestId(`tile-${f}`)).toHaveAttribute('data-allowed', 'true')
  await expect(page.getByRole('button', { name: 'Request staff' })).toBeEnabled()

  // "Why is this locked?" from a locked tile
  await page.getByTestId('tile-calls').click()
  await expect(page.getByTestId('reason-title')).toHaveText('Disruptive behavior')
  await expect(page.getByTestId('reason-until').locator('time')).toHaveAttribute('datetime', until!)
  await expect(page.getByTestId('reason-how')).toContainText('Press Appeal')
})

test('tier-locked features explain what unlocks them', async ({ page }) => {
  await openKiosk(page, 'fay')
  await expect(page.getByTestId('tile-reason-texting')).toHaveText('Unlocks at Tier 4')
  await page.getByTestId('tile-texting').click()
  await expect(page.getByTestId('reason-title')).toHaveText('Unlocks at Tier 4')
  await expect(page.getByTestId('reason-how')).toContainText('Request staff')
})

test('Spanish resident sees Spanish throughout', async ({ page }) => {
  await openKiosk(page, 'benito')
  await expect(page.getByTestId('tier-label')).toHaveText('Nivel 1')
  await expect(page.getByRole('button', { name: 'Solicitar personal' })).toBeVisible()
  await expect(page.getByTestId('lock-title')).toHaveText('Limpieza de la celda')
  await expect(page.getByTestId('tile-commissary')).toContainText('Bloqueado')
})

test('repeat-return ceiling is shown with its reason', async ({ page }) => {
  await openKiosk(page, 'carla')
  await expect(page.getByTestId('tier-label')).toHaveText('Tier 2')
  await expect(page.getByTestId('next-tier')).toContainText('highest available tier is 2')
  await page.getByRole('link', { name: 'Tier details' }).click()
  await expect(page.getByTestId('ceiling-title')).toHaveText('Your highest available tier is 2')
  await expect(page.getByTestId('ceiling-card')).toContainText('previous returns')
})

test('resident files an appeal from the device', async ({ page }) => {
  await openKiosk(page, 'dan')
  await page.getByTestId('lock').getByRole('link', { name: 'Appeal' }).click()
  await page.getByRole('button', { name: 'Send appeal' }).click()
  await expect(page.getByTestId('appeal-result')).toContainText('Your appeal was sent')
  await page.getByRole('link', { name: 'Back' }).click()
  await expect(page.getByTestId('appeal-sent')).toBeVisible()
})

test('device without a token cannot see anyone', async ({ page }) => {
  await page.goto('/resident')
  await expect(page.getByTestId('status-message')).toContainText('not set up')
})

test('kiosk CSP is present and blocks inline script', async ({ page }) => {
  const violations: string[] = []
  page.on(
    'console',
    (m) => m.text().includes('Content Security Policy') && violations.push(m.text()),
  )
  await openKiosk(page, 'fay')
  const csp = await page
    .locator('meta[http-equiv="Content-Security-Policy"]')
    .getAttribute('content')
  expect(csp).toContain("default-src 'self'")
  expect(csp).toContain("connect-src 'self'")
  await page.evaluate(() => {
    const s = document.createElement('script')
    s.textContent = 'window.__injected = true'
    document.head.appendChild(s)
  })
  expect(
    await page.evaluate(() => (window as unknown as { __injected?: boolean }).__injected),
  ).toBeUndefined()
  expect(violations.length).toBeGreaterThan(0)
})

test('returns to home after inactivity', async ({ page }) => {
  await page.clock.install()
  await openKiosk(page, 'fay')
  await page.getByRole('link', { name: 'Tier details' }).click()
  await expect(page).toHaveURL(/\/resident\/tier$/)
  await page.clock.fastForward('01:35')
  await expect(page).toHaveURL(/\/resident$/)
})

test.describe('offline', () => {
  test('locks still apply offline, and fail closed once the cached snapshot expires', async ({
    page,
    context,
  }) => {
    await page.clock.install()
    await openKiosk(page, 'eve')
    await expect(page.getByTestId('lock-title')).toHaveText('Disruptive behavior')
    await expect(page.getByTestId('tile-calls')).toHaveAttribute('data-allowed', 'false')
    await expect(page.getByTestId('tile-commissary')).toHaveAttribute('data-allowed', 'true')

    await context.setOffline(true)
    await page.clock.fastForward('00:40') // poll fails -> offline banner, cache still trusted
    await expect(page.getByTestId('connection-banner')).toContainText('No connection')
    await expect(page.getByTestId('tile-calls')).toHaveAttribute('data-allowed', 'false')
    await expect(page.getByTestId('tile-commissary')).toHaveAttribute('data-allowed', 'true')

    // The sanction ended 20 minutes in; the device cannot know that is still true, so it pauses features.
    await page.clock.fastForward('25:00')
    await expect(page.getByTestId('connection-banner')).toContainText('out of date')
    await expect(page.getByTestId('tile-commissary')).toHaveAttribute('data-allowed', 'false')
    await expect(page.getByTestId('tile-reason-commissary')).toHaveText(
      'Paused until the connection returns',
    )
    await expect(page.getByTestId('tile-legal_materials')).toHaveAttribute('data-allowed', 'true')
    await expect(page.getByTestId('tile-attorney_calls')).toHaveAttribute('data-allowed', 'true')
    await expect(page.getByRole('button', { name: 'Request staff' })).toBeEnabled()

    // Back online: a fresh snapshot arrives from the server, whose clock is the authority.
    await context.setOffline(false)
    await page.clock.fastForward('00:40')
    await expect(page.getByTestId('connection-banner')).toHaveCount(0)
    await expect(page.getByTestId('tile-commissary')).toHaveAttribute('data-allowed', 'true')
    await expect(page.getByTestId('tile-calls')).toHaveAttribute('data-allowed', 'false') // server says still locked
    await expect(page.getByTestId('lock-title')).toHaveText('Disruptive behavior')
  })

  test('Request staff works offline and is delivered when the connection returns', async ({
    page,
    context,
  }) => {
    await page.clock.install()
    await openKiosk(page, 'fay')
    await expect(page.getByTestId('tier-label')).toBeVisible()
    await context.setOffline(true)
    await page.getByRole('button', { name: 'Request staff' }).click()
    await page.getByRole('button', { name: 'Medical help' }).click()
    await expect(page.getByTestId('request-result')).toContainText('will be sent')
    await page.getByRole('button', { name: 'Close' }).click()
    await expect(page.getByTestId('pending-count')).toBeVisible()

    await context.setOffline(false)
    await page.clock.fastForward('00:40')
    await expect(page.getByTestId('pending-count')).toHaveCount(0)
  })
})
