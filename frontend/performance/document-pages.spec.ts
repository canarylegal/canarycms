import {expect,test} from '@playwright/test'
import {apiLogin,caseId,login} from '../e2e/core-helpers'
import type {FileSummary} from '../src/types'
import {docListPrimaryDate} from '../src/case/docFormat'
import {fileDocOwnerLabel} from '../src/case/caseDetailHelpers'

test('document pages match complete legacy folder groups for every sort and preserve metadata',async({request})=>{
 await apiLogin(request,'STAFF');const id=await caseId(request)
 const files:FileSummary[]=await(await request.get(`/api/cases/${id}/files`)).json()
 const metadata=await(await request.get(`/api/cases/${id}/files/folder-metadata`)).json()
 for(const folder of ['',...metadata.paths]) {
   const expected=files.filter(f=>f.category!=='system'&&(f.folder_path??'')===folder)
   const ids:string[]=[];let cursor:string|null=null
   do {
     const response=await request.get(`/api/cases/${id}/files/browse`,{params:{folder,limit:37,...(cursor?{cursor}:{})}})
     expect(response.ok()).toBe(true);expect((await response.body()).length).toBeLessThan(150000)
     const data=await response.json();expect(data.items.length).toBeLessThanOrEqual(37)
     for(const item of data.items){const {group_pinned,...original}=item;expect(typeof group_pinned).toBe('boolean');expect(original).toEqual(files.find(f=>f.id===item.id));ids.push(item.id)}
     cursor=data.next_cursor
   }while(cursor)
   expect(new Set(ids)).toEqual(new Set(expected.map(f=>f.id)))
   expect(ids.length).toBe(new Set(ids).size)
 }
 const local=files.filter(f=>(f.folder_path??'')===''&&f.category!=='system')
 for(const sort of ['description','size','created','user'] as const)for(const direction of ['asc','desc']){
   const value=(f:FileSummary)=>sort==='description'?f.original_filename:sort==='size'?f.size_bytes:sort==='created'?docListPrimaryDate(f):fileDocOwnerLabel(f)
   const compare=(a:FileSummary,b:FileSummary)=>{const av=value(a),bv=value(b);return(typeof av==='number'&&typeof bv==='number'?av-bv:String(av).localeCompare(String(bv)))*(direction==='asc'?1:-1)}
   const expected:string[]=[]
   for(const pin of [true,false])for(const parent of local.filter(f=>!f.parent_file_id&&f.is_pinned===pin).sort(compare)){
     expected.push(parent.id,...local.filter(f=>f.parent_file_id===parent.id).sort(compare).map(f=>f.id))
   }
   const found:string[]=[];let cursor:string|null=null
   do{const response=await request.get(`/api/cases/${id}/files/browse`,{params:{sort,direction,limit:100,...(cursor?{cursor}:{})}});expect(response.ok()).toBe(true);const page=await response.json();found.push(...page.items.map((f:FileSummary)=>f.id));cursor=page.next_cursor}while(cursor)
   // Equal sort values have deterministic creation/id ties on the server.
   expect(found.length).toBe(expected.length)
   const actual=found.map(id=>local.find(f=>f.id===id)!)
   for(let i=0;i<actual.length;i++){
     expect(value(actual[i])).toEqual(value(local.find(f=>f.id===expected[i])!))
     expect(Boolean(actual[i].parent_file_id)).toBe(Boolean(local.find(f=>f.id===expected[i])!.parent_file_id))
   }
 }
})

test('document scrolling preserves selection and search finds an unloaded attachment group',async({page})=>{
 await login(page);await page.getByRole('textbox',{name:'Search cases',exact:true}).fill('900001')
 await page.getByRole('row').filter({hasText:'900001'}).dblclick()
 const rows=page.locator('.caseDocsScroll [data-doc-key]').filter({hasNot:page.locator('.docsFolderIcon')})
 await expect(page.locator('.caseDocsScroll .docsTr.rowbtn[data-doc-key]')).toHaveCount(120) // 100 documents + 20 child folders
 const parent=page.getByText('Performance document 0000',{exact:true})
 await parent.click()
 const selected=page.locator('.caseDocsScroll .docsTr.active').first()
 const selectedId=await selected.getAttribute('data-doc-key')
 await page.locator('.caseDocsScroll').evaluate(el=>{el.scrollTop=el.scrollHeight})
 await expect.poll(()=>page.locator('.caseDocsScroll [data-doc-key]').count()).toBeGreaterThan(120)
 await expect(page.locator(`[data-doc-key="${selectedId}"]`)).toHaveClass(/active/)
 const search=page.getByRole('textbox',{name:'Search documents',exact:true})
 await search.fill('Performance document 0201')
 await expect(page.getByText('Performance document 0200',{exact:true})).toBeVisible()
 await expect(page.getByText('Performance document 0201',{exact:true})).toBeVisible()
 expect(await rows.count()).toBeGreaterThan(0)
})
