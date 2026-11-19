import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { caseId, credentials, login } from './core-helpers'

test('real expired session keeps selected upload and resumes after sign-in in another tab', async ({ page, context }) => {
  await login(page)
  const id = await caseId(page.request)
  await page.getByRole('row').filter({ hasText: '900001' }).dblclick()
  // Expire the real server session, not a mocked 401 response.
  expect((await page.request.post('/api/auth/logout')).ok()).toBe(true)
  let navigations = 0
  page.on('framenavigated', frame => { if (frame === page.mainFrame()) navigations++ })
  const name = `session-${Date.now()}.docx`
  const chooser = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: 'Import', exact: true }).click()
  await (await chooser).setFiles({ name, mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', buffer: await readFile('e2e/fixtures/workflow.docx') })
  await expect(page.getByText('Upload interrupted', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Sign in in another tab' })).toBeVisible()
  const popup = context.waitForEvent('page')
  await page.getByRole('link', { name: 'Sign in in another tab' }).click()
  const signin = await popup
  const user = credentials()
  await signin.getByLabel('Email address', { exact: true }).fill(user.email)
  await signin.getByLabel('Password', { exact: true }).fill(user.password)
  await signin.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(signin.getByRole('button', { name: 'New matter', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'I’ve signed in' }).click()
  await expect(page.getByRole('link', { name: 'Sign in in another tab' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByText(name, { exact: true })).toBeVisible()
  expect(navigations).toBe(0)
  const files = await (await page.request.get(`/api/cases/${id}/files`)).json()
  expect(files.filter((f: { original_filename: string }) => f.original_filename === name)).toHaveLength(1)
  await signin.close()
})
