import { expect, test } from '@playwright/test'
import { login } from './core-helpers'

test('staff signs in, opens a matter from its row, and signs out', async ({ page }) => {
  await login(page)
  const row = page.getByRole('row').filter({ hasText: '900001' })
  await row.focus()
  await row.click({ button: 'right' })
  await expect(page.getByRole('menuitem', { name: 'Open', exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(row).toBeFocused()
  await page.screenshot({ path: test.info().outputPath('matters.png') })
  await row.dblclick()
  await expect(page.getByRole('heading', { name: 'CI Core Workflows', exact: true })).toBeVisible()
  await expect(page.getByRole('toolbar', { name: 'Documents actions' })).toBeVisible()
  await page.getByRole('button', { name: 'Sign out', exact: true }).click()
  const logout = page.waitForResponse((response) => response.url().endsWith('/api/auth/logout') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Sign out', exact: true }).last().click()
  expect((await logout).ok()).toBe(true)
  await expect(page.getByLabel('Email address', { exact: true })).toBeVisible()
  expect((await page.request.get('/api/auth/me')).status()).toBe(401)
})
