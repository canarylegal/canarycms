import { beforeEach, expect, it, vi } from 'vitest'
import { webcrypto } from 'node:crypto'
import { documentOperationRetry } from './documentOperationRetry'
beforeEach(() => { vi.stubGlobal('crypto', webcrypto); sessionStorage.clear() })
it('retains uncertain identities and releases only after a valid success response', async () => {
  const path='/cases/one/files/compose-office'
  const first=await documentOperationRetry(path,'POST','{"name":"one"}')
  const retry=await documentOperationRetry(path,'POST','{"name":"one"}')
  expect(retry?.key).toBe(first?.key)
  retry?.complete('<html>proxy response</html>')
  expect((await documentOperationRetry(path,'POST','{"name":"one"}'))?.key).toBe(first?.key)
  retry?.complete({id:'saved'})
  expect((await documentOperationRetry(path,'POST','{"name":"one"}'))?.key).not.toBe(first?.key)
})
it('does not reuse keys for changed content or unrelated operations', async () => {
  const a=await documentOperationRetry('/cases/two/files/compose-office','POST','a')
  const b=await documentOperationRetry('/cases/two/files/compose-office','POST','b')
  expect(a?.key).not.toBe(b?.key)
  expect(await documentOperationRetry('/cases/two/files','GET',undefined)).toBeNull()
  expect(await documentOperationRetry('/cases/two/invoices','POST','a')).toBeNull()
})
