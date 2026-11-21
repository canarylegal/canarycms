import { expect, test } from '@playwright/test'
import { createHash } from 'node:crypto'
import { apiLogin } from './core-helpers'

test('approval freezes report bytes and protects archive downloads', async ({ request, playwright, baseURL }) => {
  await apiLogin(request, 'APPROVER')
  // An ancient synthetic period cannot close dates used by other workflow tests.
  const create = await request.post('/api/reports/reconciliations', { data: {
    period_end_date: '1901-01-31', bank_statement_balance_pence: 0, notes: 'Isolated immutable archive test',
  } })
  expect(create.status(), await create.text()).toBe(201)
  const { id } = await create.json()
  const approved = await request.post(`/api/reports/reconciliations/${id}/approve`)
  expect(approved.status(), await approved.text()).toBe(200)
  const history = await request.get(`/api/reports/approved-snapshots?source_kind=firm&source_id=${id}`)
  expect(history.status(), await history.text()).toBe(200)
  const { items } = await history.json()
  expect(items).toHaveLength(1)
  expect(items[0].version).toBe(1)
  expect(items[0].integrity).toBe('verified')
  const download = await request.get(`/api/reports/approved-snapshots/${items[0].snapshot_id}/download`)
  expect(download.status(), await download.text()).toBe(200)
  expect(createHash('sha256').update(await download.body()).digest('hex')).toBe(items[0].sha256)
  expect(download.headers()['cache-control']).toContain('no-store')
  const first = await request.get(`/api/reports/reconciliations/${id}/report.docx`)
  const second = await request.get(`/api/reports/reconciliations/${id}/report.docx`)
  expect(first.status()).toBe(200)
  expect(first.headers()['x-canary-archive-state']).toBe('archived')
  expect(await second.body()).toEqual(await first.body())
  const options = await request.get('/api/reports/fee-earners')
  const people = await options.json()
  const pack = await request.post('/api/reports/accountant-pack', { data: {
    fee_earner_user_ids: people.map((person: {id: string}) => person.id),
    period_end_date: '1901-01-31', include_reconcile_doc: true, include_exceptions: false,
  } })
  expect(pack.status(), await pack.text()).toBe(200)
  expect(pack.headers()['cache-control']).toContain('no-store')
  const staff = await playwright.request.newContext({ baseURL })
  try {
    await apiLogin(staff, 'STAFF')
    const denied = await staff.get(`/api/reports/approved-snapshots/${items[0].snapshot_id}/download`)
    expect(denied.status()).toBe(403)
  } finally { await staff.dispose() }
})
