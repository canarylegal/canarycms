import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { useAuth } from './useAuth'
import { apiFetch } from '../api'
import { startAuthentication } from '@simplewebauthn/browser'
vi.mock('../api', () => ({ apiFetch: vi.fn(), COOKIE_SESSION_TOKEN: 'cookie' }))
vi.mock('@simplewebauthn/browser', () => ({ startAuthentication: vi.fn() }))
afterEach(() => { cleanup(); vi.resetAllMocks() })
it('refreshes second-factor state when the cookie marker is already set', async () => {
  let verified = false
  vi.mocked(apiFetch).mockImplementation(async (path) => {
    if (path === '/auth/me') return { email: 'staff@example.test', session_second_factor_verified: verified } as never
    if (path === '/auth/webauthn/login/finish') verified = true
    return {} as never
  })
  vi.mocked(startAuthentication).mockResolvedValue({ id: 'synthetic' } as never)
  const { result } = renderHook(() => useAuth())
  await waitFor(() => expect(result.current.me?.session_second_factor_verified).toBe(false))
  await act(async () => { await result.current.loginWithPasskey('staff@example.test') })
  expect(result.current.me?.session_second_factor_verified).toBe(true)
  expect(result.current.token).toBe('cookie')
})
