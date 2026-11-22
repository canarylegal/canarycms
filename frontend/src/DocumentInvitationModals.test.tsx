import { cleanup, render, screen, fireEvent } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { SendQuoteViaPortalModal } from './SendQuoteViaPortalModal'
import { SendPortalFormModal } from './SendPortalFormModal'
import { SendCanarySignModal } from './SendCanarySignModal'
import { apiFetch } from './api'
vi.mock('./api', () => ({ apiFetch: vi.fn(), apiUrl: (path: string) => path }))
vi.mock('./DialogProvider', () => ({ useDialogs: () => ({ askConfirm: vi.fn() }) }))
vi.mock('./SingleSelectDropdown', () => ({ SingleSelectDropdown: ({ options, onChange }: { options: { label: string; value: string }[]; onChange: (value: string) => void }) => <div>{options.map((option, i) => <button key={i} onClick={() => onChange(option.value)}>{option.label}</button>)}</div> }))
vi.mock('./CanarySignPdfDocument', () => ({ CANARY_SIGN_SIGNER_PALETTE: ['blue'], CanarySignPdfDocument: () => null, defaultFieldSize: () => ({ w: 30, h: 10 }), fieldTypeLabel: (value: string) => value }))
beforeEach(() => {
  vi.mocked(apiFetch).mockImplementation(async path => {
    if (path.endsWith('/form-fields')) return [] as never
    if (path.includes('folder-share')) return [{ contact_id: 'synthetic-contact', contact_name: 'Synthetic signer', portal_access_active: false }] as never
    if (path.endsWith('/templates')) return [{ id: 'synthetic-template', name: 'Synthetic form' }] as never
    return { alerts_configured: true } as never
  })
})
afterEach(() => { cleanup(); vi.resetAllMocks() })
it.each(['quote', 'form'])('offers a document-only %s invitation without promising a portal login', async kind => {
  const props = { token: 'cookie', caseId: 'matter', open: true, onClose: vi.fn() }
  render(kind === 'quote' ? <SendQuoteViaPortalModal {...props} fileId="file" /> : <SendPortalFormModal {...props} />)
  expect(await screen.findByText(/No portal login is created or enabled/)).toBeTruthy()
  expect(screen.getByText('Synthetic signer')).toBeTruthy()
  expect(screen.queryByText(/access code|enabled automatically|portal access will be enabled/i)).toBeNull()
})

it('uses a selected matter contact email as read-only signing identity', async () => {
  render(<SendCanarySignModal token="cookie" caseId="matter" fileId="file" fileName="Synthetic.pdf" open onClose={vi.fn()}
    caseContacts={[{ id: 'matter-contact', contact_id: 'contact', name: 'Synthetic signer', email: 'stored@example.test' },
      { id: 'unlinked', contact_id: null, name: 'Unlinked', email: 'unlinked@example.test' }] as never} />)
  expect(await screen.findByText(/No portal login is created or enabled/)).toBeTruthy()
  fireEvent.click(await screen.findByRole('button', { name: 'Synthetic signer (stored@example.test)' }))
  const email = screen.getByLabelText('E-mail') as HTMLInputElement
  expect(email.value).toBe('stored@example.test')
  expect(email.readOnly).toBe(true)
  expect(screen.queryByRole('button', { name: 'Unlinked (unlinked@example.test)' })).toBeNull()
  expect(screen.queryByText(/access code|portal access will be enabled/i)).toBeNull()
})
