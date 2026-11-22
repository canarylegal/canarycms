import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import Page from './MailPluginConnectPage'
import { apiFetch } from './api'
import { startAuthentication } from '@simplewebauthn/browser'
vi.mock('./api', () => ({ apiFetch: vi.fn(), COOKIE_SESSION_TOKEN: 'cookie' }))
vi.mock('@simplewebauthn/browser', () => ({ startAuthentication: vi.fn() }))
vi.mock('./AppLogo', () => ({ AppLogo: () => null }))
afterEach(() => { cleanup(); vi.resetAllMocks() })
it.each(['outlook', 'thunderbird'])('verifies an existing password session before authorizing %s', async (client) => {
  window.history.replaceState(null, '', '/connect/mail-plugin?' + new URLSearchParams({ client, state: 's'.repeat(32), redirect_uri: 'https://canary.test/callback' }))
  let verified = false
  vi.mocked(apiFetch).mockImplementation(async (path) => {
    if (path === '/auth/me') return { email: 'staff@example.test', session_second_factor_verified: verified } as never
    if (path === '/auth/webauthn/login/finish') verified = true
    return {} as never
  })
  vi.mocked(startAuthentication).mockResolvedValue({ id: 'synthetic' } as never)
  render(<Page />)
  fireEvent.click(await screen.findByRole('button', { name: 'Verify with passkey' }))
  expect(await screen.findByRole('button', { name: 'Authorise ' + (client === 'outlook' ? 'Outlook' : 'Thunderbird') })).toBeEnabled()
  expect(screen.queryByRole('button', { name: 'Verify with passkey' })).toBeNull()
  expect(apiFetch).not.toHaveBeenCalledWith('/auth/plugin/authorize', expect.anything())
})
