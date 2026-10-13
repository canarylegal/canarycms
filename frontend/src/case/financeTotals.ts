import type { FinanceOut } from '../types'

export function financeCaseTotals(
  f: FinanceOut,
  opts?: { includeVat?: boolean },
): { dr: number; cr: number } {
  const includeVat = Boolean(opts?.includeVat)
  let dr = 0
  let cr = 0
  for (const cat of f.categories) {
    for (const it of cat.items) {
      const amt = it.amount_pence
      if (amt == null) continue
      const vat = includeVat ? it.vat_pence ?? 0 : 0
      const line = amt + vat
      if (it.direction === 'debit') dr += line
      else cr += line
    }
  }
  return { dr, cr }
}

export function penceGb(p: number): string {
  return `£${(p / 100).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

/** Net credits − debits: positive = due to client, negative = owed by client. */
export function financeBalanceLabel(net: number): string {
  if (net > 0) return 'Due to client'
  if (net < 0) return 'Owed by client'
  return 'Balanced'
}
