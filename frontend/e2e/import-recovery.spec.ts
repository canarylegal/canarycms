import {test, expect} from '@playwright/test'
import {randomUUID} from 'node:crypto'
import {login, apiLogin, caseId} from './core-helpers'

async function importFiles(page: import('@playwright/test').Page, names: string[]) {
 const chooser=page.waitForEvent('filechooser')
 await page.getByRole('button',{name:'Import',exact:true}).click()
 await (await chooser).setFiles(names.map(name=>({name,mimeType:'text/plain',buffer:Buffer.from(name)})))
}

test('lost upload acknowledgement retries the same receipt and resumes only pending files',async({page})=>{
 await login(page);const id=await caseId(page.request)
 await page.getByRole('row').filter({hasText:'900001'}).dblclick()
 const prefix=`recovery-${randomUUID()}`
 const names=[`${prefix}-one.txt`,`${prefix}-two.txt`,`${prefix}-three.txt`]
 const keys:string[]=[];let intercepted=false
 await page.route(`**/api/cases/${id}/files`,async route=>{
  if(route.request().method()!=='POST')return route.continue()
  keys.push(route.request().headers()['idempotency-key'])
  if(keys.length===2&&!intercepted){
   intercepted=true
   // The real server commits, but the browser never receives its acknowledgement.
   expect((await route.fetch()).status()).toBe(201)
   return route.abort('failed')
  }
  return route.continue()
 })
 await importFiles(page,names)
 await expect(page.getByRole('dialog')).toContainText('Retry safely')
 await page.getByRole('button',{name:'Retry',exact:true}).click()
 await expect(page.getByText(names[2].replace(/\.txt$/, ''),{exact:true})).toBeVisible()
 const files=await(await page.request.get(`/api/cases/${id}/files`)).json()
 expect(files.filter((f:{original_filename:string})=>f.original_filename.startsWith(prefix)).map((f:{original_filename:string})=>f.original_filename).sort()).toEqual([...names].sort())
 expect(keys).toHaveLength(4);expect(keys[1]).toBe(keys[2]);expect(keys[0]).not.toBe(keys[1])
})

test('a rejected file does not block the remaining batch and identifies the failed filename',async({page})=>{
 await login(page);const id=await caseId(page.request)
 await page.getByRole('row').filter({hasText:'900001'}).dblclick()
 const prefix=`recovery-${randomUUID()}`
 const names=[`${prefix}-one.txt`,`${prefix}-too-large.txt`,`${prefix}-three.txt`]
 let count=0
 await page.route(`**/api/cases/${id}/files`,route=>{
  if(route.request().method()==='POST'&&++count===2)return route.fulfill({status:413,body:'{}'})
  return route.continue()
 })
 await importFiles(page,names)
 await expect(page.getByText(names[2].replace(/\.txt$/, ''),{exact:true})).toBeVisible()
 await expect(page.getByRole('alertdialog')).toContainText('2 of 3 files uploaded')
 await expect(page.getByRole('alertdialog')).toContainText(names[1])
 const files=await(await page.request.get(`/api/cases/${id}/files`)).json()
 expect(files.filter((f:{original_filename:string})=>f.original_filename.startsWith(prefix))).toHaveLength(2)
})

test('parallel duplicate imports and email attachments preserve one file per receipt',async({request,playwright,baseURL})=>{
 await apiLogin(request,'STAFF'); const id=await caseId(request)
 const prefix=`recovery-${randomUUID()}`
 const url=`/api/cases/${id}/files`
 const key=randomUUID()
 const upload={name:`${prefix}.eml`,mimeType:'message/rfc822',buffer:Buffer.from('From: sender@example.com\r\nSubject: large import\r\n\r\nMessage')}
 const send=()=>request.post(url,{headers:{'Idempotency-Key':key},multipart:{upload}})
 const responses=await Promise.all([send(),send(),send(),send()])
 expect(responses.every(r=>[201,429].includes(r.status()))).toBe(true)
 const parent=await(await send()).json()
 for(const response of responses)if(response.status()===201)expect((await response.json()).id).toBe(parent.id)
 const childKey=randomUUID()
 const child=()=>request.post(url,{headers:{'Idempotency-Key':childKey},multipart:{parent_file_id:parent.id,upload:{name:`${prefix}-attachment.txt`,mimeType:'text/plain',buffer:Buffer.alloc(16*1024*1024,97)}}})
 const start=Date.now()
 const first=await child();expect(first.status()).toBe(201)
 expect((await(await child()).json()).id).toBe((await first.json()).id)
 console.log(JSON.stringify({upload_and_replay_bytes:16*1024*1024,elapsed_ms:Date.now()-start}))
 expect(Date.now()-start).toBeLessThan(30000)
 expect((await request.post(url,{headers:{'Idempotency-Key':key},multipart:{upload:{...upload,buffer:Buffer.from('different')}}})).status()).toBe(409)
 const other=await playwright.request.newContext({baseURL})
 try{
  await apiLogin(other,'DENIED')
  expect((await other.post(url,{headers:{'Idempotency-Key':key},multipart:{upload}})).status()).toBe(403)
 }finally{await other.dispose()}
 const files=await(await request.get(url)).json()
 expect(files.filter((f:{original_filename:string})=>f.original_filename.startsWith(prefix))).toHaveLength(2)
})


test('a 32-file import retains every file across a mid-batch connection failure',async({page})=>{
 await login(page);const id=await caseId(page.request)
 await page.getByRole('row').filter({hasText:'900001'}).dblclick()
 const prefix=`recovery-batch-${randomUUID()}`
 const names=Array.from({length:32},(_,i)=>`${prefix}-${i}.txt`)
 let requests=0
 await page.route(`**/api/cases/${id}/files`,async route=>{
  if(route.request().method()!=='POST')return route.continue()
  if(++requests===17){expect((await route.fetch()).status()).toBe(201);return route.abort('failed')}
  return route.continue()
 })
 const start=Date.now()
 await importFiles(page,names)
 await expect(page.getByRole('dialog')).toContainText('16 file(s) completed')
 await page.getByRole('button',{name:'Retry',exact:true}).click()
 await expect(page.getByText(names[31].replace(/\.txt$/, ''),{exact:true})).toBeVisible()
 const files=await(await page.request.get(`/api/cases/${id}/files`)).json()
 expect(files.filter((f:{original_filename:string})=>f.original_filename.startsWith(prefix))).toHaveLength(32)
 expect(requests).toBe(33)
 console.log(JSON.stringify({batch_files:32,requests,elapsed_ms:Date.now()-start}))
 expect(Date.now()-start).toBeLessThan(30000)
})
