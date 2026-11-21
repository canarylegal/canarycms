import { expect, test } from '@playwright/test'
import { caseId, credentials } from './core-helpers'

test('posting and transfer forms retry lost responses once; whole reversals restore balances', async ({ page }) => {
  await page.goto('/')
  const user = credentials('APPROVER')
  await page.getByLabel('Email address', { exact: true }).fill(user.email)
  await page.getByLabel('Password', { exact: true }).fill(user.password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Sign out', exact: true })).toBeVisible()
  const id = await caseId(page.request)
  const destination = await caseId(page.request, '900002')
  const before = await (await page.request.get(`/api/cases/${id}/ledger`)).json()
  const otherBefore = await (await page.request.get(`/api/cases/${destination}/ledger`)).json()
  await page.getByRole('row').filter({ hasText: '900001' }).dblclick()
  await page.locator('button.accHead').filter({ hasText: 'Accounts' }).click()
  await page.getByRole('button', { name: 'Open accounts', exact: true }).click()
  await page.getByRole('button', { name: 'New posting', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'New posting', exact: true })
  await dialog.getByRole('button', { name: 'Party', exact: true }).click()
  await page.getByRole('option', { name: 'N/A', exact: true }).click()
  const description = `Ledger retry ${Date.now()}`
  await dialog.getByLabel(/^Description/).fill(description)
  await dialog.getByLabel(/^Amount/).fill('100')
  await dialog.getByRole('group', { name: 'Client account', exact: true }).getByLabel('Credit', { exact: true }).check()
  await dialog.getByLabel('Actual payment', { exact: true }).check()
  const postingKeys: string[] = []
  await page.route(`**/cases/${id}/ledger/post`, async route => {
    postingKeys.push(route.request().postDataJSON().idempotency_key)
    if (postingKeys.length === 1) {
      expect((await route.fetch()).status()).toBe(204)
      await route.abort('failed')
    } else await route.continue()
  })
  await dialog.getByRole('button', { name: 'Post', exact: true }).click()
  await expect(dialog.locator('.error')).toBeVisible()
  await dialog.getByRole('button', { name: 'Post', exact: true }).click()
  await expect(dialog).toBeHidden()
  expect(postingKeys).toHaveLength(2)
  expect(postingKeys[0]).toBeTruthy()
  expect(postingKeys[1]).toBe(postingKeys[0])
  const posted = await (await page.request.get(`/api/cases/${id}/ledger`)).json()
  const entries = posted.entries.filter((e: { description: string }) => e.description === description)
  expect(entries).toHaveLength(1)
  expect(posted.client.balance_pence).toBe(before.client.balance_pence + 10000)

  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: 'Accounts', exact: true }).click()
  await page.getByRole('button', { name: 'Banking', exact: true }).click()
  await page.getByPlaceholder('From case id', { exact: true }).fill(id)
  await page.getByPlaceholder('To case id', { exact: true }).fill(destination)
  await page.getByPlaceholder('Amount £', { exact: true }).fill('40')
  await page.getByPlaceholder('Description', { exact: true }).fill(description)
  const transferKeys: string[] = []
  let journalId = ''
  await page.route('**/accounts/banking/journals', async route => {
    if (route.request().method() !== 'POST') return route.continue()
    transferKeys.push(route.request().postDataJSON().idempotency_key)
    if (transferKeys.length === 1) {
      const response = await route.fetch()
      expect(response.status()).toBe(200)
      journalId = (await response.json()).id
      await route.abort('failed')
    } else await route.continue()
  })
  await page.getByRole('button', { name: 'Post journal', exact: true }).click()
  await expect(page.locator('.error').filter({ hasText: /network|fetch/i })).toBeVisible()
  await page.getByRole('button', { name: 'Post journal', exact: true }).click()
  await expect(page.getByPlaceholder('Amount £', { exact: true })).toHaveValue('')
  expect(transferKeys).toHaveLength(2)
  expect(transferKeys[0]).toBeTruthy()
  expect(transferKeys[1]).toBe(transferKeys[0])
  const journals = await (await page.request.get('/api/accounts/banking/journals')).json()
  expect(journals.filter((j: { description: string }) => j.description === description)).toHaveLength(1)
  const reverseJournal = { idempotency_key: 'dc34c395-16e3-44fb-bfa3-84b2b39a7101', reason: 'Synthetic correction' }
  const reverseURL = `/api/accounts/banking/journals/${journalId}/reverse`
  const reversed = await page.request.post(reverseURL, { data: reverseJournal })
  expect(reversed.status()).toBe(200)
  expect(await (await page.request.post(reverseURL, { data: reverseJournal })).json()).toEqual(await reversed.json())
  const reversePosting = await page.request.post(`/api/cases/${id}/ledger/pairs/${entries[0].pair_id}/reverse`, {
    data: { idempotency_key: 'dc34c395-16e3-44fb-bfa3-84b2b39a7102', reason: 'Synthetic receipt correction' },
  })
  expect(reversePosting.status()).toBe(200)
  expect((await (await page.request.get(`/api/cases/${id}/ledger`)).json()).client.balance_pence).toBe(before.client.balance_pence)
  expect((await (await page.request.get(`/api/cases/${destination}/ledger`)).json()).client.balance_pence).toBe(otherBefore.client.balance_pence)
})
