import { expect, test } from '@playwright/test'

import { apiHeaders, openKiosk, staffLogin, token } from './helpers'

test('chess against the computer works with no connection', async ({ context, page }) => {
  await openKiosk(page, 'cha', '/resident/feature/chess')
  await page.getByTestId('level-1').click()
  await page.getByTestId('play-engine').click()
  await expect(page.getByTestId('chess-status')).toHaveText('Your move')
  await context.setOffline(true)
  await page.getByTestId('sq-e2').click()
  await page.getByTestId('sq-e4').click()
  await expect(page.getByLabel('white pawn on e4')).toBeVisible()
  await expect(page.getByTestId('chess-status')).toHaveText('Your move', { timeout: 10_000 })
  await context.setOffline(false)
})

test('two residents on different lines are paired, see only handles, and play', async ({
  context,
  request,
}) => {
  const a = await context.newPage()
  const b = await context.newPage()
  await openKiosk(a, 'cha', '/resident/feature/chess_human')
  await a.getByTestId('play-human').click()
  await expect(a.getByTestId('chess-status')).toContainText('Waiting for another player')
  await openKiosk(b, 'chb', '/resident/feature/chess_human')
  await b.getByTestId('play-human').click()
  await expect(b.getByTestId('handles')).toBeVisible()
  await expect(a.getByTestId('handles')).toBeVisible({ timeout: 10_000 })
  const names =
    (await a.getByTestId('handles').innerText()) + (await b.getByTestId('handles').innerText())
  expect(names).not.toMatch(/E2E-/) // never a code or a name
  expect(await a.locator('input, textarea').count()).toBe(0) // nothing to type into

  await a.getByTestId('sq-e2').click()
  await a.getByTestId('sq-e4').click()
  await expect(b.getByLabel('white pawn on e4')).toBeVisible({ timeout: 10_000 })
  await expect(b.getByTestId('chess-status')).toHaveText('Your move')

  const sup = await apiHeaders(request, 'e2e_sup1')
  const log = await (await request.get('/api/staff/chess/matches', { headers: sup })).json()
  const row = log.find((m: { white: string }) => m.white === 'E2E-CHA')
  expect(row.black).toBe('E2E-CHB')
  expect(row.plies).toBeGreaterThanOrEqual(1)

  await b.getByTestId('resign').click() // leaving costs nothing
  await expect(b.getByTestId('chess-status')).toContainText('You lost')
  await expect(a.getByTestId('chess-status')).toContainText('You won', { timeout: 10_000 })
})

test('staff can switch human chess off for one resident, and the engine stays open', async ({
  request,
}) => {
  const sup = await apiHeaders(request, 'e2e_sup1')
  const roster = await (await request.get('/api/staff/roster', { headers: sup })).json()
  const chb = roster.find((r: { code: string }) => r.code === 'E2E-CHB')
  const put = (human: boolean | null) =>
    request.put(`/api/staff/residents/${chb.resident_id}/chess`, {
      headers: sup,
      data: { human, reason: 'e2e check' },
    })
  expect((await put(false)).status()).toBe(200)
  const device = { 'X-Device-Token': token('chb') }
  const human = await request.post('/api/device/chess', {
    headers: device,
    data: { opponent: 'human' },
  })
  expect(human.status()).toBe(409)
  expect((await human.json()).detail.code).toBe('FEATURE_LOCKED')
  const engine = await request.post('/api/device/chess', {
    headers: device,
    data: { opponent: 'engine', level: 1 },
  })
  expect(engine.status()).toBe(201)
  expect((await put(null)).status()).toBe(200)
})

test('the match log page lists games for supervisors', async ({ context }) => {
  const sup = await context.newPage()
  await staffLogin(sup, 'e2e_sup1', '/staff/chess')
  await expect(sup.getByRole('heading', { name: 'Match log' })).toBeVisible()
})
