import { expect, test } from '@playwright/test'
import { caseId, credentials } from './core-helpers'

test('allocation correction survives a lost response and the existing dialog can reallocate', async ({ page }) => {
  await page.goto('/')
  const user = credentials('APPROVER')
  await page.getByLabel('Email address', { exact: true }).fill(user.email)
  await page.getByLabel('Password', { exact: true }).fill(user.password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('button', { name: 'New matter', exact: true })).toBeVisible()
  const id = await caseId(page.request)
  const matter = await (await page.request.get(`/api/cases/${id}`)).json()
  const created = await page.request.post(`/api/cases/${id}/invoices`, { data: {
    credit_user_id: matter.fee_earner_user_id, lines: [{ line_type: 'fee', description: 'Correction test', amount_pence: 10000 }],
  } })
  expect(created.status()).toBe(201)
  const invoice = await created.json()
  const invoiceURL = `/api/cases/${id}/invoices/${invoice.id}`
  expect((await page.request.post(`${invoiceURL}/approve`)).status()).toBe(204)
  const description = `Correction receipt ${Date.now()}`
  expect((await page.request.post(`/api/cases/${id}/ledger/post`, { data: {
    description, amount_pence: 10000, office_direction: 'credit', contact_label: 'N/A',
  } })).status()).toBe(204)
  const ledger = await (await page.request.get(`/api/cases/${id}/ledger`)).json()
  const pair = ledger.entries.find((e: {description: string}) => e.description === description).pair_id
  const allocate = { ledger_pair_id: pair, amount_pence: 10000, idempotency_key: '25cfbf56-e450-4e70-8ced-5173df551101' }
  const allocated = await page.request.post(`${invoiceURL}/allocations`, { data: allocate })
  expect(allocated.status()).toBe(201)
  const original = await allocated.json()
  await page.getByRole('row').filter({ hasText: '900001' }).dblclick()
  await page.locator('button.accHead').filter({ hasText: 'Accounts' }).click()
  await page.getByRole('button', { name: 'Open accounts', exact: true }).click()
  const row = page.getByRole('row').filter({ hasText: invoice.invoice_number })
    .filter({ has: page.getByRole('button', { name: 'Download', exact: true }) })
  await expect(row).toContainText('Paid')
  const reverseURL = `${invoiceURL}/allocations/${original.id}/reverse`
  const correction = { idempotency_key: '25cfbf56-e450-4e70-8ced-5173df551102', reason: 'Synthetic allocation correction' }
  let calls = 0
  await page.route(`**/allocations/${original.id}/reverse`, async route => {
    calls++
    if (calls === 1) {
      expect((await route.fetch()).status()).toBe(200)
      await route.abort('failed')
    } else await route.continue()
  })
  const correct = () => page.evaluate(async ({ url, data }) => {
    try {
      const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
      return { status: response.status, data: await response.json() }
    } catch { return null }
  }, { url: reverseURL, data: correction })
  expect(await correct()).toBeNull()
  const result = await correct()
  expect(result?.status).toBe(200)
  expect(calls).toBe(2)
  const replay = await page.request.post(`${invoiceURL}/allocations`, { data: allocate })
  expect((await replay.json()).reversal.id).toBe(result?.data.id)
  const report = await page.request.get(`${invoiceURL}/allocation-consistency`)
  expect(report.status()).toBe(200)
  expect(await report.json()).toMatchObject({ consistent: true, active_allocated_pence: 0 })
  await page.locator('.ledgerActions').getByRole('button', { name: 'Refresh', exact: true }).click()
  await expect(row.getByRole('button', { name: 'Allocate', exact: true })).toBeVisible()
  await row.getByRole('button', { name: 'Allocate', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: `Allocate — ${invoice.invoice_number}` })
  await dialog.getByLabel('Ledger pair id').fill(pair)
  await dialog.getByLabel('Amount (£)').fill('60')
  await dialog.getByRole('button', { name: 'Allocate', exact: true }).click()
  await expect(dialog).toBeHidden()
  const history = await (await page.request.get(`${invoiceURL}/allocations`)).json()
  expect(history).toHaveLength(2)
  expect(history.find((a: {id: string}) => a.id === original.id).reversal.id).toBe(result?.data.id)
  const active = history.find((a: {reversal: unknown}) => !a.reversal)
  expect(active.amount_pence).toBe(6000)
  expect((await (await page.request.get(`${invoiceURL}/allocation-consistency`)).json()).active_allocated_pence).toBe(6000)
  expect((await page.request.post(reverseURL, { data: { ...correction, idempotency_key: '25cfbf56-e450-4e70-8ced-5173df551103' } })).status()).toBe(409)
  expect((await page.request.delete(invoiceURL)).status()).toBe(409)
  const receiptReverse = `/api/cases/${id}/ledger/pairs/${pair}/reverse`
  const receiptCorrection = { idempotency_key: '25cfbf56-e450-4e70-8ced-5173df551104', reason: 'Synthetic receipt correction' }
  expect((await page.request.post(receiptReverse, { data: receiptCorrection })).status()).toBe(409)
  expect((await page.request.post(`${invoiceURL}/allocations/${active.id}/reverse`, { data: {
    idempotency_key: '25cfbf56-e450-4e70-8ced-5173df551105', reason: 'Synthetic final correction',
  } })).status()).toBe(200)
  expect((await page.request.post(receiptReverse, { data: receiptCorrection })).status()).toBe(200)
  expect((await page.request.delete(invoiceURL)).status()).toBe(204)
  expect((await (await page.request.get(`${invoiceURL}/allocation-consistency`)).json()).consistent).toBe(true)
})
