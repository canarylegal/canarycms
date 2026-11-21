import {test,expect,type Page} from '@playwright/test'
const id='11111111-1111-4111-8111-111111111111', matter='22222222-2222-4222-8222-222222222222'
const form={id,case_id:matter,template_id:id,template_name:'Synthetic review form',template_reference:'review',contact_id:id,contact_name:'Synthetic client',status:'pending',responses:{},sent_at:'2026-11-21T12:00:00Z',completed_at:null,snapshot_file_id:null,description:'',fields:[{field_key:'answer',label:'Answer',field_type:'text',required:true,sort_order:0,select_options:[]}]}
async function setup(page: Page){
 const state={expired:false,unavailable:false,submissions:0,contactId:id,denyForm:false,authToken:'renewed-token'}
 await page.route('**/api/**',async route=>{
  const path=new URL(route.request().url()).pathname.replace(/^\/api/,'')
  const reply=(body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)})
  if(path==='/portal/config')return reply({firm_name:'Isolated review',portal_title:'Client portal',portal_logo_enabled:false})
  if(path==='/portal/form-exchange')return reply({session_token:'synthetic-token',contact_id:state.contactId,contact_name:'Synthetic client',grants:[],form})
  if(path==='/portal/auth'){state.expired=false;return reply({session_token:state.authToken,contact_id:state.contactId,contact_name:'Synthetic client',grants:[],audience:'client'})}
  if(path==='/portal/session' && state.unavailable)return reply({detail:'Temporarily unavailable'},503)
  if(state.expired)return reply({detail:'Invalid or expired portal session'},401)
  if(path==='/portal/session')return reply({contact_id:state.contactId,contact_name:'Synthetic client',grants:[],staff_preview:false,audience:'client',focus_case_id:matter})
  if(path==='/portal/forms')return reply([form])
  if(path==='/portal/quote-deliveries')return reply([])
  if(path==='/portal/client-actions')return reply({outstanding:[{kind:'form',id,title:form.template_name,status:'pending',matter_label:'Synthetic matter',badge:'Form',href_key:`form:${id}`,case_id:matter,occurred_at:form.sent_at}],complete:[],inactive:[]})
  if(path===`/portal/forms/${id}`)return state.denyForm ? reply({detail:'Access revoked'},403) : reply(form)
  if(path===`/portal/forms/${id}/submit`){state.submissions++;return reply({...form,status:'completed'})}
  return reply([])
 })
 return state
}

test('control: rejected form submission keeps current text and is not falsely confirmed',async({page})=>{
 const state=await setup(page);await page.goto('/portal?form='+id)
 await page.getByLabel(/^Answer/).fill('Unsaved confidential draft')
 state.expired=true
 await page.getByRole('button',{name:'Submit form',exact:true}).click()
 await expect(page.getByText('Invalid or expired portal session',{exact:true})).toBeVisible()
 await expect(page.getByLabel(/^Answer/)).toHaveValue('Unsaved confidential draft')
 expect(state.submissions).toBe(0)
})
test('expired submit offers a sign-in recovery action',async({page})=>{
 const state=await setup(page);await page.goto('/portal?form='+id)
 await page.getByLabel(/^Answer/).fill('Unsaved confidential draft')
 state.expired=true;await page.getByRole('button',{name:'Submit form',exact:true}).click()
 await expect(page.getByText('Invalid or expired portal session',{exact:true})).toBeVisible()
 await page.screenshot({path:test.info().outputPath('expired-submit.png'),fullPage:true})
 await expect(page.getByRole('button',{name:/^Sign in$/i})).toBeVisible()
})
test('focus-time expiry changes signed-in UI to recovery',async({page})=>{
 const state=await setup(page);await page.goto('/portal?form='+id)
 await page.getByLabel(/^Answer/).fill('Unsaved confidential draft')
 state.expired=true
 const rejected=page.waitForResponse(r=>r.url().endsWith('/portal/session') && r.status()===401)
 await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await rejected
 await page.screenshot({path:test.info().outputPath('expired-focus.png'),fullPage:true})
 await expect(page.getByRole('button',{name:/^Sign in$/i})).toBeVisible()
})
test('reauthentication preserves pending form text',async({page})=>{
 const state=await setup(page);await page.goto('/portal?form='+id)
 await page.getByLabel(/^Answer/).fill('Unsaved confidential draft')
 state.expired=true;await page.getByRole('button',{name:'Submit form',exact:true}).click()
 await expect(page.getByText('Invalid or expired portal session',{exact:true})).toBeVisible()
 await page.getByRole('button',{name:'Sign in',exact:true}).click()
 await page.getByLabel('Access code',{exact:true}).fill('SYNTHETIC-REVIEW')
 await page.getByRole('button',{name:'Sign in',exact:true}).click()
 await expect(page.getByLabel(/^Answer/)).toBeVisible()
 await page.screenshot({path:test.info().outputPath('reauthenticated-form.png'),fullPage:true})
 await expect(page.getByLabel(/^Answer/)).toHaveValue('Unsaved confidential draft')
})
test('transient session error does not erase the login token',async({page})=>{
 const state=await setup(page);state.unavailable=true
 await page.addInitScript(()=>sessionStorage.setItem('canary_portal_token','synthetic-token'))
 await page.goto('/portal')
 await expect(page.getByText('Temporarily unavailable',{exact:true})).toBeVisible()
 expect(await page.evaluate(()=>sessionStorage.getItem('canary_portal_token'))).toBe('synthetic-token')
})

for (const reason of ['different client','revoked form']) {
 test(`recovery does not restore draft for ${reason}`,async({page})=>{
  const state=await setup(page);await page.goto('/portal?form='+id)
  await page.getByLabel(/^Answer/).fill('Private retained text')
  state.expired=true;await page.getByRole('button',{name:'Submit form',exact:true}).click()
  await page.getByRole('button',{name:'Sign in',exact:true}).click()
  if(reason==='different client')state.contactId=matter
  else state.denyForm=true
  await page.getByLabel('Access code',{exact:true}).fill('SYNTHETIC-REVIEW')
  await page.getByRole('button',{name:'Sign in',exact:true}).click()
  await expect(page.getByRole('button',{name:'Sign out',exact:true})).toBeVisible()
  await expect(page.getByLabel(/^Answer/)).toHaveCount(0)
  await expect(page.getByText('Private retained text',{exact:true})).toHaveCount(0)
  expect(state.submissions).toBe(0)
 })
}
test('explicit sign out discards the draft',async({page})=>{
 const state=await setup(page);await page.goto('/portal?form='+id)
 await page.getByLabel(/^Answer/).fill('Discard this text')
 await page.getByRole('button',{name:'Sign out',exact:true}).click()
 await page.getByLabel('Access code',{exact:true}).fill('SYNTHETIC-REVIEW')
 await page.getByRole('button',{name:'Sign in',exact:true}).click()
 await page.getByText('Synthetic review form',{exact:true}).click()
 await expect(page.getByLabel(/^Answer/)).toHaveValue('')
 expect(state.submissions).toBe(0)
})
test('temporary session error can retry without signing in',async({page})=>{
 const state=await setup(page);state.unavailable=true
 await page.addInitScript(()=>sessionStorage.setItem('canary_portal_token','synthetic-token'))
 await page.goto('/portal')
 await expect(page.getByRole('button',{name:'Retry',exact:true})).toBeVisible()
 state.unavailable=false
 await page.getByRole('button',{name:'Retry',exact:true}).click()
 await expect(page.getByText('Temporarily unavailable',{exact:true})).toHaveCount(0)
 expect(await page.evaluate(()=>sessionStorage.getItem('canary_portal_token'))).toBe('synthetic-token')
})


for (const failure of ['503', 'network'] as const) {
  test(`recovery retains a quarantined draft through ${failure} and retries`, async ({page}) => {
    const state = await setup(page)
    await page.goto('/portal?form=' + id)
    await page.getByLabel(/^Answer/).fill('Retained through verification outage')
    state.expired = true
    await page.getByRole('button', {name:'Submit form', exact:true}).click()
    await page.getByRole('button', {name:'Sign in', exact:true}).click()
    let failed = false
    await page.route('**/api/portal/forms/' + id, async route => {
      if (failed) return route.fallback()
      failed = true
      if (failure === 'network') return route.abort('failed')
      return route.fulfill({status:503, contentType:'application/json', body:'{"detail":"Temporary outage"}'})
    })
    await page.getByLabel('Access code', {exact:true}).fill('SYNTHETIC-REVIEW')
    await page.getByRole('button', {name:'Sign in', exact:true}).click()
    await expect(page.getByText(/Your unsent draft is still held in this tab/)).toBeVisible()
    await expect(page.getByLabel(/^Answer/)).toHaveCount(0)
    expect(await page.evaluate(() => sessionStorage.getItem('canary_portal_token'))).toBeNull()
    await page.getByRole('button', {name:'Sign in', exact:true}).click()
    await expect(page.getByLabel(/^Answer/)).toHaveValue('Retained through verification outage')
    expect(state.submissions).toBe(0)
  })
}

for (const reuseToken of [false, true]) {
  for (const status of [200, 401, 503]) {
    test(`old action response ${status} is ignored after identity switch, reused token=${reuseToken}`, async ({page}) => {
      const state = await setup(page)
      if (reuseToken) state.authToken = 'synthetic-token'
      let release!: () => void
      let started!: () => void
      const gate = new Promise<void>(resolve => { release = resolve })
      const waiting = new Promise<void>(resolve => { started = resolve })
      const actions = (title: string) => ({outstanding:[{kind:'form', id, title, status:'pending', matter_label:'Synthetic matter', badge:'Form', href_key:`form:${id}`, case_id:matter, occurred_at:form.sent_at}], complete:[], inactive:[]})
      let delayed = false
      await page.route('**/api/portal/client-actions', async route => {
        if (!delayed) {
          delayed = true
          started()
          await gate
          return route.fulfill({status, contentType:'application/json', body:JSON.stringify(status === 200 ? actions('Previous client private action') : {detail:'Previous session failure'})})
        }
        return route.fulfill({status:200, contentType:'application/json', body:JSON.stringify(actions('Current client action'))})
      })
      await page.goto('/portal?form=' + id)
      await page.getByLabel(/^Answer/).fill('Private old draft')
      await waiting
      state.expired = true
      await page.getByRole('button', {name:'Submit form', exact:true}).click()
      await page.getByRole('button', {name:'Sign in', exact:true}).click()
      state.contactId = matter
      await page.getByLabel('Access code', {exact:true}).fill('SYNTHETIC-REVIEW')
      await page.getByRole('button', {name:'Sign in', exact:true}).click()
      await expect(page.getByText('Current client action', {exact:true})).toBeVisible()
      const response = page.waitForResponse(r => r.url().endsWith('/portal/client-actions') && r.status() === status)
      release()
      await response
      // Wait for the old response body and React's queued callbacks to be processed.
      await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))))
      await expect(page.getByText('Previous client private action', {exact:true})).toHaveCount(0)
      await expect(page.getByText('Current client action', {exact:true})).toBeVisible()
      await expect(page.getByRole('button', {name:'Sign in', exact:true})).toHaveCount(0)
      await expect(page.getByText('Previous session failure', {exact:true})).toHaveCount(0)
    })
  }
}

for (const status of [200, 401]) {
  test(`old form submission response ${status} cannot update a replacement session`, async ({page}) => {
    const state = await setup(page)
    state.authToken = 'synthetic-token'
    let release!: () => void
    let started!: () => void
    const gate = new Promise<void>(resolve => { release = resolve })
    const waiting = new Promise<void>(resolve => { started = resolve })
    await page.route('**/api/portal/forms/' + id + '/submit', async route => {
      started()
      await gate
      return route.fulfill({status, contentType:'application/json', body:JSON.stringify(status === 200 ? {...form,status:'completed'} : {detail:'Old form session expired'})})
    })
    await page.goto('/portal?form=' + id)
    await page.getByLabel(/^Answer/).fill('Old submitted text')
    await page.getByRole('button', {name:'Submit form',exact:true}).click()
    await waiting
    await page.getByRole('button', {name:'Sign out',exact:true}).click()
    state.contactId = matter
    await page.getByLabel('Access code', {exact:true}).fill('SYNTHETIC-REVIEW')
    await page.getByRole('button', {name:'Sign in',exact:true}).click()
    await expect(page.getByRole('button', {name:'Sign out',exact:true})).toBeVisible()
    const response = page.waitForResponse(r => r.url().endsWith('/submit') && r.status() === status)
    release()
    await response
    await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))))
    await expect(page.getByText('Thank you — your form has been submitted.', {exact:true})).toHaveCount(0)
    await expect(page.getByRole('button', {name:'Sign in',exact:true})).toHaveCount(0)
    await expect(page.getByText('Old form session expired', {exact:true})).toHaveCount(0)
  })
}
