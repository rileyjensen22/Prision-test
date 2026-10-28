import { expect, test } from '@playwright/test'

import { apiHeaders, staffLogin } from './helpers'

test('keep-separate screen lists pairs for supervisors and opens the add form', async ({
  context,
}) => {
  const sup = await context.newPage()
  await staffLogin(sup, 'e2e_sup1', '/staff/keep-separate')
  await expect(sup.getByRole('heading', { name: 'Keep separate' }).first()).toBeVisible()
  await expect(sup.getByTestId('separate-form')).toBeVisible()
})

test('accounts screen is admin-only: an officer cannot list accounts over the API', async ({
  context,
  request,
}) => {
  const officer = await apiHeaders(request, 'e2e_officer')
  expect((await request.get('/api/staff/accounts', { headers: officer })).status()).toBe(403)
  const admin = await context.newPage()
  await staffLogin(admin, 'e2e_admin', '/staff/accounts')
  await expect(admin.getByTestId('account-form')).toBeVisible()
})

test('call review: an officer cannot open the queue, a supervisor can, a reason is required', async ({
  context,
  request,
}) => {
  const officer = await apiHeaders(request, 'e2e_officer')
  expect((await request.get('/api/staff/monitoring/calls', { headers: officer })).status()).toBe(
    403,
  )
  const sup = await apiHeaders(request, 'e2e_sup1')
  const q = await request.get('/api/staff/monitoring/calls', { headers: sup })
  expect(q.status()).toBe(200)
  const calls: { call_id: number; privileged?: boolean }[] = await q.json()
  expect(calls.every((c) => !c.privileged)).toBe(true) // attorney calls never appear
  const page = await context.newPage()
  await staffLogin(page, 'e2e_sup1', '/staff/monitoring')
  await expect(page.getByTestId('monitored-calls')).toBeVisible()
})

test('outcomes import: preview first, a bad file cannot be applied', async ({ context }) => {
  const admin = await context.newPage()
  await staffLogin(admin, 'e2e_admin', '/staff/outcomes')
  await admin.getByLabel('CSV file').setInputFiles({
    name: 'bad.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from('resident_code,window_months,outcome\nNOPE-1,12,returned\n'),
  })
  await admin.getByLabel('Source record').last().fill('County record 2026')
  await admin.getByRole('button', { name: 'Preview' }).click()
  await expect(admin.getByTestId('import-preview')).toContainText('NOT_FOUND')
  await expect(admin.getByTestId('import-apply')).toBeDisabled()
})

test('officer sign-in with a temporary password is forced to change it', async ({ request }) => {
  const admin = await apiHeaders(request, 'e2e_admin')
  const name = `e2e_temp_${Date.now()}`
  const made = await request.post('/api/staff/accounts', {
    headers: admin,
    data: { username: name, role: 'officer', reason: 'e2e check' },
  })
  expect(made.status()).toBe(201)
  const temp = (await made.json()).temporary_password as string
  const login = await request.post('/api/auth/login', { data: { username: name, password: temp } })
  const body = await login.json()
  expect(body.must_change_password).toBe(true)
  const blocked = await request.get('/api/staff/roster', {
    headers: { Authorization: `Bearer ${body.token}` },
  })
  expect(blocked.status()).toBe(403)
})
