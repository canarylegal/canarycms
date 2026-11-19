import { afterEach, expect, it, vi } from 'vitest'
import { apiFetch } from './api'
afterEach(() => vi.unstubAllGlobals())
it('preserves the server request ID on existing error objects', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"detail":"Internal server error"}', {
    status: 500, headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'diagnostic-reference' },
  })))
  await expect(apiFetch('/documents')).rejects.toMatchObject({ status: 500, requestId: 'diagnostic-reference', message: 'Internal server error' })
})
