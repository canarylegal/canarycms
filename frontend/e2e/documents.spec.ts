import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { caseId, login } from './core-helpers'

test('document upload, double-click open, edit, save and download persist real content', async ({ page }) => {
  test.setTimeout(180_000)
  await login(page)
  const id = await caseId(page.request)
  await page.getByRole('row').filter({ hasText: '900001' }).dblclick()
  const name = `workflow-${Date.now()}.docx`
  const upload = await readFile(path.resolve('e2e/fixtures/workflow.docx'))
  const chooser = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: 'Import', exact: true }).click()
  await (await chooser).setFiles({ name, mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', buffer: upload })
  await expect(page.getByText(name, { exact: true })).toBeVisible()
  const files = await (await page.request.get(`/api/cases/${id}/files`)).json() as { id: string; original_filename: string }[]
  const file = files.find((item) => item.original_filename === name)
  expect(file).toBeDefined()
  const popup = page.waitForEvent('popup')
  await page.getByText(name, { exact: true }).dblclick()
  const editor = await popup
  const office = editor.frameLocator('iframe[name="frameEditor"]')
  await expect(office.getByText('Page 1 of 1', { exact: true })).toBeVisible({ timeout: 90_000 })
  // Exercise the real editor and callback path, not a mocked save response.
  const canvasInput = office.locator('#area_id')
  await canvasInput.focus()
  await canvasInput.press('Control+End')
  await canvasInput.press('Enter')
  const marker = `SAVED-BY-CORE-TEST-${Date.now()}`
  await canvasInput.pressSequentially(marker)
  await editor.getByRole('button', { name: 'Save Changes', exact: true }).click()
  await expect(editor.getByRole('button', { name: 'Save Changes', exact: true })).toBeEnabled({ timeout: 90_000 })
  await editor.getByRole('button', { name: 'Close', exact: true }).click()
  await page.getByText(name, { exact: true }).click({ button: 'right' })
  const download = page.waitForEvent('download')
  await page.getByRole('menuitem', { name: 'Download', exact: true }).click()
  const downloaded = await download
  expect(downloaded.suggestedFilename()).toBe(name)
  const destination = test.info().outputPath(name)
  await downloaded.saveAs(destination)
  // Inspect the downloaded DOCX bytes, so a successful-looking Save cannot mask data loss.
  const { execFileSync } = await import('node:child_process')
  const xml = execFileSync('python3', ['-c', 'import sys,zipfile; print(zipfile.ZipFile(sys.argv[1]).read("word/document.xml").decode())', destination], { encoding: 'utf8' })
  expect(xml).toContain(marker)
  await page.screenshot({ path: test.info().outputPath('documents.png') })
})
