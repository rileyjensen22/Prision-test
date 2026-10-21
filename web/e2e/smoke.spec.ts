import { expect, test } from '@playwright/test'

test('resident kiosk shows Request staff', async ({ page }) => {
  await page.goto('/resident')
  await expect(page.getByRole('button', { name: 'Request staff' })).toBeVisible()
})
