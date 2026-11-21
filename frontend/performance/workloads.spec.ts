import { expect, test } from '@playwright/test'
import { performance } from 'node:perf_hooks'
import { credentials, login } from '../e2e/core-helpers'

const p95 = (values: number[]) => [...values].sort((a,b)=>a-b)[Math.ceil(values.length*0.95)-1]

test('large matter and document lists retain interactions within generous UI budgets', async ({ page }, info) => {
  const requests: string[]=[]
  page.on('request',r=>{ if(r.method()==='GET' && /\/api\/cases\/menu(?:\?|$)/.test(r.url())) requests.push(r.url()) })
  const start=performance.now()
  await login(page)
  await expect(page.locator('.casesTableScroll .tr.rowbtn')).toHaveCount(100)
  const loaded=performance.now()-start
  const scroll=page.locator('.casesTableScroll').first()
  await page.locator('.casesTableScroll .tr.rowbtn').nth(99).click()
  await page.keyboard.press('ArrowDown')
  await expect(page.locator('.casesTableScroll .tr.rowbtn')).toHaveCount(200)
  await expect(page.locator('.casesTableScroll .tr.rowbtn').nth(100)).toHaveClass(/active/)
  expect(new Set(await page.locator('[data-case-row-id]').evaluateAll(rows=>rows.map(row=>row.getAttribute('data-case-row-id')))).size).toBe(200)
  await scroll.evaluate(el => {el.scrollTop=0})
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
  expect(requests.length).toBeLessThanOrEqual(4)
})

test('four concurrent staff sessions read bounded matter pages and complete documents without errors',async({playwright,baseURL},info)=>{
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
        for(const [name,path,count] of [['matters','/api/cases/menu',100],['documents',`/api/cases/${id}/files`,1200]] as const){
          const start=performance.now();const response=await ctx.get(path)
          expect(response.status()).toBe(200);const data=await response.json();expect(name==='matters'?data.items:data).toHaveLength(count)
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


test('bounded pages traverse every matter once and match browser sorting and search', async ({request}) => {
  expect((await request.post('/api/auth/login', {data: credentials()})).ok()).toBe(true)
  const legacy = await (await request.get('/api/cases')).json()
  for (const direction of ['asc','desc']) {
    const all: {id:string;client_name:string}[]=[]
    let cursor: string | null = null
    do {
      const response=await request.get('/api/cases/menu', {params:{sort:'client',direction,...(cursor?{cursor}:{})}})
      expect(response.ok()).toBe(true)
      expect((await response.body()).length).toBeLessThan(150000)
      const data=await response.json()
      expect(data.items.length).toBeLessThanOrEqual(100)
      all.push(...data.items);cursor=data.next_cursor
    } while(cursor)
    expect(all).toHaveLength(5002)
    expect(new Set(all.map(row=>row.id)).size).toBe(5002)
    expect(new Set(all.map(row=>row.id))).toEqual(new Set(legacy.map((row:{id:string})=>row.id)))
    const labels=all.map(row=>row.client_name??'')
    expect(labels).toEqual([...labels].sort((a,b)=>a.localeCompare(b)*(direction==='asc'?1:-1)))
  }
  const response=await request.get('/api/cases/menu',{params:{q:'Synthetic client 04999',status:'closed'}})
  expect(response.ok()).toBe(true)
  const found=await response.json()
  expect(found.items).toHaveLength(1) // Search overrides the saved status filter.
  expect(found.next_cursor).toBeNull()
  expect((await request.get('/api/cases/menu?limit=101')).status()).toBe(422)
  expect((await request.get('/api/cases/menu?cursor=invalid')).status()).toBe(400)
})
