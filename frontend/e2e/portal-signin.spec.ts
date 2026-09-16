import { expect, test } from '@playwright/test'

/** Portal: sign-in chrome renders (access code + e-mail OTP tabs). */
test('portal sign-in page loads', async ({ page }) => {
  await page.goto('/portal')
  await expect(page.getByRole('button', { name: 'Access code' })).toBeVisible({ timeout: 30_000 })
  await expect(page.getByRole('button', { name: 'E-mail code' })).toBeVisible()
  await expect(page.getByText(/Sign in with your access code/i)).toBeVisible()
})
