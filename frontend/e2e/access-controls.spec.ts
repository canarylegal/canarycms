import { expect, test } from '@playwright/test'
import { apiLogin, caseId } from './core-helpers'

// Separate cookie jars prove direct API calls cannot bypass the visible UI.
test('cross-user document routes deny access, preserve data and record denials', async ({ playwright, baseURL }) => {
  const owner = await playwright.request.newContext({ baseURL })
  const denied = await playwright.request.newContext({ baseURL })
  const admin = await playwright.request.newContext({ baseURL })
  try {
    await apiLogin(owner, 'STAFF'); await apiLogin(denied, 'DENIED'); await apiLogin(admin, 'APPROVER')
    const id = await caseId(owner)
    const otherId = await caseId(admin, '900002')
    const name = `access-${Date.now()}.txt`
    const secret = 'private synthetic document bytes'
    const upload = await owner.post(`/api/cases/${id}/files`, { multipart: { upload: { name, mimeType: 'text/plain', buffer: Buffer.from(secret) } } })
    expect(upload.status()).toBe(201)
    const file = await upload.json()
    const root = `/api/cases/${id}/files`
    const routes: [string, string, object?][] = [
      ['GET', `${root}/browse`], ['GET', `${root}/folder-metadata`], ['GET', `${root}/${file.id}/metadata`],
      ['GET', root], ['GET', `${root}/${file.id}`], ['GET', `${root}/export-zip`],
      ['GET', `${root}/folders/download-zip?folder_path=`],
      ['GET', `${root}/${file.id}/oo-save-status?base_version=1`],
      ['POST', `${root}/${file.id}/oo-export-pdf`, { browser_url: 'http://onlyoffice/cache.pdf' }],
      ['POST', `${root}/${file.id}/oo-persist-download`, { browser_url: 'http://onlyoffice/cache.docx' }],
      ['GET', `${root}/${file.id}/onlyoffice-config`], ['GET', `${root}/${file.id}/edit-session`],
      ['POST', `${root}/${file.id}/checkout-edit`], ['POST', `${root}/${file.id}/release-edit`],
      ['POST', `${root}/${file.id}/discard-edit`],
      ['PATCH', `${root}/${file.id}/rename`, { original_filename: 'stolen.txt', expected_original_filename: name }],
      ['POST', `${root}/${file.id}/move`, { folder_path: '' }],
      ['DELETE', `${root}/${file.id}`],
      ['POST', `${root}/${file.id}/oo-force-save?doc_key=never-log-this-secret&phase=arm`],
    ]
    for (const [method, url, data] of routes) {
      const response = await denied.fetch(url, { method, data })
      expect(response.status(), `${method} ${url}`).toBe(403)
      expect(await response.text()).not.toContain(secret)
    }
    expect((await denied.post(root, { multipart: { upload: { name: 'forbidden.txt', mimeType: 'text/plain', buffer: Buffer.from('x') } } })).status()).toBe(403)
    const wrongMatter = await admin.post(`/api/cases/${otherId}/files`, { multipart: { upload: { name: 'other.txt', mimeType: 'text/plain', buffer: Buffer.from('other secret') } } })
    const foreign = await wrongMatter.json()
    for (const method of ['GET', 'DELETE']) expect((await owner.fetch(`${root}/${foreign.id}`, { method })).status()).toBe(404)
    expect(await (await owner.get(`${root}/${file.id}`)).text()).toBe(secret)
    const who = await (await denied.get('/api/auth/me')).json()
    const events = await (await admin.get(`/api/admin/audit-events?action=access.denied&actor_user_id=${who.id}&limit=100`)).json()
    expect(events.length).toBeGreaterThanOrEqual(routes.length + 1)
    expect(JSON.stringify(events)).not.toContain('never-log-this-secret')
    expect(JSON.stringify(events)).not.toContain(secret)
    expect(events.some((e: { meta: { method: string; file_id: string } }) => e.meta.method === 'DELETE' && e.meta.file_id === file.id)).toBe(true)
    const reads = await (await admin.get(`/api/admin/audit-events?action=case.file.read&entity_id=${file.id}`)).json()
    expect(reads.length).toBeGreaterThan(0)
  } finally { await owner.dispose(); await denied.dispose(); await admin.dispose() }
})

test('another authorised user cannot release an active editors pending save', async ({ playwright, baseURL }) => {
  const owner = await playwright.request.newContext({ baseURL })
  const other = await playwright.request.newContext({ baseURL })
  try {
    await apiLogin(owner, 'STAFF'); await apiLogin(other, 'APPROVER')
    const id = await caseId(owner)
    const { readFile } = await import('node:fs/promises')
    const response = await owner.post(`/api/cases/${id}/files`, { multipart: { upload: { name: `ownership-${Date.now()}.docx`, mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', buffer: await readFile('e2e/fixtures/workflow.docx') } } })
    const file = await response.json(); const root = `/api/cases/${id}/files/${file.id}`
    expect((await owner.post(`${root}/checkout-edit`)).status()).toBe(201)
    const arm = await owner.post(`${root}/oo-force-save?phase=arm&doc_key=ownership-test`)
    expect(arm.ok()).toBe(true)
    const { base_version } = await arm.json()
    expect((await other.post(`${root}/release-edit`)).status()).toBe(204)
    expect((await (await owner.get(`${root}/edit-session`)).json()).active).toBe(true)
    expect((await (await owner.get(`${root}/oo-save-status?base_version=${base_version}`)).json()).saved).toBe(false)
    expect((await other.post(`${root}/oo-force-save?phase=arm&doc_key=ownership-test`)).status()).toBe(409)
    expect((await owner.post(`${root}/release-edit`)).status()).toBe(204)
  } finally { await owner.dispose(); await other.dispose() }
})

test('revoking an allow rule invalidates existing document sessions and is audited', async ({ playwright, baseURL }) => {
  const owner = await playwright.request.newContext({ baseURL })
  const guest = await playwright.request.newContext({ baseURL })
  const admin = await playwright.request.newContext({ baseURL })
  try {
    await apiLogin(owner, 'STAFF'); await apiLogin(guest, 'DENIED'); await apiLogin(admin, 'APPROVER')
    const id = await caseId(owner)
    const who = await (await guest.get('/api/auth/me')).json()
    const { readFile } = await import('node:fs/promises')
    const uploaded = await owner.post(`/api/cases/${id}/files`, { multipart: { upload: { name: `revoke-${Date.now()}.docx`, mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', buffer: await readFile('e2e/fixtures/workflow.docx') } } })
    const file = await uploaded.json(); const root = `/api/cases/${id}/files/${file.id}`
    expect((await owner.put(`/api/cases/${id}/access`, { data: { user_id: who.id, mode: 'allow' } })).ok()).toBe(true)
    expect((await guest.put(`/api/cases/${id}/access`, { data: { user_id: who.id, mode: 'allow' } })).status()).toBe(403)
    const checkout = await guest.post(`${root}/checkout-edit`)
    expect(checkout.status()).toBe(201)
    const session = await checkout.json()
    expect((await guest.get(session.webdav_file_url)).ok()).toBe(true)
    expect((await owner.delete(`/api/cases/${id}/access/${who.id}`)).status()).toBe(204)
    expect((await guest.get(`${root}`)).status()).toBe(403)
    expect((await guest.get(`/api/cases/${id}/files/browse`)).status()).toBe(403)
    expect((await guest.get(`/api/cases/${id}/files/folder-metadata`)).status()).toBe(403)
    expect((await guest.post(`${root}/oo-force-save?phase=arm&doc_key=revoked`)).status()).toBe(403)
    expect((await guest.get(session.webdav_file_url)).status()).toBe(404)
    const events = await (await admin.get(`/api/admin/audit-events?action_prefix=case.access.&case_id=${id}`)).json()
    expect(events.some((e: { action: string; meta: { user_id: string } }) => e.action === 'case.access.upsert' && e.meta.user_id === who.id)).toBe(true)
    expect(events.some((e: { action: string; meta: { user_id: string } }) => e.action === 'case.access.delete' && e.meta.user_id === who.id)).toBe(true)
  } finally { await owner.dispose(); await guest.dispose(); await admin.dispose() }
})
