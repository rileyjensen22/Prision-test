import { expect, test } from '@playwright/test'

import { answerQuiz, openKiosk } from './helpers'

test('demo loop: finishing the sample course raises tier and call minutes', async ({ page }) => {
  await openKiosk(page, 'gina')
  await expect(page.getByTestId('tier-label')).toHaveText('Tier 1')
  await expect(page.getByTestId('allowance-calls')).toContainText('15 of 15 minutes left')

  await page.getByTestId('tile-basic_education').click()
  await expect(page.getByTestId('course-MONEY101')).toHaveAttribute('data-allowed', 'true')
  await expect(page.getByTestId('course-WORKMATH')).toHaveAttribute('data-allowed', 'false')
  await expect(page.getByTestId('course-WORKMATH')).toContainText('Unlocks at Tier 3')
  await page.getByTestId('course-MONEY101').getByRole('button', { name: 'Start' }).click()

  await expect(page.getByTestId('lesson')).toContainText('Lesson 1 of 3')
  await page.getByRole('button', { name: 'Next' }).click()
  await expect(page.getByTestId('lesson')).toContainText('Lesson 2 of 3')
  await page.getByRole('button', { name: 'Next' }).click()
  await expect(page.getByTestId('lesson')).toContainText('Lesson 3 of 3')
  await page.getByRole('button', { name: 'Take the quiz' }).click()
  await page.getByTestId('begin-quiz').click()

  await expect(page.getByRole('button', { name: 'Submit answers' })).toBeDisabled()
  await answerQuiz(page, 'MONEY101')
  await page.getByRole('button', { name: 'Submit answers' }).click()

  await expect(page.getByTestId('quiz-result')).toContainText('You passed!')
  await expect(page.getByTestId('points-earned')).toHaveText('+50 points earned')
  await expect(page.getByTestId('tier-up')).toHaveText('You moved up: Tier 1 to Tier 2.')
  await expect(page.getByTestId('calls-up')).toHaveText('Phone calls: 15 to 20 minutes per day.')

  await page.getByRole('link', { name: '← Back' }).click()
  await expect(page.getByTestId('tier-label')).toHaveText('Tier 2')
  await expect(page.getByTestId('allowance-calls')).toContainText('20 of 20 minutes left')
})

test('wrong answers earn nothing and can be retried', async ({ page }) => {
  await openKiosk(page, 'fay', '/resident/feature/basic_education')
  await page.getByTestId('course-MONEY101').getByRole('button', { name: 'Start' }).click()
  for (const label of ['Next', 'Next', 'Take the quiz'])
    await page.getByRole('button', { name: label }).click()
  await page.getByTestId('begin-quiz').click()
  await answerQuiz(page, 'MONEY101', 'wrong')
  await page.getByRole('button', { name: 'Submit answers' }).click()
  await expect(page.getByTestId('quiz-result')).toContainText('Not yet')
  await expect(page.getByTestId('points-earned')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Try the quiz again' })).toBeVisible()
})

test('attorney calls are private; other calls say they may be monitored', async ({ page }) => {
  await openKiosk(page, 'ivy', '/resident/feature/calls')
  await expect(page.getByTestId('calls-left')).toContainText('15 minutes left today')

  await page.getByTestId('contact-attorney').getByRole('button', { name: 'Call' }).click()
  await expect(page.getByTestId('call-notice')).toContainText('not recorded')
  await expect(page.getByTestId('call-timer')).toBeVisible()
  await page.getByRole('button', { name: 'End call' }).click()
  await expect(page.getByTestId('call-summary')).toContainText('Call ended')
  await expect(page.getByTestId('calls-left')).toContainText('15 minutes left today') // attorney time is not metered

  await page.getByTestId('contact-family').getByRole('button', { name: 'Call' }).click()
  await expect(page.getByTestId('call-notice')).toContainText('may be monitored and recorded')
  await page.getByRole('button', { name: 'End call' }).click()
  await expect(page.getByTestId('call-summary')).toBeVisible()
})

test('a communication lock stops regular calls on the tile', async ({ page }) => {
  await openKiosk(page, 'alice')
  await page.getByTestId('tile-calls').click() // locked tile goes to the explanation, not the dialer
  await expect(page.getByTestId('reason-title')).toHaveText('Disruptive behavior')
})

test('commissary: balance, limits, item restrictions, and ordering', async ({ page }) => {
  await openKiosk(page, 'hal', '/resident/feature/commissary')
  await expect(page.getByTestId('balance')).toHaveText('Your balance: $50.00')
  await expect(page.getByTestId('weekly')).toHaveText('This week: $20.00 left of $20.00')
  await expect(page.getByTestId('block-SNACK')).toHaveText('Available at a higher tier')
  await expect(page.getByTestId('item-SNACK')).toHaveAttribute('data-available', 'false')

  await page.getByRole('button', { name: 'Add Bar soap' }).click()
  await page.getByRole('button', { name: 'Add Bar soap' }).click()
  await page.getByRole('button', { name: 'Add Writing pad' }).click()
  await expect(page.getByTestId('cart-total')).toHaveText('Total: $4.25')
  await page.getByRole('button', { name: 'Place order' }).click()
  await expect(page.getByTestId('order-message')).toHaveText('Order placed. New balance: $45.75.')
  await expect(page.getByTestId('balance')).toHaveText('Your balance: $45.75')
  await expect(page.getByTestId('weekly')).toHaveText('This week: $15.75 left of $20.00')

  for (let i = 0; i < 3; i++)
    await page.getByRole('button', { name: 'Add Postage stamps (book)' }).click()
  await page.getByRole('button', { name: 'Place order' }).click() // $24.00 > $15.75 left
  await expect(page.getByTestId('order-message')).toHaveText(
    'This order would go over your weekly limit.',
  )
  await expect(page.getByTestId('balance')).toHaveText('Your balance: $45.75')
})

test('commissary lock blocks ordering, in Spanish for a Spanish resident', async ({ page }) => {
  await openKiosk(page, 'benito', '/resident/feature/commissary')
  await expect(page.getByRole('heading', { name: 'Cantina' })).toBeVisible()
  await expect(page.getByTestId('commissary-locked')).toHaveText(
    'La cantina está bloqueada por ahora.',
  )
  await expect(page.getByRole('button', { name: 'Hacer pedido' })).toBeDisabled()
})
