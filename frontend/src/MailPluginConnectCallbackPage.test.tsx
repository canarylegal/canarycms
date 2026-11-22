import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import Callback from './MailPluginConnectCallbackPage'
afterEach(cleanup)
it('offers a state-bound Thunderbird handoff and removes code from browser URL', () => {
  const code = 'a'.repeat(43)
  window.history.replaceState(null, '', '/connect/mail-plugin/callback#' + new URLSearchParams({client:'thunderbird',state:'s'.repeat(32),code}))
  render(<Callback />)
  const link = screen.getByRole('link', {name:'Open Thunderbird'}) as HTMLAnchorElement
  const target = new URL(link.href)
  expect(target.protocol).toBe('ext+canary:')
  expect(target.pathname).toBe('auth')
  expect(target.searchParams.get('code')).toBe(code)
  expect(target.searchParams.get('state')).toBe('s'.repeat(32))
  expect(target.searchParams.get('origin')).toBe(window.location.origin)
  expect(window.location.hash).toBe('')
  expect(window.location.search).toBe('')
  expect(screen.queryByText('Thunderbird connected')).toBeNull()
})
it('rejects a missing code instead of claiming success', () => {
  window.history.replaceState(null, '', '/connect/mail-plugin/callback?client=thunderbird&state=synthetic')
  render(<Callback />)
  expect(screen.getByText('Connection failed')).toBeTruthy()
  expect(screen.queryByRole('link')).toBeNull()
})
