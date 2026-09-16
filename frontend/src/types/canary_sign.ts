import type { PortalGrantSummaryOut } from './portal'

export type CanarySignSendRecipientIn = {
  name: string
  email: string
  routing_order: number
  case_contact_id?: string | null
  contact_id?: string | null
}

export type CanarySignFieldOut = {
  id: string
  recipient_id: string
  field_type: 'signature' | 'initials' | 'date' | 'printed_name' | 'checkbox' | string
  label?: string | null
  required: boolean
  sort_order: number
  placement_mode: 'free' | 'fixed' | string
  page?: number | null
  x_pct?: number | null
  y_pct?: number | null
  w_pct?: number | null
  h_pct?: number | null
  value?: Record<string, unknown> | null
  filled_at?: string | null
}

export type CanarySignRecipientOut = {
  id: string
  name: string
  email: string
  routing_order: number
  status: string
  decline_reason?: string | null
  signed_at?: string | null
  viewed_at?: string | null
  contact_id?: string | null
  case_contact_id?: string | null
}

export type CanarySignSigningRequestOut = {
  id: string
  case_id: string
  source_file_id: string
  source_filename?: string
  snapshot_pdf_file_id?: string | null
  signed_file_id?: string | null
  certificate_file_id?: string | null
  subject: string
  status: string
  status_detail?: string | null
  order_mode: string
  expires_at?: string | null
  completed_at?: string | null
  voided_at?: string | null
  created_at?: string | null
  has_fillable_form?: boolean
  form_locked_by_recipient_id?: string | null
  form_completed_at?: string | null
  recipients?: CanarySignRecipientOut[]
  fields?: CanarySignFieldOut[]
}

export type CanarySignAcroFormFieldOut = {
  name: string
  label: string
  field_type: 'text' | 'checkbox' | 'choice' | 'radio' | string
  required: boolean
  page: number
  x_pct: number
  y_pct: number
  w_pct: number
  h_pct: number
  options: string[]
  current_value?: string
  multiline?: boolean
}

export type PortalCanarySignOut = {
  id: string
  subject: string
  status: string
  status_detail?: string | null
  order_mode?: string
  expires_at?: string | null
  can_sign: boolean
  recipient_id: string
  recipient_name?: string | null
  recipient_status?: string
  sign_token: string
  matter_label?: string
  case_id?: string | null
  fields?: CanarySignFieldOut[]
  disclaimer?: string
  has_fillable_form?: boolean
  form_fields?: CanarySignAcroFormFieldOut[]
  form_responses?: Record<string, unknown>
  form_locked?: boolean
  form_locked_by_recipient_id?: string | null
  form_locked_by_name?: string | null
  form_lock_held_by_me?: boolean
  form_completed?: boolean
  can_edit_form?: boolean
  can_claim_form_lock?: boolean
}

export type PortalClientActionItemOut = {
  kind: 'quote' | 'form' | 'canary_sign' | 'docusign'
  id: string
  title: string
  status: string
  matter_label?: string
  badge?: string
  href_key?: string
  case_id?: string | null
}

export type PortalClientActionsOut = {
  outstanding: PortalClientActionItemOut[]
  complete: PortalClientActionItemOut[]
  inactive: PortalClientActionItemOut[]
}

export type PortalCanarySignExchangeOut = {
  session_token: string
  contact_name: string
  grants: PortalGrantSummaryOut[]
  signing: PortalCanarySignOut
}

/** Response from ``POST /cases/{id}/files/email-drafts/m365`` (Microsoft Graph draft). */
