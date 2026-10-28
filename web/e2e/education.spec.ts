import { expect, test } from '@playwright/test'

import { answerQuiz, openKiosk, staffLogin } from './helpers'

test('prerequisites say what to finish first; a pass earns a certificate staff can print', async ({
  page,
  browser,
}) => {
  await openKiosk(page, 'ned', '/resident/feature/basic_education')
  const first = page.getByTestId('course-LIT101')
  await expect(first).toHaveAttribute('data-allowed', 'true')
  await first.getByRole('button', { name: 'Start' }).click()
  const lessons = await page.getByTestId('lesson').innerText()
  const total = Number(/of (\d+)/.exec(lessons)?.[1])
  for (let i = 0; i < total - 1; i++) await page.getByRole('button', { name: 'Next' }).click()
  await page.getByRole('button', { name: 'Take the quiz' }).click()
  await page.getByTestId('begin-quiz').click()
  await answerQuiz(page, 'LIT101')
  await page.getByRole('button', { name: 'Submit answers' }).click()
  await expect(page.getByTestId('quiz-result')).toContainText('You passed!')
  await page.getByTestId('certificate-link').click()
  await expect(page.getByText('Certificate of completion')).toBeVisible()

  const staff = await browser.newPage()
  await staffLogin(staff, 'e2e_officer')
  await staff.goto('/staff/roster')
  await staff.getByRole('link', { name: /ned/i }).first().click()
  await staff.getByRole('link', { name: 'Certificates' }).click()
  await expect(staff.getByTestId('certificate-LIT101')).toContainText('LIT101-')
})

test('progress survives going offline in the middle of a lesson', async ({ page, context }) => {
  await openKiosk(page, 'pam', '/resident/feature/basic_education')
  await page.getByTestId('course-LIT101').getByRole('button', { name: 'Start' }).click()
  await expect(page.getByTestId('lesson')).toContainText('Lesson 1 of')
  await page.getByRole('button', { name: 'Next' }).click()
  await expect(page.getByTestId('lesson')).toContainText('Lesson 2 of')

  await context.setOffline(true)
  await page.getByRole('button', { name: 'Next' }).click() // finished offline: saved here, queued
  await expect(page.getByTestId('lesson')).toContainText('Lesson 3 of')

  await context.setOffline(false)
  // Let the queue drain on its own: reloading the page every few seconds would keep interrupting it.
  await expect(page.getByTestId('pending-count')).toHaveCount(0, { timeout: 30_000 })
  await expect(async () => {
    await page.goto('/resident/feature/basic_education')
    await expect(page.getByTestId('course-LIT101')).toContainText('2 of 3 lessons', {
      timeout: 3000,
    })
  }).toPass({ timeout: 20_000 })
  await page.getByTestId('course-LIT101').getByRole('button', { name: 'Continue' }).click()
  await expect(page.getByTestId('lesson')).toContainText('Lesson 3 of') // resumes where they left off
})
