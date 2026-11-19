import { expect, test } from '@playwright/test'
import { login } from './core-helpers'

test('staff signs in, opens a matter with visible controls, and signs out', async ({ page }) => {
  await login(page)
  await page.getByRole('button', { name: 'Actions for matter 900001', exact: true }).click()
  await expect(page.getByRole('menuitem', { name: 'Open', exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: 'Actions for matter 900001', exact: true })).toBeFocused()
  await page.screenshot({ path: test.info().outputPath('matters.png') })
  await page.getByRole('button', { name: 'Open matter 900001', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'CI Core Workflows', exact: true })).toBeVisible()
  await expect(page.getByRole('toolbar', { name: 'Documents actions' })).toBeVisible()
  await page.getByRole('button', { name: 'Sign out', exact: true }).click()
  const logout = page.waitForResponse((response) => response.url().endsWith('/api/auth/logout') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Sign out', exact: true }).last().click()
  expect((await logout).ok()).toBe(true)
  await expect(page.getByLabel('Email address', { exact: true })).toBeVisible()
  expect((await page.request.get('/api/auth/me')).status()).toBe(401)
})
