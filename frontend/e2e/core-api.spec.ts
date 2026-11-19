import { expect, test } from '@playwright/test'
import { apiLogin, caseId } from './core-helpers'

test('restricted user cannot open matter, list documents, or post to its ledger', async ({ request, playwright, baseURL }) => {
  await apiLogin(request, 'DENIED')
  const id = await caseId(request)
  const staff = await playwright.request.newContext({ baseURL })
  try {
    await apiLogin(staff, 'STAFF')
    const uploaded = await staff.post(`/api/cases/${id}/files`, {
      multipart: { upload: { name: 'private-test.txt', mimeType: 'text/plain', buffer: Buffer.from('Synthetic restricted content') } },
    })
    expect(uploaded.status()).toBe(201)
    const file = await uploaded.json()
    expect((await request.get(`/api/cases/${id}/files/${file.id}`)).status()).toBe(403)
  } finally {
    await staff.dispose()
  }
  for (const suffix of ['', '/files', '/ledger']) {
    expect((await request.get(`/api/cases/${id}${suffix}`)).status()).toBe(403)
  }
  expect((await request.post(`/api/cases/${id}/ledger/post`, {
    data: { description: 'Must not persist', amount_pence: 100, client_direction: 'credit' },
  })).status()).toBe(403)
})

test('anticipated posting requires approval and balances change only after approval', async ({ playwright, baseURL }) => {
  const staff = await playwright.request.newContext({ baseURL })
  const approver = await playwright.request.newContext({ baseURL })
  try {
    await apiLogin(staff, 'STAFF')
    await apiLogin(approver, 'APPROVER')
    const id = await caseId(staff)
    const before = await (await staff.get(`/api/cases/${id}/ledger`)).json()
    const description = `Core test receipt ${Date.now()}`
    const post = await staff.post(`/api/cases/${id}/ledger/post`, {
      data: { description, amount_pence: 12345, client_direction: 'credit', anticipated: true, anticipated_for_date: new Date().toISOString().slice(0, 10) },
    })
    expect(post.status()).toBe(204)
    const pending = await (await staff.get(`/api/cases/${id}/ledger`)).json()
    const entry = pending.entries.find((e: { description: string }) => e.description === description)
    expect(entry).toBeDefined()
    expect(entry.is_approved).toBe(false)
    expect(pending.client.balance_pence).toBe(before.client.balance_pence)
    expect((await staff.post(`/api/cases/${id}/ledger/approve/${entry.pair_id}`)).status()).toBe(403)
    expect((await approver.post(`/api/cases/${id}/ledger/approve/${entry.pair_id}`)).status()).toBe(204)
    const approved = await (await staff.get(`/api/cases/${id}/ledger`)).json()
    expect(approved.client.balance_pence).toBe(before.client.balance_pence + 12345)
    expect(approved.entries.find((e: { pair_id: string }) => e.pair_id === entry.pair_id).is_approved).toBe(true)
    // A failed debit must leave the previous committed balance intact.
    expect((await approver.post(`/api/cases/${id}/ledger/post`, {
      data: { description: 'Rejected deficit', amount_pence: approved.client.balance_pence + 1, client_direction: 'debit' },
    })).status()).toBe(422)
    expect((await (await staff.get(`/api/cases/${id}/ledger`)).json()).client.balance_pence).toBe(approved.client.balance_pence)
  } finally {
    await staff.dispose()
    await approver.dispose()
  }
})
