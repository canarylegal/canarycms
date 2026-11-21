import {expect,test} from '@playwright/test'
import {apiLogin,caseId,login} from './core-helpers'

test('paged documents and folder metadata enforce matter access',async({request,playwright,baseURL})=>{
 await apiLogin(request,'DENIED');const id=await caseId(request)
 for(const path of ['browse','folder-metadata'])expect((await request.get(`/api/cases/${id}/files/${path}`)).status()).toBe(403)
 const staff=await playwright.request.newContext({baseURL})
 try{
  await apiLogin(staff,'STAFF')
  const files=await(await staff.get(`/api/cases/${id}/files`)).json()
  expect(files.length).toBeGreaterThan(0)
  expect((await request.get(`/api/cases/${id}/files/${files[0].id}/metadata`)).status()).toBe(403)
  const other=await caseId(staff,'900002')
  await apiLogin(staff,'APPROVER')
  expect((await staff.get(`/api/cases/${other}/files/${files[0].id}/metadata`)).status()).toBe(404)
 }finally{await staff.dispose()}
})

test('document search failure recovers via Refresh without changing preferences',async({page})=>{
 await login(page);const id=await caseId(page.request)
 await page.getByRole('row').filter({hasText:'900001'}).dblclick()
 await expect(page.locator('.caseDocsScroll')).toBeVisible()
 const preferences=(await(await page.request.get('/api/auth/me')).json()).ui_preferences
 let fail=true
 await page.route(`**/api/cases/${id}/files/browse?**`,route=>fail?route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Synthetic document query failure'})}):route.continue())
 await page.getByRole('textbox',{name:'Search documents',exact:true}).fill('nonexistent document')
 await expect(page.getByRole('alert')).toContainText('Synthetic document query failure')
 fail=false
 await page.getByRole('button',{name:'Refresh',exact:true}).click()
 await expect(page.getByRole('alert')).toHaveCount(0)
 await page.getByRole('textbox',{name:'Search documents',exact:true}).clear()
 await expect(page.locator('.caseDocsScroll [data-doc-key]').first()).toBeVisible()
 expect((await(await page.request.get('/api/auth/me')).json()).ui_preferences).toEqual(preferences)
})
