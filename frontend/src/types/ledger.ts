export type CaseInvoiceLineOut = {
  id: string
  line_type: string
  description: string
  amount_pence: number
  tax_pence: number
  credit_user_id?: string | null
}

export type CaseInvoiceOut = {
  id: string
  case_id: string
  invoice_number: string
  status: string
  total_pence: number
  payee_name?: string | null
  credit_user_id?: string | null
  credit_user_display_name?: string | null
  contact_id?: string | null
  ledger_pair_id?: string | null
  created_by_user_id?: string | null
  approved_by_user_id?: string | null
  approved_at?: string | null
  voided_at?: string | null
  created_at: string
  document_file_id?: string | null
  lines: CaseInvoiceLineOut[]
}

export type CaseInvoicesOut = {
  case_id: string
  invoices: CaseInvoiceOut[]
}

export type CaseInvoiceLineCreate = {
  line_type: 'fee' | 'disbursement' | 'vat'
  description: string
  amount_pence: number
  tax_pence?: number
  credit_user_id?: string | null
}

export type CaseInvoiceCreate = {
  credit_user_id: string
  payee_name?: string | null
  contact_id?: string | null
  lines: CaseInvoiceLineCreate[]
  time_entry_ids?: string[]
}

export type BillingLineTemplateOut = {
  id: string
  matter_sub_type_id: string
  line_kind: 'fee' | 'disbursement'
  label: string
  default_amount_pence: number
  sort_order: number
}

export type InvoiceBillingDefaultsUser = {
  id: string
  email: string
  display_name: string
  initials?: string
}

export type InvoiceBillingDefaultsOut = {
  default_vat_percent: number
  fee_earner_user_id: string
  fee_templates: BillingLineTemplateOut[]
  disbursement_templates: BillingLineTemplateOut[]
  users: InvoiceBillingDefaultsUser[]
}

export type LedgerEntryOut = {
  id: string
  pair_id: string
  account_type: 'client' | 'office'
  direction: 'debit' | 'credit'
  amount_pence: number
  description: string
  reference?: string | null
  contact_label?: string | null
  case_contact_id?: string | null
  contact_id?: string | null
  posted_by_user_id?: string | null
  posted_at: string
  is_approved?: boolean
  is_anticipated?: boolean
  anticipated_for_date?: string | null
}

export type LedgerAccountSummary = {
  account_type: 'client' | 'office'
  balance_pence: number
}

export type LedgerOut = {
  entries: LedgerEntryOut[]
  client: LedgerAccountSummary
  office: LedgerAccountSummary
}

export type LedgerPostCreate = {
  description: string
  reference?: string | null
  contact_label?: string | null
  case_contact_id?: string | null
  contact_id?: string | null
  amount_pence: number
  client_direction?: 'debit' | 'credit' | null
  office_direction?: 'debit' | 'credit' | null
  anticipated?: boolean
  anticipated_for_date?: string | null
}

// ---------------------------------------------------------------------------
// Finance templates (admin)
// ---------------------------------------------------------------------------
