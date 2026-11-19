import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { caseId, login } from './core-helpers'

const docx = () => readFile(path.resolve('e2e/fixtures/workflow.docx'))

test('partial upload retries only the rejected file and keeps the original selection', async ({ page }) => {
  await login(page)
  const id = await caseId(page.request)
  await page.getByRole('row').filter({ hasText: '900001' }).dblclick()
  const names = [`first-${Date.now()}.docx`, `second-${Date.now()}.docx`]
  const attempts: string[] = []
  let rejected = false
  await page.route(`**/api/cases/${id}/files`, async route => {
    if (route.request().method() !== 'POST') return route.continue()
    const name = /filename="([^"]+)"/.exec(route.request().postData() ?? '')?.[1] ?? ''
    attempts.push(name)
    if (name === names[1] && !rejected) { rejected = true; return route.fulfill({ status: 429, body: 'busy' }) }
    await route.continue()
  })
  const chooser = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: 'Import', exact: true }).click()
  const buffer = await docx()
  await (await chooser).setFiles(names.map(name => ({ name, mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', buffer })))
  await expect(page.getByText('Upload interrupted', { exact: true })).toBeVisible()
  await expect(page.getByText(/1 file\(s\) completed/)).toBeVisible()
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  for (const name of names) await expect(page.getByText(name, { exact: true })).toBeVisible()
  expect(attempts).toEqual([names[0], names[1], names[1]])
  const files = await (await page.request.get(`/api/cases/${id}/files`)).json() as { original_filename: string }[]
  for (const name of names) expect(files.filter(f => f.original_filename === name)).toHaveLength(1)
})

test('lost upload response is reconciled without silently uploading a duplicate', async ({ page }) => {
  await login(page)
  const id = await caseId(page.request)
  await page.getByRole('row').filter({ hasText: '900001' }).dblclick()
  const name = `uncertain-${Date.now()}.docx`
  let posts = 0
  await page.route(`**/api/cases/${id}/files`, async route => {
    if (route.request().method() !== 'POST') return route.continue()
    posts++
    const response = await route.fetch()
    expect(response.ok()).toBe(true)
    await route.abort('failed') // The server accepted the upload, but the browser lost its reply.
  })
  const chooser = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: 'Import', exact: true }).click()
  await (await chooser).setFiles({ name, mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', buffer: await docx() })
  await expect(page.getByText(/upload result could not be confirmed/)).toBeVisible()
  expect(posts).toBe(1)
  const files = await (await page.request.get(`/api/cases/${id}/files`)).json() as { original_filename: string }[]
  expect(files.filter(f => f.original_filename === name)).toHaveLength(1)
})

test('denied downloads show a useful error; transient downloads can be retried from the same menu', async ({ page }) => {
  await login(page)
  const id = await caseId(page.request)
  const name = `download-recovery-${Date.now()}.docx`
  const uploaded = await page.request.post(`/api/cases/${id}/files`, { multipart: { folder: '', upload: { name, mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', buffer: await docx() } } })
  expect(uploaded.ok()).toBe(true)
  const file = await uploaded.json() as { id: string }
  await page.getByRole('row').filter({ hasText: '900001' }).dblclick()
  const url = `**/api/cases/${id}/files/${file.id}`
  let attempts = 0
  await page.route(url, route => { attempts++; return route.fulfill({ status: 403, body: 'private server detail' }) })
  await page.getByText(name, { exact: true }).click({ button: 'right' })
  await page.getByRole('menuitem', { name: 'Download', exact: true }).click()
  await expect(page.getByText(/You do not have permission to access this document/)).toBeVisible()
  expect(attempts).toBe(1)
  await page.getByRole('button', { name: 'OK', exact: true }).click()
  await page.unroute(url)
  attempts = 0
  await page.route(url, route => { attempts++; return attempts <= 2 ? route.fulfill({ status: 503, body: '<html>proxy failed</html>' }) : route.continue() })
  await page.getByText(name, { exact: true }).click({ button: 'right' })
  await page.getByRole('menuitem', { name: 'Download', exact: true }).click()
  await expect(page.getByText('Download interrupted', { exact: true })).toBeVisible()
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  expect((await download).suggestedFilename()).toBe(name)
  expect(attempts).toBe(3)
})
