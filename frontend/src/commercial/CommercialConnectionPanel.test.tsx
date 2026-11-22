import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { CommercialConnectionPanel } from './CommercialConnectionPanel'
import { apiFetch } from '../api'
vi.mock('../api', () => ({ apiFetch: vi.fn() }))
const api = vi.mocked(apiFetch)
const offline = { enabled: true, connected: false, version: 0, installation_id: null, tenant_id: null, contract_version: '1' }
beforeEach(() => api.mockReset())
afterEach(cleanup)

it('stays hidden when the foundation is disabled', async () => {
  api.mockResolvedValue({ ...offline, enabled: false })
  const { container } = render(<CommercialConnectionPanel token="admin" />)
  await waitFor(() => expect(api).toHaveBeenCalledTimes(1))
  expect(container).toBeEmptyDOMElement()
})

it('clears the activation code on submit and displays confirmed status', async () => {
  api.mockResolvedValueOnce(offline).mockResolvedValueOnce({ ...offline, connected: true, version: 1, installation_id: 'synthetic' })
  render(<CommercialConnectionPanel token="admin" />)
  const input = await screen.findByLabelText('Commercial activation code')
  fireEvent.change(input, { target: { value: 'synthetic-secret' } })
  fireEvent.click(screen.getByRole('button', { name: 'Connect Commercial' }))
  expect(input).toHaveValue('')
  await screen.findByRole('button', { name: 'Disconnect hosted service locally' })
  expect(api).toHaveBeenLastCalledWith('/commercial-connection/activate', { token: 'admin', method: 'POST', json: { expected_version: 0, activation_code: 'synthetic-secret' } })
  expect(screen.queryByDisplayValue('synthetic-secret')).toBeNull()
})

it('does not infer success or display remote errors after an uncertain response', async () => {
  api.mockResolvedValueOnce(offline).mockRejectedValueOnce(new Error('sensitive remote response')).mockResolvedValueOnce(offline)
  render(<CommercialConnectionPanel token="admin" />)
  fireEvent.change(await screen.findByLabelText('Commercial activation code'), { target: { value: 'code' } })
  fireEvent.click(screen.getByRole('button', { name: 'Connect Commercial' }))
  await screen.findByRole('alert')
  expect(screen.getByRole('alert')).not.toHaveTextContent('sensitive')
  await waitFor(() => expect(api).toHaveBeenCalledTimes(3))
  expect(screen.getByText('Not connected')).toBeVisible()
})

it('ignores an old connection response after a session change', async () => {
  let resolve!: (value: unknown) => void
  api.mockResolvedValueOnce(offline).mockImplementationOnce(() => new Promise(r => { resolve = r })).mockResolvedValueOnce({ ...offline, enabled: false })
  const { rerender, container } = render(<CommercialConnectionPanel token="old" />)
  fireEvent.change(await screen.findByLabelText('Commercial activation code'), { target: { value: 'code' } })
  fireEvent.click(screen.getByRole('button', { name: 'Connect Commercial' }))
  rerender(<CommercialConnectionPanel token="new" />)
  await waitFor(() => expect(api).toHaveBeenCalledTimes(3))
  await act(async () => resolve({ ...offline, connected: true, installation_id: 'old-installation' }))
  expect(container).toBeEmptyDOMElement()
})
