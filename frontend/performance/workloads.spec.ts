import { expect, test } from '@playwright/test'
import { performance } from 'node:perf_hooks'
import { credentials, login } from '../e2e/core-helpers'

const p95 = (values: number[]) => [...values].sort((a,b)=>a-b)[Math.ceil(values.length*0.95)-1]

test('large matter and document lists retain interactions within generous UI budgets', async ({ page }, info) => {
  const requests: string[]=[]
  page.on('request',r=>{ if(r.method()==='GET' && /\/api\/cases(?:\?|$)/.test(r.url())) requests.push(r.url()) })
  const start=performance.now()
  await login(page)
  await expect(page.locator('.casesTableScroll .tr.rowbtn')).toHaveCount(5002)
  const loaded=performance.now()-start
  const sortStart=performance.now()
  await page.locator('.casesTableScroll .tr.th').getByRole('button',{name:/^Fee earner$/i}).click()
  await expect(page.locator('.casesTableScroll .tr.rowbtn').first().locator('.td').nth(3)).toHaveText('Synthetic Fee Earner 000')
  const sorted=performance.now()-sortStart
  const search=page.getByRole('textbox',{name:'Search cases',exact:true})
  const searchStart=performance.now()
  await search.fill('900001')
  await expect(page.locator('.casesTableScroll .tr.rowbtn')).toHaveCount(1)
  const searched=performance.now()-searchStart
  const row=page.getByRole('row').filter({hasText:'900001'})
  await row.click({button:'right'})
  await expect(page.getByRole('menuitem',{name:'Open',exact:true})).toBeVisible()
  await page.keyboard.press('Escape')
  const openStart=performance.now()
  await row.dblclick()
  await expect(page.getByRole('heading',{name:'CI Core Workflows',exact:true})).toBeVisible()
  await expect(page.getByText('Performance document 0000',{exact:true})).toBeVisible()
  const opened=performance.now()-openStart
  const file=page.getByText('Performance document 0000',{exact:true})
  await file.click({button:'right'})
  await expect(page.getByRole('menuitem',{name:'Download',exact:true})).toBeVisible()
  await page.keyboard.press('Escape')
  await page.getByText('Folder 00',{exact:true}).dblclick()
  await expect(page.getByText('Section 0',{exact:true})).toBeVisible()
  const devtools=await page.context().newCDPSession(page)
  await devtools.send('Performance.enable')
  const {metrics}=await devtools.send('Performance.getMetrics')
  const heap=metrics.find(metric=>metric.name==='JSHeapUsedSize')?.value ?? 0
  await devtools.detach()
  const report={renderer_heap_bytes:heap,matters:5002,documents:1200,initial_load_ms:loaded,fee_earner_sort_ms:sorted,search_ms:searched,open_matter_ms:opened,matter_list_requests:requests.length}
  await info.attach('browser-metrics.json',{body:JSON.stringify(report,null,2),contentType:'application/json'})
  console.log(JSON.stringify(report))
  expect(loaded).toBeLessThan(15000)
  expect(sorted).toBeLessThan(5000)
  expect(searched).toBeLessThan(5000)
  expect(opened).toBeLessThan(10000)
  expect(requests.length).toBeLessThanOrEqual(3)
})

test('four concurrent staff sessions read complete large lists without errors',async({playwright,baseURL},info)=>{
  const contexts=await Promise.all(Array.from({length:4},()=>playwright.request.newContext({baseURL})))
  const times:Record<string,number[]>={matters:[],documents:[]}
  try {
    await Promise.all(contexts.map(async (ctx,index)=>{
      const auth=await ctx.post('/api/auth/login',{data:{email:`performance-${index}@example.com`,password:credentials().password}})
      expect(auth.status()).toBe(200)
      const response=await ctx.get('/api/cases?q=900001&limit=1')
      expect(response.ok()).toBe(true)
      const matches=await response.json();expect(matches).toHaveLength(1)
      const id=matches[0].id
      for(let i=0;i<5;i++) {
        for(const [name,path,count] of [['matters','/api/cases',5002],['documents',`/api/cases/${id}/files`,1200]] as const){
          const start=performance.now();const response=await ctx.get(path)
          expect(response.status()).toBe(200);expect(await response.json()).toHaveLength(count)
          times[name].push(performance.now()-start)
        }
      }
    }))
  } finally { await Promise.all(contexts.map(ctx=>ctx.dispose())) }
  const report=Object.fromEntries(Object.entries(times).map(([key,values])=>[key,{requests:values.length,p95_ms:p95(values),max_ms:Math.max(...values)}]))
  await info.attach('concurrency-metrics.json',{body:JSON.stringify(report,null,2),contentType:'application/json'})
  console.log(JSON.stringify(report))
  for(const values of Object.values(times)) expect(p95(values)).toBeLessThan(5000)
})
