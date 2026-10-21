import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import type { Page } from '@playwright/test'

export function token(resident: string): string {
  const f = JSON.parse(readFileSync(join(process.cwd(), 'e2e', '.fixtures.json'), 'utf8'))
  return f.tokens[resident]
}

/** Opens the kiosk the way a staff-provisioned device would: with its device token. */
export async function openKiosk(page: Page, resident: string, path = '/resident') {
  await page.goto(`${path}#device=${token(resident)}`)
}

interface StaffFixtures {
  staff: Record<string, string>
  staff_password: string
}

function fixtures(): StaffFixtures {
  return JSON.parse(readFileSync(join(process.cwd(), 'e2e', '.fixtures.json'), 'utf8'))
}

/** Signs a staff member in on a fresh page (sessionStorage is per tab, so each page is its own session). */
export async function staffLogin(page: Page, username: string, path = '/staff') {
  await page.goto(path)
  await page.getByLabel('Username').fill(username)
  await page.getByLabel('Password').fill(fixtures().staff_password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByTestId('whoami').waitFor()
}

/** Logs in over the API (no browser UI) and returns auth headers, for checking server-side facts. */
export async function apiHeaders(
  request: import('@playwright/test').APIRequestContext,
  username: string,
) {
  const r = await request.post('/api/auth/login', {
    data: { username, password: fixtures().staff_password },
  })
  const { token } = await r.json()
  return { Authorization: `Bearer ${token}` }
}

export interface AuditEntry {
  seq: number
  action: string
  payload: Record<string, unknown>
}

/** Every audit entry, oldest first. One request returns at most 500, so this pages through the log. */
export async function allAuditEntries(
  request: import('@playwright/test').APIRequestContext,
  headers: Record<string, string>,
): Promise<AuditEntry[]> {
  const out: AuditEntry[] = []
  for (;;) {
    const after = out.length ? out[out.length - 1].seq : 0
    const page = (await (
      await request.get(`/api/audit?after_seq=${after}&limit=500`, { headers })
    ).json()) as AuditEntry[]
    if (page.length === 0) return out
    out.push(...page)
  }
}

/** How many audit entries exist, not counting sign-ins (every staff login adds one). */
export async function auditCountExcludingLogins(
  request: import('@playwright/test').APIRequestContext,
  headers: Record<string, string>,
): Promise<number> {
  return (await allAuditEntries(request, headers)).filter((e) => e.action !== 'login').length
}
