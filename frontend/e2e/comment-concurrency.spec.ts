import { expect, test } from '@playwright/test'
import { apiLogin, caseId, login } from './core-helpers'

test('stale comment keeps its draft and reconciles against the latest saved version', async ({page,playwright,baseURL}) => {
  await login(page)
  const id = await caseId(page.request)
  const other = await playwright.request.newContext({baseURL})
  try {
    await apiLogin(other,'APPROVER')
    const name = `shared-note-${Date.now()}.txt`
    const created = await page.request.post(`/api/cases/${id}/files`, {multipart:{upload:{name,mimeType:'text/plain',buffer:Buffer.from('Original note')}}})
    expect(created.status()).toBe(201)
    const file = await created.json()
    const path = `/api/cases/${id}/files/${file.id}/comment`
    const original = await page.request.get(path)
    expect(original.headers()['cache-control']).toBe('no-store')
    const opened = await original.json()
    expect(opened.text).toBe('Original note')
    expect((await page.request.patch(path,{data:{text:'missing version'}})).status()).toBe(422)
    await page.getByRole('textbox',{name:'Search cases',exact:true}).fill('900001')
    await page.getByRole('row').filter({hasText:'900001'}).dblclick()
    await page.getByRole('textbox',{name:'Search documents',exact:true}).fill(name)
    await page.getByText(name.replace(/\.txt$/, ''),{exact:true}).dblclick()
    await expect(page.getByRole('dialog',{name:'Edit comment'})).toBeVisible()
    await page.getByLabel('Your comment draft').fill('My draft')
    expect((await other.patch(path,{data:{text:'Colleague addition',expected_version:opened.version}})).status()).toBe(200)
    await page.getByRole('button',{name:'Save comment',exact:true}).click()
    await expect(page.getByRole('alert')).toContainText('Your draft has not been saved')
    await expect(page.getByLabel('Your comment draft')).toHaveValue('My draft')
    expect((await (await other.get(path)).json()).text).toBe('Colleague addition')
    await page.getByRole('button',{name:'Load latest comment'}).click()
    await expect(page.getByLabel('Latest saved comment')).toHaveValue('Colleague addition')
    await expect(page.getByLabel('Your comment draft')).toHaveValue('My draft')
    await page.getByLabel('Your comment draft').fill('Colleague addition and my draft')
    await page.getByRole('button',{name:'Save comment',exact:true}).click()
    await expect(page.getByRole('dialog',{name:'Edit comment'})).toHaveCount(0)
    const combined=await(await other.get(path)).json()
    expect(combined.text).toBe('Colleague addition and my draft')
    const races=await Promise.all([
      page.request.patch(path,{data:{text:'Race A',expected_version:combined.version}}),
      other.patch(path,{data:{text:'Race B',expected_version:combined.version}}),
    ])
    expect(races.map(r=>r.status()).sort()).toEqual([200,409])
    const winner=await(await other.get(path)).json()
    expect(winner.version).toBe(combined.version+1)
    expect(winner.text).toBe(races[0].status()===200?'Race A':'Race B')
  } finally { await other.dispose() }
})
