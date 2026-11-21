import { expect, test } from '@playwright/test'
import { credentials } from './core-helpers'

test('authenticated reports and accountant exports run in read-only snapshots', async ({ page }) => {
  await page.goto('/')
  const user = credentials('APPROVER')
  await page.getByLabel('Email address', { exact: true }).fill(user.email)
  await page.getByLabel('Password', { exact: true }).fill(user.password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Sign out', exact: true })).toBeVisible()
  const options = await page.request.get('/api/reports/fee-earners')
  expect(options.status()).toBe(200)
  const people = await options.json()
  expect(people.length).toBeGreaterThan(0)
  const data = { fee_earner_user_ids: people.map((person: {id: string}) => person.id) }
  for (const report of ['aged-debt', 'client-office-balances', 'billing', 'ledger-activity']) {
    const json = await page.request.post(`/api/reports/${report}?format=json`, { data })
    expect(json.status(), await json.text()).toBe(200)
    expect(Array.isArray((await json.json()).rows)).toBe(true)
    const xlsx = await page.request.post(`/api/reports/${report}?format=xlsx`, { data })
    expect(xlsx.status()).toBe(200)
    expect(xlsx.headers()['content-type']).toContain('spreadsheetml')
    expect((await xlsx.body()).subarray(0,2).toString()).toBe('PK')
  }
  const pack = await page.request.post('/api/reports/accountant-pack', { data: {
    ...data, period_end_date: new Date().toISOString().slice(0,10),
    include_exceptions: false, include_reconcile_doc: false,
  } })
  expect(pack.status(), await pack.text()).toBe(200)
  expect(pack.headers()['content-type']).toContain('application/zip')
})
