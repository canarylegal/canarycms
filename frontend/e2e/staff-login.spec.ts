import { expect, test } from '@playwright/test'

/**
 * Staff: password login reaches the main-menu shell.
 * Env: E2E_STAFF_EMAIL, E2E_STAFF_PASSWORD (master admin with 2FA off is fine).
 */
test('staff login reaches main menu', async ({ page }) => {
  const email = process.env.E2E_STAFF_EMAIL?.trim()
  const password = process.env.E2E_STAFF_PASSWORD?.trim()
  test.skip(!email || !password, 'Set E2E_STAFF_EMAIL and E2E_STAFF_PASSWORD')

  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible()

  await page.getByLabel('Email address').fill(email!)
  await page.getByLabel('Password', { exact: true }).fill(password!)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()

  // Authenticated shell: firm main menu, or master recovery console.
  await expect(page.locator('.loginCard')).toHaveCount(0, { timeout: 30_000 })
  await expect(
    page.getByText('Master recovery').or(page.locator('.mainMenuShell')).first(),
  ).toBeVisible({ timeout: 30_000 })
})

/**
 * Optional deeper path: open first matter row and land on the case view (docs panel host).
 * Needs a firm staff account (not master recovery) and at least one matter.
 */
test('staff can open a matter from the main menu', async ({ page }) => {
  const email = process.env.E2E_STAFF_EMAIL?.trim()
  const password = process.env.E2E_STAFF_PASSWORD?.trim()
  test.skip(!email || !password, 'Set E2E_STAFF_EMAIL and E2E_STAFF_PASSWORD')

  await page.goto('/')
  await page.getByLabel('Email address').fill(email!)
  await page.getByLabel('Password', { exact: true }).fill(password!)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.locator('.loginCard')).toHaveCount(0, { timeout: 30_000 })

  if (await page.getByText('Master recovery').isVisible().catch(() => false)) {
    test.skip(true, 'Master recovery has no matter main menu — use a firm staff account')
  }

  // Matters list host (not quote/fee-scale shells — those also use mainMenuShell).
  const casesHost = page.locator('.mainMenuCasesHost:not(.mainMenuCasesHost--hidden)')
  await expect(casesHost).toBeVisible({ timeout: 30_000 })

  const matterRow = casesHost.locator('.tr.rowbtn').first()
  const hasMatter = await matterRow.isVisible().catch(() => false)
  test.skip(!hasMatter, 'No matters in main menu (seed a case or run portal fixture)')

  // Single click only focuses the row; open requires double-click (or context menu Open).
  await matterRow.dblclick()
  await expect(page.locator('.caseShell')).toBeVisible({ timeout: 30_000 })
  await expect(page.locator('.caseDocsCard, .caseDocsScroll').first()).toBeVisible({
    timeout: 30_000,
  })
})
