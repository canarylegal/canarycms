import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { SessionRecovery } from './SessionRecovery'
import { rememberSessionUser, signalSessionExpired } from './sessionRecovery'
import { apiFetch } from '../api'
vi.mock('../api', () => ({ apiFetch: vi.fn(), COOKIE_SESSION_TOKEN: 'cookie' }))
beforeEach(() => { vi.resetAllMocks(); rememberSessionUser('original') })
it('keeps drafts mounted and requires the original user when checking recovery', async () => {
  render(<><input aria-label="Draft" defaultValue="unsaved work" /><SessionRecovery /></>)
  act(() => signalSessionExpired())
  expect(screen.getByRole('link', { name: 'Sign in in another tab' })).toHaveAttribute('target', '_blank')
  vi.mocked(apiFetch).mockResolvedValueOnce({ id: 'different' })
  fireEvent.click(screen.getByRole('button', { name: 'I’ve signed in' }))
  await screen.findByText(/different account/)
  expect(screen.getByLabelText('Draft')).toHaveValue('unsaved work')
  vi.mocked(apiFetch).mockResolvedValueOnce({ id: 'original' })
  fireEvent.click(screen.getByRole('button', { name: 'I’ve signed in' }))
  await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
  expect(screen.getByLabelText('Draft')).toHaveValue('unsaved work')
})

it('uses the current account after a deliberate account switch', async () => {
  render(<SessionRecovery />)
  rememberSessionUser('newly-signed-in')
  act(() => signalSessionExpired())
  vi.mocked(apiFetch).mockResolvedValueOnce({ id: 'newly-signed-in' })
  fireEvent.click(screen.getByRole('button', { name: 'I’ve signed in' }))
  await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
})
