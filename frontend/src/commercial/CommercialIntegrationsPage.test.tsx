import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { apiFetch } from '../api'
import { CommercialIntegrationsPage } from './CommercialIntegrationsPage'
vi.mock('../api', () => ({ apiFetch: vi.fn() }))
vi.mock('./CommercialSlotHosts', () => ({ CommercialAdminIntegrationsSlot: () => <div>Existing provider controls</div> }))
const api = vi.mocked(apiFetch)
const connection = { enabled: false, connected: false, version: 0, installation_id: null, tenant_id: null, contract_version: '1' }
const pkg = { attached: true, compatible: true, loaded: true, fault: false, products: ['hmlr'] }
beforeEach(() => { api.mockReset() })
afterEach(cleanup)

it('offers a licence overview on Core-only installations', async () => {
  api.mockImplementation(async path => path === '/commercial-package/status' ? { ...pkg, attached: false, loaded: false } : connection)
  render(<CommercialIntegrationsPage token="admin" />)
  expect(await screen.findByLabelText('Canary Commercial licence key')).toBeDisabled()
  expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.queryByRole('tab', { name: 'Provider settings' })).toBeNull()
})

it('disables provider settings without a validated licence', async () => {
  api.mockImplementation(async path => path === '/commercial-package/status' ? pkg : connection)
  render(<CommercialIntegrationsPage token="admin" />)
  const tab = await screen.findByRole('tab', { name: 'Provider settings' })
  expect(tab).toBeDisabled()
  fireEvent.click(tab)
  expect(screen.queryByText('Existing provider controls')).toBeNull()
  expect(screen.queryByText(/Connect your self-hosted Canary installation/)).toBeNull()
})

it('keeps provider settings locked when connection status is unavailable', async () => {
  api.mockImplementation(async path => { if (path === '/commercial-package/status') return pkg; throw new Error('offline') })
  render(<CommercialIntegrationsPage token="admin" />)
  await screen.findByRole('alert')
  expect(screen.getByRole('tab', { name: 'Provider settings' })).toBeDisabled()
  expect(screen.queryByText('Existing provider controls')).toBeNull()
})

it('unlocks only after server activation and locks again after disconnect', async () => {
  let finish!: (value: unknown) => void
  api.mockImplementation(async path => {
    if (path === '/commercial-package/status') return pkg
    if (path === '/commercial-connection/activate') return new Promise(resolve => { finish = resolve })
    return { ...connection, enabled: true }
  })
  render(<CommercialIntegrationsPage token="admin" />)
  const input = await screen.findByLabelText('Canary Commercial licence key')
  const tab = screen.getByRole('tab', { name: 'Provider settings' })
  fireEvent.change(input, { target: { value: 'synthetic-key' } })
  expect(tab).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Activate licence' }))
  expect(tab).toBeDisabled()
  await act(async () => finish({ ...connection, enabled: true, connected: true, version: 1 }))
  expect(tab).toBeEnabled()
  fireEvent.click(tab)
  expect(screen.getByText('Existing provider controls')).toBeVisible()
  fireEvent.click(screen.getByRole('tab', { name: 'Overview' }))
  fireEvent.click(screen.getByRole('button', { name: 'Disconnect hosted service locally' }))
  await waitFor(() => expect(screen.getByLabelText('Canary Commercial licence key')).toBeVisible())
  expect(tab).toBeDisabled()
  expect(screen.queryByText('Existing provider controls')).toBeNull()
})

it('locks previously activated settings after a failed status refresh', async () => {
  api.mockImplementation(async path => path === '/commercial-package/status' ? pkg : { ...connection, enabled: true, connected: true })
  render(<CommercialIntegrationsPage token="admin" />)
  const tab = await screen.findByRole('tab', { name: 'Provider settings' })
  await waitFor(() => expect(tab).toBeEnabled())
  api.mockRejectedValue(new Error('offline'))
  fireEvent.click(screen.getByRole('button', { name: 'Refresh connection status' }))
  await screen.findByRole('alert')
  expect(tab).toBeDisabled()
})

it('does not unlock after an invalid licence submission', async () => {
  api.mockImplementation(async path => {
    if (path === '/commercial-package/status') return pkg
    if (path === '/commercial-connection/activate') throw new Error('invalid licence')
    return { ...connection, enabled: true }
  })
  render(<CommercialIntegrationsPage token="admin" />)
  fireEvent.change(await screen.findByLabelText('Canary Commercial licence key'), { target: { value: 'invalid-key' } })
  fireEvent.click(screen.getByRole('button', { name: 'Activate licence' }))
  await screen.findByRole('alert')
  expect(screen.getByRole('tab', { name: 'Provider settings' })).toBeDisabled()
})

it('does not equate activation with live subscription entitlement', async () => {
  api.mockImplementation(async path => path === '/commercial-package/status' ? { ...pkg, attached: false, loaded: false } : { ...connection, enabled: true, connected: true, version: 1 })
  render(<CommercialIntegrationsPage token="admin" />)
  await screen.findByText('Activation recorded on this installation')
  expect(screen.getByText(/Live subscription details and included integrations are not available yet/)).toBeVisible()
  expect(screen.queryByRole('tab', { name: 'Provider settings' })).toBeNull()
})

it('does not restore previous-session providers after switching users', async () => {
  let finish!: (value: unknown) => void
  api.mockImplementation(async (path, opts) => {
    if (path !== '/commercial-package/status') return connection
    if (opts?.token === 'old') return new Promise(resolve => { finish = resolve })
    return { ...pkg, attached: false, loaded: false }
  })
  const { rerender } = render(<CommercialIntegrationsPage token="old" />)
  await waitFor(() => expect(finish).toBeDefined())
  rerender(<CommercialIntegrationsPage token="new" />)
  await screen.findByText(/No provider settings are available/)
  await act(async () => finish(pkg))
  expect(screen.queryByRole('tab', { name: 'Provider settings' })).toBeNull()
})
