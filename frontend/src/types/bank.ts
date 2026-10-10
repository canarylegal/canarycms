export type PaymentMethod =
  | 'faster_payments'
  | 'bacs'
  | 'chaps'
  | 'cheque'
  | 'card'
  | 'journal'
  | 'other'

export const PAYMENT_METHOD_LABELS: Record<PaymentMethod, string> = {
  faster_payments: 'Faster Payments',
  bacs: 'BACS',
  chaps: 'CHAPS',
  cheque: 'Cheque',
  card: 'Card',
  journal: 'Journal',
  other: 'Other',
}

export type FirmBankAccountOut = {
  id: string
  name: string
  account_kind: 'client' | 'office'
  sort_code?: string | null
  account_number?: string | null
  account_number_last4?: string | null
  is_active: boolean
  is_default: boolean
  created_at: string
  updated_at: string
}

export type BankStatementLineOut = {
  id: string
  import_id: string
  firm_bank_account_id: string
  statement_date: string
  amount_pence: number
  description: string
  reference?: string | null
  balance_pence?: number | null
  matched_pair_id?: string | null
  matched_at?: string | null
  ignored: boolean
}

export type BankReconciliationOut = {
  id: string
  firm_bank_account_id: string
  period_end_date: string
  statement_balance_pence: number
  ledger_total_pence: number
  unpresented_total_pence: number
  unmatched_statement_total_pence: number
  difference_pence: number
  status: string
  notes?: string | null
  prepared_at: string
  approved_at?: string | null
}

export type ClientAccountEomOut = {
  id: string
  firm_bank_account_id: string
  period_end_date: string
  generated_at: string
  filename: string
  notes?: string | null
}

export type UnpresentedLedgerLegOut = {
  pair_id: string
  case_id: string
  case_number?: string | null
  posted_at: string
  amount_pence: number
  direction: 'debit' | 'credit'
  description: string
  reference?: string | null
  payment_method?: string | null
}

export type InterMatterJournalOut = {
  id: string
  from_case_id: string
  to_case_id: string
  firm_bank_account_id?: string | null
  amount_pence: number
  description: string
  from_pair_id: string
  to_pair_id: string
  created_at: string
}

export type XeroSettingsOut = {
  enabled: boolean
  tenant_name?: string | null
  office_income_code?: string | null
  office_bank_code?: string | null
  vat_code?: string | null
  disbursement_code?: string | null
}

export type XeroExportOut = {
  id: string
  period_from: string
  period_to: string
  generated_at: string
  filename: string
  row_count: number
}
