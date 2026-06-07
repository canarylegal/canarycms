import { apiFetch } from '../api'
import type { LedgerOut } from '../types'
import { penceGb } from './financeTotals'

function ledgerSignedGb(p: number): string {
  if (p === 0) return penceGb(0)
  return p < 0 ? `-${penceGb(-p)}` : penceGb(p)
}

/** Returns a user-facing message when the matter cannot be closed, or null if balances are clear. */
export async function closeMatterBlockMessage(token: string, caseId: string): Promise<string | null> {
  const ledger = await apiFetch<LedgerOut>(`/cases/${caseId}/ledger`, { token })
  const clientBal = ledger.client.balance_pence
  const officeBal = ledger.office.balance_pence
  if (clientBal === 0 && officeBal === 0) return null

  const lines: string[] = []
  if (clientBal !== 0) lines.push(`Client account balance: ${ledgerSignedGb(clientBal)}`)
  if (officeBal !== 0) lines.push(`Office account balance: ${ledgerSignedGb(officeBal)}`)

  return (
    'This matter cannot be closed while the client or office account has a non-zero balance.\n\n' +
    `${lines.join('\n')}\n\n` +
    'Clear the balances in Accounts before closing.'
  )
}
