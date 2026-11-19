import { expect, test, type Locator } from '@playwright/test'
import { caseId, login } from './core-helpers'

async function tracks(header: Locator) {
  return header.evaluate(el => getComputedStyle(el).gridTemplateColumns.split(' ').map(parseFloat))
}
async function aligned(header: Locator, body: Locator) {
  const a = await tracks(header)
  const b = await tracks(body)
  expect(b.length).toBe(a.length)
  a.forEach((width, i) => expect(Math.abs(width - b[i])).toBeLessThan(1))
}

test('saved menu proportions survive sidebar, device size and reload; dragging saves once', async ({ page }) => {
  await page.setViewportSize({ width: 1800, height: 1000 })
  await login(page)
  const saved = [140, 260, 340, 180, 120]
  const prefs = { main_menu_column_widths: saved, tasks_menu_column_widths: [100, 80, 100, 200, 300, 200, 100], contacts_column_widths: [300, 200, 300, 200] }
  expect((await page.request.put('/api/users/me/ui-preferences', { data: prefs })).ok()).toBe(true)
  await page.reload()
  const header = page.locator('.casesTableScroll .tr.th').first()
  await expect(header).toBeVisible()
  const writes: string[] = []
  page.on('request', request => {
    if (request.url().includes('/users/me/ui-preferences') && request.method() === 'PUT') writes.push(request.postData() ?? '')
  })
  const originalLabels = await header.locator('.thbtn').allTextContents()
  const wide = await tracks(header)
  expect(wide[2] / wide[1]).toBeCloseTo(saved[2] / saved[1], 2)
  await page.getByRole('button', { name: /^(Expand|Collapse) sidebar$/ }).click()
  await expect.poll(async () => (await tracks(header))[2]).not.toBe(wide[2])
  await header.evaluate(async () => {
    await Promise.all(document.getAnimations().map(animation => animation.finished.catch(() => {})))
  })
  const toggled = await tracks(header)
  expect(toggled[2] / toggled[1]).toBeCloseTo(saved[2] / saved[1], 2)
  await page.setViewportSize({ width: 1100, height: 800 })
  await aligned(header, page.getByRole('row').filter({ hasText: '900001' }))
  await page.setViewportSize({ width: 750, height: 800 })
  const minimums = [88, 140, 180, 120, 90]
  const narrow = await tracks(header)
  narrow.forEach((width, i) => expect(width).toBeGreaterThanOrEqual(minimums[i] - 1))
  expect(await header.locator('.thbtn').allTextContents()).toEqual(originalLabels)
  await page.setViewportSize({ width: 1800, height: 1000 })
  await expect.poll(async () => (await tracks(header))[2]).toBeCloseTo(toggled[2], 0)
  expect(writes).toEqual([])
  expect((await (await page.request.get('/api/auth/me')).json()).ui_preferences.main_menu_column_widths).toEqual(saved)

  const before = await tracks(header)
  const handle = header.getByRole('separator').first()
  const box = await handle.boundingBox()
  expect(box).not.toBeNull()
  await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2)
  await page.mouse.down()
  await page.mouse.move(box!.x + box!.width / 2 + 40, box!.y + box!.height / 2, { steps: 4 })
  expect(writes).toEqual([])
  await page.mouse.up()
  await expect.poll(() => writes.length).toBe(1)
  const after = await tracks(header)
  expect(after[0] - before[0]).toBeCloseTo(40, 0)
  expect(before[1] - after[1]).toBeCloseTo(40, 0)
  const persisted = (await (await page.request.get('/api/auth/me')).json()).ui_preferences.main_menu_column_widths
  await page.reload()
  await expect(header).toBeVisible()
  expect((await tracks(header))[0] / (await tracks(header))[1]).toBeCloseTo(persisted[0] / persisted[1], 2)
  await page.screenshot({ path: test.info().outputPath('columns-matters.png') })

  for (const [name, selector, key] of [
    ['Tasks', '.tasksTableScroll .tr.th', 'tasks_menu_column_widths'],
    ['Contacts', '.contactsTableScroll .tr.th', 'contacts_column_widths'],
  ] as const) {
    await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name, exact: true }).click()
    const head = page.locator(selector)
    await expect(head).toBeVisible()
    const large = await tracks(head)
    await page.setViewportSize({ width: 1200, height: 800 })
    expect((await tracks(head))[0]).toBeLessThan(large[0])
    expect((await (await page.request.get('/api/auth/me')).json()).ui_preferences[key]).toEqual(prefs[key])
    await page.setViewportSize({ width: 1800, height: 1000 })
  }
  expect(writes).toHaveLength(1)
  // Restore shared fixture preferences for subsequent workflow tests.
  expect((await page.request.put('/api/users/me/ui-preferences', { data: { main_menu_column_widths: [], tasks_menu_column_widths: [], contacts_column_widths: [] } })).ok()).toBe(true)
})

test('case document columns scale together and remain aligned at minimum size', async ({ page }) => {
  await page.setViewportSize({ width: 1800, height: 1000 })
  await login(page)
  const id = await caseId(page.request)
  const parent = await page.request.post(`/api/cases/${id}/files`, { multipart: {
    upload: { name: 'column-parent.eml', mimeType: 'message/rfc822', buffer: Buffer.from('From: test@example.com\r\nSubject: Column fixture\r\n\r\nTest message') },
  } })
  expect(parent.status()).toBe(201)
  const attachment = await page.request.post(`/api/cases/${id}/files`, { multipart: {
    parent_file_id: (await parent.json()).id,
    upload: { name: 'column-attachment.txt', mimeType: 'text/plain', buffer: Buffer.from('Test attachment') },
  } })
  expect(attachment.status()).toBe(201)
  await page.getByRole('row').filter({ hasText: '900001' }).dblclick()
  const header = page.locator('.docsTh')
  await expect(header).toBeVisible()
  const large = await tracks(header)
  await aligned(header, page.locator('.docsTr.attachmentChild'))
  await page.setViewportSize({ width: 1100, height: 800 })
  const small = await tracks(header)
  expect(small[0]).toBeLessThan(large[0])
  expect(small[2]).toBeLessThan(large[2])
  await aligned(header, page.locator('.docsTr.rowbtn').first())
  await aligned(header, page.locator('.docsTr.attachmentChild'))
  await page.setViewportSize({ width: 750, height: 800 })
  const minimums = [200, 76, 132, 92]
  ;(await tracks(header)).forEach((width, i) => expect(width).toBeGreaterThanOrEqual(minimums[i] - 1))
  await aligned(header, page.locator('.docsTr.rowbtn').first())
  await aligned(header, page.locator('.docsTr.attachmentChild'))
  await page.screenshot({ path: test.info().outputPath('columns-documents-narrow.png') })
  await page.locator('.caseLeft').getByRole('button', { name: /^Tasks/ }).click()
  await page.getByRole('button', { name: 'Open tasks', exact: true }).click()
  const tasks = page.locator('.tasksTableEmbed .tasksTableScroll')
  await expect(tasks.locator('.tr.th')).toBeVisible()
  expect(await tasks.evaluate(el => getComputedStyle(el).overflowX)).toBe('auto')
  expect(await tasks.evaluate(el => el.scrollWidth > el.clientWidth)).toBe(true)
  await page.setViewportSize({ width: 1800, height: 1000 })
  expect((await tracks(tasks.locator('.tr.th')))[4]).toBeGreaterThan(180)

})
