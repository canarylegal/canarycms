import { afterEach, expect, it, vi } from 'vitest'
import { apiFetch } from './api'
import { SESSION_EXPIRED } from './auth/sessionRecovery'
afterEach(() => vi.unstubAllGlobals())
it('signals an expired session without navigation or silently retrying a mutation', async () => {
  const expired = vi.fn()
  window.addEventListener(SESSION_EXPIRED, expired)
  const fetch = vi.fn().mockResolvedValue(new Response('{"detail":"expired"}', { status: 401 }))
  vi.stubGlobal('fetch', fetch)
  try {
    await expect(apiFetch('/cases/example', { method: 'PATCH', json: { title: 'draft' } })).rejects.toMatchObject({ status: 401 })
    expect(expired).toHaveBeenCalledOnce()
    expect(fetch).toHaveBeenCalledOnce()
  } finally { window.removeEventListener(SESSION_EXPIRED, expired) }
})
it('does not signal expiry for a wrong sign-in password', async () => {
  const expired = vi.fn(); window.addEventListener(SESSION_EXPIRED, expired)
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 401 })))
  try { await expect(apiFetch('/auth/login', { method: 'POST' })).rejects.toMatchObject({ status: 401 }); expect(expired).not.toHaveBeenCalled() }
  finally { window.removeEventListener(SESSION_EXPIRED, expired) }
})
