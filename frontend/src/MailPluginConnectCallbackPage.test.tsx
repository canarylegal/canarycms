import { StrictMode } from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Callback from './MailPluginConnectCallbackPage'
beforeEach(() => { vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {}) })
afterEach(() => { cleanup(); vi.restoreAllMocks() })
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

it('automatically hands off once under StrictMode, after clearing the code from history', () => {
  const click = vi.mocked(HTMLAnchorElement.prototype.click)
  click.mockImplementation(() => { expect(window.location.hash).toBe('') })
  window.history.replaceState(null, '', '/connect/mail-plugin/callback#' + new URLSearchParams({client:'thunderbird',state:'s'.repeat(32),code:'a'.repeat(43)}))
  render(<StrictMode><Callback /></StrictMode>)
  expect(click).toHaveBeenCalledTimes(1)
  expect(screen.getByRole('link', {name:'Open Thunderbird'})).toBeTruthy()
})
it('retains manual fallback when automatic launch fails', () => {
  vi.mocked(HTMLAnchorElement.prototype.click).mockImplementation(() => { throw new Error('Browser blocked launch') })
  window.history.replaceState(null, '', '/connect/mail-plugin/callback#' + new URLSearchParams({client:'thunderbird',state:'synthetic',code:'a'.repeat(43)}))
  render(<Callback />)
  expect(screen.getByRole('link', {name:'Open Thunderbird'})).toBeTruthy()
})
it('does not launch Thunderbird for an invalid callback or Outlook', () => {
  window.history.replaceState(null, '', '/connect/mail-plugin/callback?client=thunderbird&state=synthetic')
  const view = render(<Callback />)
  expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled()
  view.unmount()
  window.history.replaceState(null, '', '/connect/mail-plugin/callback?client=outlook&state=synthetic')
  render(<Callback />)
  expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled()
})
