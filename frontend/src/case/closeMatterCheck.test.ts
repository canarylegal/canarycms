import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { LedgerOut } from '../types'

vi.mock('../api', () => ({
  apiFetch: vi.fn(),
}))

import { apiFetch } from '../api'
import { closeMatterBlockMessage } from './closeMatterCheck'

const apiFetchMock = vi.mocked(apiFetch)

function ledger(client: number, office: number): LedgerOut {
  return {
    entries: [],
    client: { account_type: 'client', balance_pence: client },
    office: { account_type: 'office', balance_pence: office },
  }
}

describe('closeMatterBlockMessage', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('returns null when both balances are zero', async () => {
    apiFetchMock.mockResolvedValueOnce(ledger(0, 0))
    await expect(closeMatterBlockMessage('tok', 'case-1')).resolves.toBeNull()
    expect(apiFetchMock).toHaveBeenCalledWith('/cases/case-1/ledger', { token: 'tok' })
  })

  it('blocks with client and office balance lines', async () => {
    apiFetchMock.mockResolvedValueOnce(ledger(150, -200))
    const msg = await closeMatterBlockMessage('tok', 'case-1')
    expect(msg).toContain('cannot be closed')
    expect(msg).toContain('Client account balance: £1.50')
    expect(msg).toContain('Office account balance: -£2.00')
    expect(msg).toContain('Clear the balances in Accounts')
  })

  it('only mentions the non-zero account', async () => {
    apiFetchMock.mockResolvedValueOnce(ledger(50, 0))
    const msg = await closeMatterBlockMessage('tok', 'case-1')
    expect(msg).toContain('Client account balance')
    expect(msg).not.toContain('Office account balance')
  })
})
