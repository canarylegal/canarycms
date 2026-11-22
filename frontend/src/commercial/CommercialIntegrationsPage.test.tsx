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

it('preserves existing local providers without a hosted licence', async () => {
  api.mockImplementation(async path => path === '/commercial-package/status' ? pkg : connection)
  render(<CommercialIntegrationsPage token="admin" />)
  fireEvent.click(await screen.findByRole('tab', { name: 'Provider settings' }))
  expect(screen.getByText('Existing provider controls')).toBeVisible()
  fireEvent.click(screen.getByRole('tab', { name: 'Overview' }))
  expect(screen.getByLabelText('Canary Commercial licence key')).toBeVisible()
})

it('keeps existing provider access when connection status is unavailable', async () => {
  api.mockImplementation(async path => { if (path === '/commercial-package/status') return pkg; throw new Error('offline') })
  render(<CommercialIntegrationsPage token="admin" />)
  await screen.findByRole('alert')
  fireEvent.click(await screen.findByRole('tab', { name: 'Provider settings' }))
  expect(screen.getByText('Existing provider controls')).toBeVisible()
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
