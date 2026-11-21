import {test,expect} from '@playwright/test'
import {login} from '../e2e/core-helpers'

test('large document browsing has bounded rendering and preserves interaction state',async({page},info)=>{
 test.setTimeout(180000)
 await login(page)
 await page.getByRole('textbox',{name:'Search cases',exact:true}).fill('900002')
 let loaded=0
 // Count actual data, independent of whether every row is mounted in the DOM.
 page.on('response',async response=>{
  if(response.url().includes('/files/browse?')&&response.ok())loaded+=(await response.json()).items.length
 })
 await page.getByRole('row').filter({hasText:'900002'}).dblclick()
 const scroll=page.locator('.caseDocsScroll')
 const rows=scroll.locator('[data-doc-key]')
 await expect(page.getByText('Large document 00000',{exact:true})).toBeVisible()
 const preferences=(await(await page.request.get('/api/auth/me')).json()).ui_preferences
 const firstKey=await rows.first().getAttribute('data-doc-key')
 await rows.first().click()
 const start=Date.now()
 for(let n=0;n<40&&loaded<2000;n++){
  const previous=loaded
  await scroll.evaluate(el=>{el.scrollTop=el.scrollHeight})
  await expect.poll(()=>loaded,{timeout:15000}).toBeGreaterThan(previous)
 }
 const cdp=await page.context().newCDPSession(page)
 await cdp.send('HeapProfiler.collectGarbage')
 const dom=await cdp.send('Memory.getDOMCounters')
 const heap=await cdp.send('Runtime.getHeapUsage')
 const report={loaded,rendered_rows:await rows.count(),dom_nodes:dom.nodes,heap_bytes:heap.usedSize,load_2000_ms:Date.now()-start}
 console.log(JSON.stringify(report))
 await info.attach('large-documents.json',{body:JSON.stringify(report),contentType:'application/json'})
 await cdp.detach()
 if(!process.env.LARGE_DOCUMENT_BASELINE){
  expect(report.rendered_rows).toBeLessThan(100)
  expect(report.dom_nodes).toBeLessThan(5000)
  expect(report.heap_bytes).toBeLessThan(100*1024*1024)
  expect(report.load_2000_ms).toBeLessThan(30000)
 }
 if(!process.env.LARGE_DOCUMENT_BASELINE){
  const fullStart=Date.now()
  for(let n=0;n<110&&loaded<10000;n++){
   const previous=loaded
   await scroll.evaluate(el=>{el.scrollTop=el.scrollHeight})
   await expect.poll(()=>loaded,{timeout:15000}).toBeGreaterThan(previous)
  }
  expect(loaded).toBe(10000)
  const fullCdp=await page.context().newCDPSession(page)
  await fullCdp.send('HeapProfiler.collectGarbage')
  const fullDom=await fullCdp.send('Memory.getDOMCounters')
  const fullHeap=await fullCdp.send('Runtime.getHeapUsage')
  const fullReport={loaded,rendered_rows:await rows.count(),dom_nodes:fullDom.nodes,heap_bytes:fullHeap.usedSize,remaining_load_ms:Date.now()-fullStart}
  console.log(JSON.stringify({full_root:fullReport}))
  await info.attach('large-documents-full-root.json',{body:JSON.stringify(fullReport),contentType:'application/json'})
  expect(fullReport.rendered_rows).toBeLessThan(100)
  expect(fullReport.dom_nodes).toBeLessThan(5000)
  expect(fullReport.heap_bytes).toBeLessThan(100*1024*1024)
  expect(fullReport.remaining_load_ms).toBeLessThan(60000)
  await fullCdp.detach()
  // Focus was left on the first document while scrolling. Arrow Down must bring
  // its off-screen successor back into the rendered window.
  await scroll.focus();await page.keyboard.press('ArrowDown')
  await expect(scroll.locator('.docsTr--focused')).toBeVisible()
  await expect.poll(()=>scroll.evaluate(el=>el.scrollTop)).toBeLessThan(200)
  await scroll.evaluate(el=>{el.scrollTop=0})
  const parent=scroll.locator(`[data-doc-key="${firstKey}"]`)
  await parent.click()
  const second=rows.nth(1);const secondKey=await second.getAttribute('data-doc-key')
  await second.click({modifiers:['Control']})
  await scroll.evaluate(el=>{el.scrollTop=el.scrollHeight})
  await expect(parent).toHaveCount(0)
  await scroll.evaluate(el=>{el.scrollTop=0})
  await expect(parent).toHaveClass(/active/)
  await expect(scroll.locator(`[data-doc-key="${secondKey}"]`)).toHaveClass(/active/)
  await page.setViewportSize({width:900,height:700})
  await expect(parent).toBeVisible()
  await parent.click({button:'right'})
  await expect(page.getByRole('menuitem',{name:'Download 2 files',exact:true})).toBeVisible()
  await page.keyboard.press('Escape')
  await page.screenshot({path:info.outputPath('large-document-window.png')})
  await scroll.evaluate(el=>{el.scrollTop=el.scrollHeight/2})
  const visibleFiles=scroll.locator('[data-doc-key]:not([data-doc-key^="folder:"])')
  await expect(visibleFiles.last()).toBeVisible()
  // Clicking an overscan row scrolls the window and changes which row is last.
  // Keep the same document identity for selection and its context menu.
  const rangeEndKey=await visibleFiles.last().getAttribute('data-doc-key')
  const rangeEnd=scroll.locator(`[data-doc-key="${rangeEndKey}"]`)
  await rangeEnd.click({modifiers:['Control','Shift']})
  await expect(rangeEnd).toHaveClass(/active/)
  await rangeEnd.click({button:'right'})
  await expect(page.getByRole('menuitem',{name:/^Download [0-9]+ files$/})).toBeVisible()
  await page.keyboard.press('Escape')
  const search=page.getByRole('textbox',{name:'Search documents',exact:true})
  await search.fill('Large document 09999')
  await expect(scroll.locator('[data-loaded-rows]')).toHaveAttribute('data-loaded-rows','41')
  await expect(page.getByText('Large document 09999',{exact:true})).toBeVisible()
  await search.clear()
  await expect(page.getByText('Large document 00000',{exact:true})).toBeVisible()
  expect((await(await page.request.get('/api/auth/me')).json()).ui_preferences).toEqual(preferences)
 }
})

test('large attachment searches traverse the complete group across page boundaries',async({request})=>{
 const {apiLogin,caseId}=await import('../e2e/core-helpers')
 await apiLogin(request,'STAFF');const id=await caseId(request,'900002')
 for(const sort of ['created','description']){
  let cursor:string|null=null;const names:string[]=[];const ids=new Set<string>()
  do{
   const response=await request.get(`/api/cases/${id}/files/browse`,{params:{q:'Large document 00001',sort,direction:'asc',...(cursor?{cursor}:{})}})
   expect(response.ok()).toBe(true)
   const result=await response.json()
   expect(result.items.length).toBeLessThanOrEqual(100)
   for(const row of result.items){expect(ids.has(row.id)).toBe(false);ids.add(row.id);names.push(row.original_filename);expect(row.group_pinned).toBe(true)}
   cursor=result.next_cursor
   expect(names.length).toBeLessThanOrEqual(2001)
  }while(cursor)
  expect(names).toEqual(Array.from({length:2001},(_,i)=>`Large document ${String(i).padStart(5,'0')}.txt`))
 }
 const deep=['Branch 39',...Array.from({length:20},(_,i)=>`Level ${String(i+1).padStart(2,'0')}`)].join('/')
 const folder=await(await request.get(`/api/cases/${id}/files/browse`,{params:{folder:deep}})).json()
 expect(folder.items).toHaveLength(50)
 expect(folder.next_cursor).toBeNull()
 expect(folder.items.every((f:{folder_path:string})=>f.folder_path===deep)).toBe(true)
 const metadata=await(await request.get(`/api/cases/${id}/files/folder-metadata`)).json()
 expect(metadata.paths).toHaveLength(840)
 expect(metadata.summaries[deep]).toBe('50 items, 0 subfolders')
})
