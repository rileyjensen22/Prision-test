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
