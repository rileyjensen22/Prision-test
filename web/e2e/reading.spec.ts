import { expect, test } from '@playwright/test'

import { openKiosk } from './helpers'

test('reader: text size, bookmarks and progress survive leaving and coming back', async ({
  page,
}) => {
  await openKiosk(page, 'fay', '/resident/feature/reading_general')
  await page.getByTestId('reading-tortoise-hare').getByRole('button', { name: 'Read' }).click()
  await expect(page.getByTestId('reading-position')).toHaveText('Page 1 of 1')
  await expect(page.getByTestId('reading-finished')).toBeVisible()

  const text = page.getByTestId('reading-page-text')
  await expect(text).toHaveAttribute('data-scale', '1')
  await page.getByRole('button', { name: 'Larger text' }).click()
  await expect(text).toHaveAttribute('data-scale', '1.25')
  await page.getByRole('button', { name: 'Smaller text' }).click()
  await expect(text).toHaveAttribute('data-scale', '1')

  await page.getByRole('button', { name: 'Back to the list' }).click()
  await expect(page.getByTestId('reading-progress-tortoise-hare')).toHaveText('Finished')
})

test('reader: multi-page text, bookmark, resume where you left off', async ({ page }) => {
  await openKiosk(page, 'ivy', '/resident/feature/reading_general')
  const row = page.getByTestId('reading-psalm-23')
  await expect(row).toHaveAttribute('data-allowed', 'true') // baseline: open for everyone
  await row.getByRole('button', { name: 'Read' }).click()
  await expect(page.getByTestId('reading-position')).toHaveText('Page 1 of 3')
  await page.getByRole('button', { name: 'Next page' }).click()
  await page.getByRole('button', { name: 'Bookmark this page' }).click()
  await expect(page.getByRole('button', { name: 'Remove bookmark' })).toBeVisible()
  await page.getByRole('button', { name: 'Back to the list' }).click()
  await expect(page.getByTestId('reading-progress-psalm-23')).toContainText('Page 2 of 3')
  await expect(page.getByTestId('reading-progress-psalm-23')).toContainText('1 bookmark')

  await page.reload() // the server has it, not just this page
  await page.getByTestId('reading-psalm-23').getByRole('button', { name: 'Continue' }).click()
  await expect(page.getByTestId('reading-position')).toHaveText('Page 2 of 3')
  await expect(page.getByRole('button', { name: 'Remove bookmark' })).toBeVisible()
  await page.getByRole('button', { name: 'Next page' }).click()
  await expect(page.getByTestId('reading-finished')).toBeVisible()
})

test('a sanction locks general reading but never the legal and religious texts', async ({
  page,
}) => {
  await openKiosk(page, 'lee', '/resident/feature/reading_general')
  await expect(page.getByTestId('reading-tortoise-hare')).toHaveAttribute('data-allowed', 'false')
  await expect(page.getByTestId('reading-tortoise-hare')).toContainText('🔒')
  await expect(page.getByTestId('reading-preamble')).toHaveAttribute('data-allowed', 'false')
  for (const id of ['bill-of-rights-selected', 'psalm-23', 'dhammapada-twin-verses'])
    await expect(page.getByTestId(`reading-${id}`)).toHaveAttribute('data-allowed', 'true')
  await page
    .getByTestId('reading-bill-of-rights-selected')
    .getByRole('button', { name: 'Read' })
    .click()
  await expect(page.getByTestId('reading-text')).toContainText('Fourth Amendment')
})

test('offline: saved texts still open, unsaved ones do not, and a lock still applies', async ({
  page,
  context,
}) => {
  await page.clock.install()
  await openKiosk(page, 'tess', '/resident/feature/reading_general')
  await page.getByTestId('reading-lion-mouse').getByRole('button', { name: 'Read' }).click()
  await expect(page.getByTestId('reading-text')).toContainText('The Lion and the Mouse')
  await page.getByRole('button', { name: 'Back to the list' }).click()

  await context.setOffline(true)
  await page.clock.fastForward('00:40') // the next poll fails, so the device knows it is offline
  await expect(page.getByTestId('reading-offline')).toBeVisible()
  await expect(page.getByTestId('reading-lion-mouse')).toHaveAttribute('data-allowed', 'true')
  await expect(page.getByTestId('reading-tortoise-hare')).toHaveAttribute('data-allowed', 'false')
  await expect(page.getByTestId('reading-tortoise-hare')).toContainText('not saved')
  await page.getByTestId('reading-lion-mouse').getByRole('button', { name: 'Read' }).click()
  await expect(page.getByTestId('reading-text')).toContainText('The Lion and the Mouse')
  await context.setOffline(false)
})
