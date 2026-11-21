import { expect, test } from '@playwright/test'
import { caseId, credentials } from './core-helpers'

test('allocation retry after a lost response pays once without changing the dialog', async ({ page }) => {
  await page.goto('/')
  const user = credentials('APPROVER')
  await page.getByLabel('Email address', { exact: true }).fill(user.email)
  await page.getByLabel('Password', { exact: true }).fill(user.password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('button', { name: 'New matter', exact: true })).toBeVisible()
  const id = await caseId(page.request)
  const matter = await (await page.request.get(`/api/cases/${id}`)).json()
  const created = await page.request.post(`/api/cases/${id}/invoices`, { data: {
    credit_user_id: matter.fee_earner_user_id,
    lines: [{ line_type: 'fee', description: 'Allocation retry test', amount_pence: 10000 }],
  } })
  expect(created.status()).toBe(201)
  const inv = await created.json()
  expect((await page.request.post(`/api/cases/${id}/invoices/${inv.id}/approve`)).status()).toBe(204)
  const description = `Allocation receipt ${Date.now()}`
  expect((await page.request.post(`/api/cases/${id}/ledger/post`, { data: {
    description, amount_pence: 10000, office_direction: 'credit', contact_label: 'N/A',
  } })).status()).toBe(204)
  const ledger = await (await page.request.get(`/api/cases/${id}/ledger`)).json()
  const pair = ledger.entries.find((entry: { description: string }) => entry.description === description).pair_id
  await page.getByRole('row').filter({ hasText: '900001' }).dblclick()
  await page.locator('button.accHead').filter({ hasText: 'Accounts' }).click()
  await page.getByRole('button', { name: 'Open accounts', exact: true }).click()
  await page.getByRole('row').filter({ hasText: inv.invoice_number }).getByRole('button', { name: 'Allocate', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: `Allocate — ${inv.invoice_number}` })
  await dialog.getByLabel('Ledger pair id').fill(pair)
  const keys: string[] = []
  await page.route(`**/invoices/${inv.id}/allocations`, async route => {
    if (route.request().method() !== 'POST') return route.continue()
    keys.push(route.request().postDataJSON().idempotency_key)
    if (keys.length === 1) {
      const response = await route.fetch()
      expect(response.status()).toBe(201)
      await route.abort('failed') // Commit succeeded but the browser lost the response.
    } else await route.continue()
  })
  await dialog.getByRole('button', { name: 'Allocate', exact: true }).click()
  await expect(dialog.locator('.error')).toBeVisible()
  await expect(dialog.getByLabel('Ledger pair id')).toHaveValue(pair)
  await dialog.getByRole('button', { name: 'Allocate', exact: true }).click()
  await expect(dialog).toBeHidden()
  expect(keys).toHaveLength(2)
  expect(keys[0]).toBeTruthy()
  expect(keys[1]).toBe(keys[0])
  const allocations = await (await page.request.get(`/api/cases/${id}/invoices/${inv.id}/allocations`)).json()
  expect(allocations).toHaveLength(1)
  expect(allocations[0].amount_pence).toBe(10000)
  await expect(page.getByRole('row').filter({ hasText: inv.invoice_number })
    .filter({ has: page.getByRole('button', { name: 'Download', exact: true }) })).toContainText('Paid')
})
