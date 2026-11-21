import { expect, test } from '@playwright/test'
import { credentials, caseId } from './core-helpers'

test('bank matching recovers a lost response and audited corrections preserve reconciliation', async ({ page }) => {
  await page.goto('/')
  const user = credentials('APPROVER')
  await page.getByLabel('Email address', { exact: true }).fill(user.email)
  await page.getByLabel('Password', { exact: true }).fill(user.password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Sign out', exact: true })).toBeVisible()
  const id = await caseId(page.request)
  const bankResponse = await page.request.post('/api/admin/bank-accounts', { data: { name: `CI bank ${Date.now()}`, account_kind: 'client' } })
  expect(bankResponse.status()).toBe(200)
  const bank = await bankResponse.json()
  const description = `Bank recovery receipt ${Date.now()}`
  expect((await page.request.post(`/api/cases/${id}/ledger/post`, { data: {
    description, amount_pence: 10000, client_direction: 'credit', contact_label: 'N/A',
    firm_bank_account_id: bank.id, payment_method: 'bacs',
  } })).status()).toBe(204)
  const ledger = await (await page.request.get(`/api/cases/${id}/ledger`)).json()
  const pair = ledger.entries.find((e: { description: string }) => e.description === description).pair_id
  const today = new Date().toISOString().slice(0, 10)
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: 'Accounts', exact: true }).click()
  await page.getByRole('button', { name: 'Banking', exact: true }).click()
  await page.getByRole('combobox', { name: 'Client bank', exact: true }).selectOption(bank.id)
  const imported = page.waitForResponse(r => r.url().endsWith('/statements/import') && r.request().method() === 'POST')
  await page.getByLabel('Import statement (CSV/OFX)').setInputFiles({ name: 'statement.csv', mimeType: 'text/csv',
    buffer: Buffer.from(`Date,Description,Amount\n${today},${description},100.00\n`) })
  const importedResponse = await imported
  expect(importedResponse.status()).toBe(200)
  const line = (await importedResponse.json()).lines[0]
  const endpoint = `/api/accounts/banking/statements/lines/${line.id}`
  await page.getByRole('combobox', { name: 'Selected ledger entry', exact: true }).selectOption(pair)
  let lostResponse = false
  await page.route(`**/statements/lines/${line.id}/match`, async route => {
    if (!lostResponse) {
      lostResponse = true
      expect((await route.fetch()).status()).toBe(200)
      await route.abort('failed')
    } else await route.continue()
  })
  const statementRow = page.getByRole('row').filter({ hasText: description }).filter({ has: page.getByRole('button', { name: 'Match', exact: true }) })
  await statementRow.getByRole('button', { name: 'Match', exact: true }).click()
  // Reload-on-error observes the committed result without repeating the write.
  const matchedRow = page.getByRole('row').filter({ hasText: description }).filter({ has: page.getByRole('button', { name: 'Unmatch', exact: true }) })
  await expect(matchedRow).toContainText('Matched')
  expect(lostResponse).toBe(true)
  expect((await page.request.post(`${endpoint}/unmatch`, { data: { expected_version: 0 } })).status()).toBe(409)
  await matchedRow.getByRole('button', { name: 'Unmatch', exact: true }).click()
  await expect(page.getByRole('row').filter({ hasText: description }).filter({ has: page.getByRole('button', { name: 'Match', exact: true }) })).toContainText('Open')
  const history = await (await page.request.get(`${endpoint}/history`)).json()
  expect(history.filter((e: { action: string }) => e.action === 'bank.statement.match')).toHaveLength(1)
  const correction = history.find((e: { action: string }) => e.action === 'bank.statement.unmatch')
  const restored = await page.request.post(`${endpoint}/restore`, { data: { expected_version: 2, event_id: correction.id, reason: 'Undo verification correction' } })
  expect(restored.status()).toBe(200)
  expect((await restored.json()).matched_pair_id).toBe(pair)
  const created = await page.request.post('/api/accounts/banking/reconciliations', { data: {
    firm_bank_account_id: bank.id, period_end_date: today, statement_balance_pence: 10000,
  } })
  expect(created.status()).toBe(200)
  const recon = await created.json()
  expect(recon.difference_pence).toBe(0)
  const reconEndpoint = `/api/accounts/banking/reconciliations/${recon.id}`
  expect((await page.request.post(`${reconEndpoint}/approve`, { data: { expected_version: 0 } })).status()).toBe(200)
  expect((await page.request.post(`${endpoint}/unmatch`, { data: { expected_version: 3 } })).status()).toBe(409)
  expect((await page.request.post(`${reconEndpoint}/reopen`, { data: { expected_version: 1, reason: 'Correction drill' } })).status()).toBe(200)
  expect((await page.request.post(`${endpoint}/unmatch`, { data: { expected_version: 3 } })).status()).toBe(200)
  // Deactivate this isolated fixture bank so subsequent fixtures keep their original posting defaults.
  expect((await page.request.patch(`/api/admin/bank-accounts/${bank.id}`, { data: { is_active: false } })).status()).toBe(200)
})
