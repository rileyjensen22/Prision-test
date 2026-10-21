import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import type { Page } from '@playwright/test'

export function token(resident: string): string {
  const f = JSON.parse(readFileSync(join(process.cwd(), 'e2e', '.fixtures.json'), 'utf8'))
  return f.tokens[resident]
}

/** Opens the kiosk the way a staff-provisioned device would: with its device token. */
export async function openKiosk(page: Page, resident: string, path = '/resident') {
  await page.goto(`${path}?device=${token(resident)}`)
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
