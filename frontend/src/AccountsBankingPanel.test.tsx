import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { apiFetch } from './api'
import { AccountsBankingPanel } from './AccountsBankingPanel'

vi.mock('./api', () => ({ apiFetch: vi.fn(), apiUrl: (path: string) => path, applyAuthHeaders: vi.fn() }))
afterEach(() => { cleanup(); vi.resetAllMocks() })

it('keeps the selected bank visible when the previous bank responds late', async () => {
  const late: ((value: unknown) => void)[] = []
  const line = (id: string, description: string) => ({ id, version: 0, statement_date: '2026-01-31',
    amount_pence: 100, description, ignored: false, matched_pair_id: null })
  vi.mocked(apiFetch).mockImplementation((path) => {
    if (path.includes('/bank-accounts?')) return Promise.resolve([
      { id: 'a', name: 'Bank A', is_default: true }, { id: 'b', name: 'Bank B' },
    ]) as never
    if (path.includes('/statements/lines?')) {
      if (path.includes('firm_bank_account_id=a')) return new Promise(resolve => { late.push(resolve) }) as never
      return Promise.resolve([line('b-line', 'Bank B receipt')]) as never
    }
    if (path.endsWith('/xero/settings')) return Promise.resolve({ enabled: false, office_income_code: '', office_bank_code: '', vat_code: '', disbursement_code: '' }) as never
    return Promise.resolve([]) as never
  })
  render(<AccountsBankingPanel token="test" busy={false} active setBusy={vi.fn()} setErr={vi.fn()} />)
  const bank = await screen.findByRole('combobox', { name: 'Client bank', exact: true })
  await waitFor(() => expect(late.length).toBeGreaterThan(0))
  fireEvent.change(bank, { target: { value: 'b' } })
  await screen.findByText('Bank B receipt')
  await act(async () => { for (const resolve of late) resolve([line('a-line', 'Bank A receipt')]) })
  expect(bank).toHaveValue('b')
  expect(screen.getByText('Bank B receipt')).toBeVisible()
  expect(screen.queryByText('Bank A receipt')).toBeNull()
})
