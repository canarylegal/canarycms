import { expect, test } from '@playwright/test'
import { apiLogin, caseId, login } from './core-helpers'

test('matter menu preserves firm-wide visibility and opening restrictions', async ({request}) => {
  expect((await request.get('/api/cases/menu')).status()).toBe(401)
  expect((await request.get('/api/cases/menu-options')).status()).toBe(401)
  await apiLogin(request, 'DENIED')
  const id=await caseId(request)
  const response=await request.get('/api/cases/menu?q=900001')
  expect(response.ok()).toBe(true)
  expect((await response.json()).items.map((row:{id:string})=>row.id)).toContain(id)
  expect((await request.get(`/api/cases/${id}`)).status()).toBe(403)
})

test('failed matter search recovers using Refresh without changing saved preferences', async ({page}) => {
  await login(page)
  await expect(page.getByRole('row').filter({hasText:'900001'})).toBeVisible()
  const before=(await (await page.request.get('/api/auth/me')).json()).ui_preferences
  let fail=true
  await page.route('**/api/cases/menu?**', route => {
    if (fail) return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Temporary matter search failure'})})
    return route.continue()
  })
  await page.getByRole('textbox',{name:'Search cases',exact:true}).fill('900001')
  await expect(page.getByRole('alert')).toContainText('Temporary matter search failure')
  fail=false
  await page.getByRole('button',{name:'Refresh',exact:true}).click()
  await expect(page.getByRole('row').filter({hasText:'900001'})).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
  expect((await (await page.request.get('/api/auth/me')).json()).ui_preferences).toEqual(before)
})
