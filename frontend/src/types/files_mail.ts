import type { CanarySignSigningRequestOut } from './canary_sign'
import type { DocusignSigningRequestOut } from './docusign'
import type { QuotePortalDeliverySummary, PortalFormSubmissionSummary } from './portal'

export type FileSummary = {
  id: string
  original_filename: string
  mime_type: string
  size_bytes: number
  created_at: string
  updated_at?: string
  folder_path?: string
  is_pinned?: boolean
  category?: 'case_document' | 'precedent' | 'system'
  parent_file_id?: string | null
  /** IMAP mailbox name when the message was linked from the server (threading / poller). */
  source_imap_mbox?: string | null
  source_imap_uid?: string | null
  /** Parsed From: header for parent .eml uploads; shown on second line in the documents list. */
  source_mail_from_name?: string | null
  source_mail_from_email?: string | null
  /** True when filed from a sent folder (IMAP) or From matches uploader; drives mail icon colour. */
  source_mail_is_outbound?: boolean | null
  /** When set, RFC5322 ``Date`` from a root .eml / rfc822 (message sent time). Used for Created column when present. */
  source_mail_date?: string | null
  /** RFC5322 Message-ID header from parent .eml (parsed on upload). */
  source_internet_message_id?: string | null
  /** Exchange/Outlook REST item id when filed from the Office add-in (OWA read deeplink). */
  source_outlook_item_id?: string | null
  /** Graph message id (often same as REST item id) for OWA read / desktop open. */
  outlook_graph_message_id?: string | null
  /** Microsoft Graph ``webLink`` when available (preferred one-click OWA open). */
  outlook_web_link?: string | null
  owner_display_name?: string | null
  owner_email?: string | null
  owner_initials?: string | null
  uploaded_via_portal?: boolean
  is_portal_quote?: boolean
  quote_portal_delivery?: QuotePortalDeliverySummary | null
  portal_form_submission?: PortalFormSubmissionSummary | null
  docusign_signing?: DocusignSigningRequestOut | null
  canary_signing?: CanarySignSigningRequestOut | null
}

export type CaseEmailDraftM365AttachmentOut = {
  file_id: string
  filename: string
}

export type CaseEmailDraftM365Out = {
  to?: string
  subject?: string
  body?: string
  open_url: string
  graph_message_id?: string | null
  draft_compose_web_link?: string | null
  compose_prefill_url?: string | null
  attachment_count?: number
  compose_handoff_token?: string | null
  attachment_files?: CaseEmailDraftM365AttachmentOut[]
}

/** Response from ``POST /cases/{id}/files/email-compose-handoff`` (Thunderbird / mail clients). */

export type CaseEmailComposeHandoffOut = {
  handoff_token: string
  case_id: string
  expires_in_seconds: number
  thunderbird_hint: string
}

/** Response from ``PUT /mail-plugin/pending-compose-handoff`` (Outlook add-in queue). */

export type OutlookPluginPendingComposeHandoffOut = {
  active: boolean
  handoff_token?: string | null
  case_id?: string | null
  expires_at?: string | null
}

/** Response from ``POST /cases/{id}/files/email-mailto``. */

export type CaseEmailMailtoOut = {
  to: string
  subject: string
  body: string
  attachment_count: number
  note: string
}
