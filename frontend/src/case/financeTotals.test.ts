import { describe, expect, it } from 'vitest'
import type { FinanceOut } from '../types'
import { financeCaseTotals, penceGb } from './financeTotals'

function finance(items: { direction: 'debit' | 'credit'; amount_pence?: number | null }[]): FinanceOut {
  return {
    case_id: 'c1',
    categories: [
      {
        id: 'cat1',
        case_id: 'c1',
        name: 'Fees',
        sort_order: 0,
        credit_only: false,
        items: items.map((it, i) => ({
          id: `i${i}`,
          category_id: 'cat1',
          name: `Item ${i}`,
          direction: it.direction,
          amount_pence: it.amount_pence,
          sort_order: i,
        })),
      },
    ],
  }
}

describe('financeCaseTotals', () => {
  it('sums debits and credits across categories', () => {
    expect(
      financeCaseTotals(
        finance([
          { direction: 'debit', amount_pence: 1000 },
          { direction: 'credit', amount_pence: 250 },
          { direction: 'debit', amount_pence: 50 },
        ]),
      ),
    ).toEqual({ dr: 1050, cr: 250 })
  })

  it('skips null amounts', () => {
    expect(
      financeCaseTotals(
        finance([
          { direction: 'debit', amount_pence: null },
          { direction: 'credit', amount_pence: undefined },
          { direction: 'debit', amount_pence: 10 },
        ]),
      ),
    ).toEqual({ dr: 10, cr: 0 })
  })

  it('returns zeros for empty finance', () => {
    expect(financeCaseTotals({ case_id: 'c1', categories: [] })).toEqual({ dr: 0, cr: 0 })
  })
})

describe('penceGb', () => {
  it('formats pence as GBP with two decimals', () => {
    expect(penceGb(0)).toBe('£0.00')
    expect(penceGb(12345)).toBe('£123.45')
    expect(penceGb(100)).toBe('£1.00')
  })
})
