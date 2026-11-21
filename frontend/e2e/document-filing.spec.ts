import { expect, test } from '@playwright/test'
import { apiLogin, caseId } from './core-helpers'
import { randomUUID } from 'node:crypto'

test('creation and filing retries preserve one document and its original bytes', async ({ request }) => {
  await apiLogin(request,'APPROVER')
  const cid=await caseId(request)
  const headers={'X-Document-Operation-ID':randomUUID()}
  const data={original_filename:'Filing regression.docx',compose_office_role:'document'}
  const created=await request.post(`/api/cases/${cid}/files/compose-office`,{data,headers})
  expect(created.status(),await created.text()).toBe(201)
  const first=await created.json()
  const retry=await request.post(`/api/cases/${cid}/files/compose-office`,{data,headers})
  expect(retry.status(),await retry.text()).toBe(201)
  expect((await retry.json()).id).toBe(first.id)
  const download=await request.get(`/api/cases/${cid}/files/${first.id}`)
  expect(download.status()).toBe(200)
  const bytes=await download.body()
  const renameHeaders={'X-Document-Operation-ID':randomUUID()}
  const rename={original_filename:'Filed regression.docx',expected_original_filename:first.original_filename}
  for(let i=0;i<2;i++){
    const result=await request.patch(`/api/cases/${cid}/files/${first.id}/rename`,{headers:renameHeaders,data:rename})
    expect(result.status(),await result.text()).toBe(200)
  }
  const after=await request.get(`/api/cases/${cid}/files/${first.id}`)
  expect(after.status()).toBe(200)
  expect(await after.body()).toEqual(bytes)
})
