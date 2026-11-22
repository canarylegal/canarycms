import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { CommercialConnectionPanel } from './CommercialConnectionPanel'
import { apiFetch } from '../api'
vi.mock('../api', () => ({ apiFetch: vi.fn() }))
const api = vi.mocked(apiFetch)
const offline = { enabled: true, connected: false, version: 0, installation_id: null, tenant_id: null, contract_version: '1' }
beforeEach(() => { api.mockReset() })
afterEach(cleanup)

it('shows the licence landing page with activation disabled', async () => {
  api.mockResolvedValue({ ...offline, enabled: false })
  render(<CommercialConnectionPanel token="admin" />)
  await screen.findByLabelText('Canary Commercial licence key')
  expect(screen.getByLabelText('Canary Commercial licence key')).toBeDisabled()
})

it('clears the activation code on submit and displays confirmed status', async () => {
  api.mockResolvedValueOnce(offline).mockResolvedValueOnce({ ...offline, connected: true, version: 1, installation_id: 'synthetic' })
  render(<CommercialConnectionPanel token="admin" />)
  const input = await screen.findByLabelText('Canary Commercial licence key')
  fireEvent.change(input, { target: { value: 'synthetic-secret' } })
  fireEvent.click(screen.getByRole('button', { name: 'Activate licence' }))
  expect(input).toHaveValue('')
  await screen.findByRole('button', { name: 'Disconnect hosted service locally' })
  expect(api).toHaveBeenLastCalledWith('/commercial-connection/activate', { token: 'admin', method: 'POST', json: { expected_version: 0, activation_code: 'synthetic-secret' } })
  expect(screen.queryByDisplayValue('synthetic-secret')).toBeNull()
})

it('does not infer success or display remote errors after an uncertain response', async () => {
  api.mockResolvedValueOnce(offline).mockRejectedValueOnce(new Error('sensitive remote response')).mockResolvedValueOnce(offline)
  render(<CommercialConnectionPanel token="admin" />)
  fireEvent.change(await screen.findByLabelText('Canary Commercial licence key'), { target: { value: 'code' } })
  fireEvent.click(screen.getByRole('button', { name: 'Activate licence' }))
  await screen.findByRole('alert')
  expect(screen.getByRole('alert')).not.toHaveTextContent('sensitive')
  await waitFor(() => expect(api).toHaveBeenCalledTimes(3))
  expect(screen.getByText('Not activated')).toBeVisible()
})

it('ignores an old connection response after a session change', async () => {
  let resolve!: (value: unknown) => void
  api.mockResolvedValueOnce(offline).mockImplementationOnce(() => new Promise(r => { resolve = r })).mockResolvedValueOnce({ ...offline, enabled: false })
  const { rerender } = render(<CommercialConnectionPanel token="old" />)
  fireEvent.change(await screen.findByLabelText('Canary Commercial licence key'), { target: { value: 'code' } })
  fireEvent.click(screen.getByRole('button', { name: 'Activate licence' }))
  rerender(<CommercialConnectionPanel token="new" />)
  await waitFor(() => expect(api).toHaveBeenCalledTimes(3))
  await act(async () => resolve({ ...offline, connected: true, installation_id: 'old-installation' }))
  expect(screen.getByLabelText('Canary Commercial licence key')).toBeDisabled()
})

it('replaces a key using the current version and clears it afterward', async () => {
  api.mockResolvedValueOnce({ ...offline, connected: true, version: 3 }).mockResolvedValueOnce({ ...offline, connected: true, version: 4 })
  render(<CommercialConnectionPanel token="admin" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Replace licence key' }))
  fireEvent.change(screen.getByLabelText('Canary Commercial licence key'), { target: { value: 'replacement-secret' } })
  fireEvent.click(screen.getByRole('button', { name: 'Replace licence key' }))
  await waitFor(() => expect(api).toHaveBeenLastCalledWith('/commercial-connection/activate', { token: 'admin', method: 'POST', json: { expected_version: 3, activation_code: 'replacement-secret' } }))
  expect(screen.queryByDisplayValue('replacement-secret')).toBeNull()
})

it('retains activation controls and records a refresh failure without clearing status', async () => {
  api.mockResolvedValueOnce({ ...offline, connected: true, version: 2 }).mockRejectedValueOnce(new Error('offline'))
  render(<CommercialConnectionPanel token="admin" />)
  await screen.findByText('Activation recorded on this installation')
  fireEvent.click(screen.getByRole('button', { name: 'Refresh connection status' }))
  await screen.findByRole('alert')
  expect(screen.getByText('Activation recorded on this installation')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Disconnect hosted service locally' })).toBeVisible()
})
