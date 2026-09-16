import type { CaseWorkflowStatus } from '../types'

export type ReportTab =
  | 'client_office_balances'
  | 'billing'
  | 'time_recorded'
  | 'wip'
  | 'aged_debt'
  | 'exceptions'
  | 'client_account_reconcile'
  | 'accountant_pack'
  | 'cases'
  | 'cases_opened'
  | 'events'
  | 'ledger_activity'

export type FeeEarnerPick = { id: string; display_name: string; email: string }

export type FeeEarnerPayload = { fee_earner_user_ids: string[] }

export const REPORT_OPTIONS: { value: ReportTab; label: string }[] = [
  { value: 'client_office_balances', label: 'Client & office balances' },
  { value: 'billing', label: 'Billing' },
  { value: 'time_recorded', label: 'Time recorded' },
  { value: 'wip', label: 'WIP (unbilled time)' },
  { value: 'aged_debt', label: 'Aged debt' },
  { value: 'exceptions', label: 'Exceptions' },
  { value: 'client_account_reconcile', label: 'Client account reconcile' },
  { value: 'accountant_pack', label: 'Accountant export pack' },
  { value: 'ledger_activity', label: 'Ledger activity' },
  { value: 'cases', label: 'Cases' },
  { value: 'cases_opened', label: 'Cases opened' },
  { value: 'events', label: 'Events' },
]

export const AGED_DEBT_BUCKETS = ['0-30', '31-60', '61-90', '90+'] as const

export const CASE_STATUS_OPTIONS: { value: CaseWorkflowStatus; label: string }[] = [
  { value: 'open', label: 'Active' },
  { value: 'quote', label: 'Quote' },
  { value: 'post_completion', label: 'Post-completion' },
  { value: 'closed', label: 'Closed' },
  { value: 'archived', label: 'Archived' },
]
