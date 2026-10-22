import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

import { apiHeaders, openKiosk, staffLogin, token } from './helpers'

/** A stand-in camera: a moving picture that the test can "cover", and a record of every track. */
async function fakeCamera(page: Page) {
  await page.addInitScript(() => {
    const canvas = document.createElement('canvas')
    canvas.width = 320
    canvas.height = 240
    const ctx = canvas.getContext('2d')!
    let covered = false
    let t = 0
    const draw = () => {
      t += 1
      if (covered) {
        ctx.fillStyle = '#000'
        ctx.fillRect(0, 0, 320, 240)
      } else {
        for (let i = 0; i < 20; i++) {
          ctx.fillStyle = `hsl(${(t * 5 + i * 18) % 360} 70% 50%)`
          ctx.fillRect(i * 16, 0, 16, 240)
        }
        ctx.fillStyle = '#fff'
        ctx.fillRect((t * 4) % 300, 100, 20, 20)
      }
      requestAnimationFrame(draw)
    }
    draw()
    const w = window as unknown as Record<string, unknown>
    w.__tracks = [] as MediaStreamTrack[]
    w.__cam = { cover: () => (covered = true), uncover: () => (covered = false) }
    navigator.mediaDevices.getUserMedia = async () => {
      const stream = canvas.captureStream(15)
      stream.getTracks().forEach((tr) => (w.__tracks as MediaStreamTrack[]).push(tr))
      return stream
    }
  })
}

const trackStates = (page: Page) =>
  page.evaluate(() =>
    ((window as unknown as { __tracks: MediaStreamTrack[] }).__tracks ?? []).map(
      (tr) => tr.readyState,
    ),
  )

test('contacts: a resident asks, an officer approves, and then it can be used', async ({
  page,
  context,
}) => {
  await openKiosk(page, 'nia', '/resident/feature/contact_requests')
  await page.getByLabel('Name').fill('Sam Rivera')
  await page.getByLabel('Who is this?').selectOption('friend')
  await page.getByLabel('Phone number').fill('555-0142')
  await page.getByRole('button', { name: 'Send request' }).click()
  await expect(page.getByTestId('contact-message')).toContainText('Your request was sent')
  await expect(page.locator('[data-status="pending"]')).toContainText('Waiting for staff')
  // while it is waiting, it is not on the text list
  await page.goto('/resident/feature/texting')
  await expect(page.getByText('No approved contacts yet.')).toBeVisible()

  const staff = await context.newPage()
  await staffLogin(staff, 'e2e_officer', '/staff/contacts')
  const row = staff.locator('tr', { hasText: 'Sam Rivera' })
  await expect(row).toContainText('Number checked (stub)')
  await row.getByRole('button', { name: 'Approve' }).click()
  await expect(staff.getByTestId('notice')).toContainText('Approved')

  await page.goto('/resident/feature/contact_requests')
  await expect(page.locator('[data-status="approved"]')).toContainText('Sam Rivera')
  await page.goto('/resident/feature/texting')
  await expect(page.getByTestId('text-contact-friend')).toBeVisible()
})

test('contacts: refusing needs a reason, and attorney requests need a supervisor', async ({
  page,
  context,
}) => {
  await openKiosk(page, 'nia', '/resident/feature/contact_requests')
  await page.getByLabel('Name').fill('Dana Cole')
  await page.getByLabel('Who is this?').selectOption('attorney')
  await page.getByLabel('Phone number').fill('555-0143')
  await page.getByRole('button', { name: 'Send request' }).click()
  await expect(page.getByTestId('contact-message')).toContainText('Your request was sent')

  const officer = await context.newPage()
  await staffLogin(officer, 'e2e_officer', '/staff/contacts')
  const row = officer.locator('tr', { hasText: 'Dana Cole' })
  await expect(row).toContainText('A supervisor must review this')

  const sup = await context.newPage()
  await staffLogin(sup, 'e2e_sup1', '/staff/contacts')
  const srow = sup.locator('tr', { hasText: 'Dana Cole' })
  await srow.getByRole('button', { name: 'Refuse' }).click()
  await expect(sup.getByTestId('notice')).toContainText('say why')
  await srow.getByLabel(/Note for request/).fill('bar number could not be confirmed')
  await srow.getByRole('button', { name: 'Refuse' }).click()
  await expect(sup.getByTestId('notice')).toContainText('Refused')

  await page.reload()
  await expect(page.locator('[data-status="rejected"]')).toContainText(
    'bar number could not be confirmed',
  )
})

test('texting: delivery shown, flags are review items, reading needs a reason, attorney text is unreadable', async ({
  page,
  context,
  request,
}) => {
  await openKiosk(page, 'ola', '/resident/feature/texting')
  await page.getByTestId('text-contact-family').click()
  await page.getByPlaceholder('Write a message').fill('we talked about demo contraband earlier')
  await page.getByRole('button', { name: 'Send' }).click()
  await expect(page.getByTestId('delivery').first()).toHaveAttribute('data-state', 'delivered')
  await expect(page.getByTestId('delivery').first()).toContainText('delivered')
  await page.getByRole('button', { name: /^←/ }).click()
  await page.getByTestId('text-contact-attorney').click()
  await page
    .getByPlaceholder('Write a message')
    .fill('attorney only words about my demo contraband case')
  await page.getByRole('button', { name: 'Send' }).click()
  await expect(page.getByTestId('text-notice')).toContainText('Private attorney messages')

  // the flag did not sanction or lock anything
  await page.goto('/resident')
  await expect(page.getByTestId('lock')).toHaveCount(0)

  const sup = await context.newPage()
  await staffLogin(sup, 'e2e_sup1', '/staff/monitoring')
  const table = sup.getByTestId('monitored-messages')
  await expect(table).toContainText('Possible contraband mention')
  await expect(table).not.toContainText('attorney') // metadata only; attorney texts never listed
  await expect(sup.locator('body')).not.toContainText('attorney only words')
  const row = sup.locator('tr', { hasText: 'E2E-OLA' }).first()
  await row.getByRole('button', { name: 'Read' }).click()
  await expect(sup.getByTestId('notice')).toContainText('state why')
  await sup.getByLabel('Reason for reading').fill('checking a keyword flag')
  await row.getByRole('button', { name: 'Read' }).click()
  await expect(sup.getByTestId('opened-body')).toContainText('demo contraband earlier')
  await sup.getByLabel('Reason for outcome').fill('ordinary conversation, no concern')
  await sup.getByRole('button', { name: 'No action needed' }).click()
  await expect(sup.getByTestId('notice')).toContainText('Recorded')

  // an officer cannot open the page at all, and the audit log has the reason but not the words
  const officer = await context.newPage()
  await staffLogin(officer, 'e2e_officer', '/staff/monitoring')
  await expect(officer.getByRole('alert')).toContainText('cannot open')
  const auditor = await apiHeaders(request, 'e2e_auditor')
  const log = await (await request.get('/api/audit?limit=500', { headers: auditor })).json()
  const entries = (Array.isArray(log) ? log : log.entries).filter(
    (e: { action: string }) => e.action === 'monitoring_access',
  )
  expect(entries.length).toBeGreaterThan(0)
  expect(JSON.stringify(entries)).toContain('checking a keyword flag')
  expect(JSON.stringify(log)).not.toContain('demo contraband')
  expect(JSON.stringify(log)).not.toContain('attorney only words')
})

test('video: the camera is on only during the call, loops back on the device, and sends no picture', async ({
  page,
}) => {
  await fakeCamera(page)
  const sent: string[] = []
  page.on('request', (r) => {
    if (r.url().includes('/api/') && r.method() !== 'GET') sent.push(r.postData() ?? '')
  })
  await openKiosk(page, 'rae', '/resident/feature/video')
  expect(await trackStates(page)).toEqual([]) // nothing has opened the camera yet
  await page
    .getByTestId('video-contact-family')
    .getByRole('button', { name: 'Start video call' })
    .click()
  await expect(page.getByTestId('video-call-notice')).toContainText('may be monitored')
  await expect(page.getByTestId('video-timer')).toBeVisible()
  // the loopback "other party" is live: the remote picture has a size
  await expect
    .poll(() => page.getByTestId('video-remote').evaluate((v: HTMLVideoElement) => v.videoWidth))
    .toBeGreaterThan(0)
  expect(await trackStates(page)).toContain('live')

  await page.getByRole('button', { name: 'End call' }).click()
  await expect(page.getByTestId('video-notice')).toContainText('Video call ended')
  const after = await trackStates(page)
  expect(after.length).toBeGreaterThan(0)
  expect(after.every((s) => s === 'ended')).toBe(true) // camera off
  // everything the device posted was tiny JSON (a call id or a contact id); no picture or file
  expect(sent.every((body) => body.length < 100 && !body.includes('data:'))).toBe(true)
})

test('video: attorney calls are private', async ({ page }) => {
  await fakeCamera(page)
  await openKiosk(page, 'rae', '/resident/feature/video')
  await page
    .getByTestId('video-contact-attorney')
    .getByRole('button', { name: 'Start video call' })
    .click()
  await expect(page.getByTestId('video-call-notice')).toContainText('not recorded or listened to')
  await page.getByRole('button', { name: 'End call' }).click()
  await expect(page.getByTestId('video-notice')).toContainText('Video call ended')
})

test('video: a covered camera ends the call, the camera goes off, and a supervisor decides', async ({
  page,
  context,
}) => {
  await fakeCamera(page)
  const bodies: string[] = []
  page.on('request', (r) => {
    if (r.url().includes('/tamper')) bodies.push(r.postData() ?? '')
  })
  await openKiosk(page, 'rae', '/resident/feature/video')
  await page
    .getByTestId('video-contact-family')
    .getByRole('button', { name: 'Start video call' })
    .click()
  await expect(page.getByTestId('video-timer')).toBeVisible()
  await page.evaluate(() => (window as unknown as { __cam: { cover: () => void } }).__cam.cover())
  await expect(page.getByTestId('video-tamper')).toContainText('camera looked covered', {
    timeout: 15_000,
  })
  const after = await trackStates(page)
  expect(after.length).toBeGreaterThan(0)
  expect(after.every((s) => s === 'ended')).toBe(true)
  expect(bodies).toHaveLength(1)
  const sent = JSON.parse(bodies[0])
  expect(Object.keys(sent).sort()).toEqual(['covered_ms', 'signal']) // a signal, never a picture
  expect(['dark', 'flat']).toContain(sent.signal)

  const kiosk = await context.newPage()
  await openKiosk(kiosk, 'rae')
  await expect(kiosk.getByTestId('lock')).toHaveCount(0) // a person must confirm first
  const sup = await context.newPage()
  await staffLogin(sup, 'e2e_sup2', '/staff/confirmations')
  const row = sup.locator('[data-testid^="pending-"]', { hasText: 'E2E-RAE' })
  await expect(row).toContainText('DEVICE_TAMPER')
  await expect(row).toContainText('System event video-call-')
})

test('video: schedule, list and cancel a call', async ({ page }) => {
  await fakeCamera(page)
  await openKiosk(page, 'rae', '/resident/feature/video')
  await page.getByRole('tab', { name: 'Schedule' }).click()
  await expect(page.getByTestId('no-bookings')).toBeVisible()
  await page.getByLabel('Time').selectOption('10:00')
  await page.getByLabel('Length').selectOption('15')
  await page.getByRole('button', { name: 'Book this call' }).click()
  await expect(page.locator('[data-testid^="booking-"]').first()).toBeVisible()
  await page.getByRole('button', { name: 'Start video call' }).click() // far too early
  await expect(page.getByTestId('video-notice')).toContainText('not time for this call yet')
  await page.getByRole('button', { name: 'Cancel' }).click()
  await expect(page.getByTestId('no-bookings')).toBeVisible()
  expect(token('rae')).toBeTruthy()
})
