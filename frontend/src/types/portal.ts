import type { PortalCanarySignOut } from './canary_sign'
import type { PortalDocusignSigningOut } from './docusign'

export type PortalFormSubmissionSummary = {
  id: string
  status: 'pending' | 'completed' | 'voided' | 'superseded'
  contact_name: string
  template_name: string
  sent_at: string
  completed_at: string | null
}

export type QuotePortalDeliverySummary = {
  id: string
  status: 'pending' | 'accepted' | 'declined' | 'superseded'
  contact_name: string
  sent_at: string
  responded_at: string | null
  decline_reason: string | null
}

export type QuotePortalDeliveryOut = {
  id: string
  file_id: string
  contact_id: string
  contact_name: string
  status: string
  sent_at: string
  responded_at: string | null
  decline_reason: string | null
  file_version_at_send: number
  email_sent: boolean
  email_skip_reason: string | null
  portal_pdf_generated?: boolean
}

export type QuotePortalSendPreflightOut = {
  alerts_configured: boolean
}

export type PortalQuoteDeliveryViewOut = {
  id: string
  file_id: string
  grant_id: string | null
  case_id?: string | null
  case_title?: string
  original_filename: string
  mime_type?: string
  size_bytes?: number
  folder_display?: string
  status: string
  can_respond: boolean
  decline_reason: string | null
  responded_at: string | null
  portal_pdf_available?: boolean
}

export type PortalQuoteExchangeOut = {
  session_token: string
  contact_name: string
  grants: PortalGrantSummaryOut[]
  quote: PortalQuoteDeliveryViewOut
}

export type PortalFormExchangeOut = {
  session_token: string
  contact_name: string
  grants: PortalGrantSummaryOut[]
  form: PortalFormPendingOut
}

export type PortalGrantSummaryOut = {
  id: string
  case_id: string
  case_title: string
  folder_path: string
  folder_label: string
  label: string
  can_download: boolean
  can_upload: boolean
  new_file_count?: number
  last_viewed_at?: string | null
}

export type PortalAuthOut = {
  session_token: string
  contact_name: string
  grants: PortalGrantSummaryOut[]
  focus_case_id?: string | null
  staff_preview?: boolean
  audience?: 'client' | 'exchange'
}

export type PortalSessionOut = {
  contact_name: string
  grants: PortalGrantSummaryOut[]
  staff_preview?: boolean
  audience?: 'client' | 'exchange'
  focus_case_id?: string | null
}

export type PortalFileOut = {
  id: string
  original_filename: string
  mime_type: string
  size_bytes: number
  folder_path: string
  folder_display?: string
  created_at: string
  updated_at: string
  is_new?: boolean
}

export type PortalBrowseOut = {
  subfolder: string
  breadcrumb: string[]
  subfolders: string[]
  files: PortalFileOut[]
  pending_approvals?: PortalQuoteDeliveryViewOut[]
  pending_docusign_signings?: PortalDocusignSigningOut[]
  pending_canary_signings?: PortalCanarySignOut[]
  pending_portal_forms?: PortalFormPendingOut[]
  new_file_count?: number
  last_viewed_at?: string | null
}

export type PortalFormFieldType = 'section' | 'text' | 'textarea' | 'date' | 'select' | 'file'

export type PortalFormTemplateFieldIn = {
  field_key: string
  label: string
  field_type: PortalFormFieldType
  help_text?: string | null
  required?: boolean
  sort_order?: number
  select_options?: string[]
}

export type PortalFormTemplateFieldOut = PortalFormTemplateFieldIn & {
  id: string
}

export type PortalFormTemplateOut = {
  id: string
  name: string
  reference: string
  description?: string | null
  matter_head_type_id?: string | null
  matter_sub_type_id?: string | null
  scope_summary: string
  field_count: number
  created_at: string
  updated_at: string
}

export type PortalFormTemplateDetailOut = PortalFormTemplateOut & {
  fields: PortalFormTemplateFieldOut[]
}

export type PortalFormSubmissionOut = {
  id: string
  case_id: string
  template_id: string
  template_name: string
  template_reference: string
  contact_id: string
  contact_name: string
  status: string
  responses: Record<string, unknown>
  snapshot_file_id?: string | null
  snapshot_filename: string
  sent_at: string
  completed_at?: string | null
  voided_at?: string | null
  email_sent?: boolean
  email_skip_reason?: string | null
}

export type PortalFormFieldOut = {
  field_key: string
  label: string
  field_type: PortalFormFieldType
  help_text?: string | null
  required: boolean
  sort_order: number
  select_options?: string[]
}

export type PortalFormPendingOut = {
  id: string
  template_name: string
  template_reference: string
  status: string
  sent_at: string
  case_id?: string | null
  matter_label: string
}

export type PortalFormDetailOut = PortalFormSubmissionOut & {
  description?: string | null
  fields: PortalFormFieldOut[]
}

export type CasePortalActivityOut = {
  id: string
  action: string
  summary: string
  contact_name: string | null
  created_at: string
}

export type CasePortalStaffUserOut = {
  id: string
  display_name: string
  email: string
}

export type CasePortalNotificationSettingsOut = {
  staff_user_ids: string[]
  staff_users?: CasePortalStaffUserOut[]
}

export type CasePortalShareStatusOut = {
  portal_enabled: boolean
  active_grant_count: number
  contact_count: number
}

export type CasePortalPreviewContactOut = {
  contact_id: string
  contact_name: string
  shared_folder_count: number
  pending_quote_count?: number
  pending_form_count?: number
  pending_canary_sign_count?: number
}

export type CasePortalPreviewOut = {
  exchange_token: string
  contact_name: string
  preview_url: string
}

export type CasePortalNotifyFilesOut = {
  contacts_notified: number
  alerts_skipped_reason?: string | null
}

export type ContactPortalNotificationPrefsOut = {
  notify_files_added: boolean
  notify_folder_shared: boolean
}

export const PORTAL_ALERTS_NOT_CONFIGURED_MSG =
  'Automated e-mail is not configured. Ask an administrator to enable Admin → E-mail → "Enable automated alert e-mail" and set up Graph or SMTP.'

export type ContactPortalAccessOut = {
  enabled: boolean
  expires_at: string | null
  last_login_at: string | null
  locked_until: string | null
  has_access: boolean
  access_code?: string | null
  access_record_exists?: boolean
  notify_files_added?: boolean
  notify_folder_shared?: boolean
}

export type ContactPortalAccessCreateOut = {
  access_code: string
  enabled: boolean
  expires_at: string | null
  email_sent?: boolean
  email_skip_reason?: string | null
}

export type ContactPortalGrantOut = {
  id: string
  contact_id: string
  case_id: string
  case_title: string
  folder_path: string
  label: string | null
  can_download: boolean
  can_upload: boolean
  expires_at: string | null
  created_at: string
  email_sent?: boolean
  email_skip_reason?: string | null
}

export type ContactPortalGrantCreateIn = {
  case_id: string
  folder_path?: string
  label?: string | null
  can_download?: boolean
  can_upload?: boolean
  expires_at?: string | null
  send_email?: boolean
}

export type CasePortalFolderShareContactOut = {
  case_contact_id: string
  contact_id: string
  contact_name: string
  has_grant: boolean
  grant_id: string | null
  /** False when the contact will be auto-granted portal access on send. */
  portal_access_active?: boolean
  /** Matter snapshot or global contact e-mail (empty when missing). */
  email?: string
  matter_contact_type?: string
  is_exchange_contact?: boolean
}

export type MatterPortalAccessOut = {
  enabled: boolean
  expires_at: string | null
  last_login_at: string | null
  locked_until: string | null
  has_access: boolean
  access_code: string | null
  access_record_exists: boolean
  notify_folder_shared: boolean
  case_id: string
  contact_id: string
}

export type MatterPortalAccessCreateOut = {
  access_code: string
  enabled: boolean
  expires_at?: string | null
  email_sent: boolean
  email_skip_reason?: string | null
  case_id: string
  contact_id: string
}

export type CasePortalFolderAccessGrantOut = {
  folder_path: string
  contact_id: string
  contact_name: string
}
