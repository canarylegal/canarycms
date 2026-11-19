import { afterEach, describe, expect, it, vi } from 'vitest'
import { documentRequest } from './documentRequests'
import { uploadFilesToCaseFolder } from './documentTransferOps'

afterEach(() => vi.unstubAllGlobals())
const read = (r: Response) => r.text()

describe('document request recovery', () => {
  it('retries a transient read once and returns its body', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(new Response('<html>proxy</html>', { status: 503 })).mockResolvedValueOnce(new Response('document'))
    vi.stubGlobal('fetch', fetch)
    expect(await documentRequest('/document', '', read)).toBe('document')
    expect(fetch).toHaveBeenCalledTimes(2)
  })
  it.each([401, 403, 404])('does not retry status %s or clear the session', async (status) => {
    localStorage.setItem('token', 'keep-session-context')
    const fetch = vi.fn().mockResolvedValue(new Response('internal details', { status }))
    vi.stubGlobal('fetch', fetch)
    await expect(documentRequest('/document', '', read)).rejects.toMatchObject({ status, retryable: false })
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(localStorage.getItem('token')).toBe('keep-session-context')
    localStorage.removeItem('token')
  })
  it('bounds repeated read failures and hides proxy HTML', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('<html>private proxy internals</html>', { status: 502 }))
    vi.stubGlobal('fetch', fetch)
    await expect(documentRequest('/document', '', read)).rejects.toThrow('temporarily unavailable')
    expect(fetch).toHaveBeenCalledTimes(2)
  })
  it('does not automatically replay an upload whose response was lost', async () => {
    const fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    vi.stubGlobal('fetch', fetch)
    await expect(documentRequest('/document', '', read, { method: 'POST' })).rejects.toMatchObject({ retryable: false, message: expect.stringContaining('before importing') })
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('times out while reading a stalled body, not just waiting for headers', async () => {
    const fetch = vi.fn((_url, options: RequestInit) => Promise.resolve({ ok: true, text: () => new Promise((_resolve, reject) => options.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))) }))
    vi.stubGlobal('fetch', fetch)
    await expect(documentRequest('/document', '', read, { timeoutMs: 10 })).rejects.toThrow('timed out')
    expect(fetch).toHaveBeenCalledTimes(2)
  })
  it('resumes a rejected batch without repeating the acknowledged first file', async () => {
    const names: string[] = []
    let rejectSecond = true
    vi.stubGlobal('fetch', vi.fn((_url, options: RequestInit) => {
      const file = (options.body as FormData).get('upload') as File
      names.push(file.name)
      if (file.name === 'two.txt' && rejectSecond) { rejectSecond = false; return Promise.resolve(new Response('', { status: 429 })) }
      return Promise.resolve(new Response('{}'))
    }))
    const files = [new File(['one'], 'one.txt'), new File(['two'], 'two.txt')]
    const progress = { completed: 0 }
    await expect(uploadFilesToCaseFolder('case', '', 'original-folder', files, progress)).rejects.toMatchObject({ status: 429 })
    expect(progress.completed).toBe(1)
    await uploadFilesToCaseFolder('case', '', 'original-folder', files, progress)
    expect(names).toEqual(['one.txt', 'two.txt', 'two.txt'])
    expect(progress.completed).toBe(2)
  })
})
