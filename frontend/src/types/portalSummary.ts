export type PortalSummaryKind = 'quote' | 'form' | 'canary_sign' | 'docusign'
export type PortalSummaryBucket = 'outstanding' | 'completed'

export type PortalSummaryOptionsOut = {
  enabled: boolean
  client_portal_enabled: boolean
  canary_sign_enabled: boolean
  docusign_enabled: boolean
}

export type PortalSummaryRowOut = {
  kind: PortalSummaryKind
  id: string
  case_id: string
  case_number?: string | null
  client_name?: string | null
  matter_description?: string
  title: string
  status: string
  contact_or_recipients?: string
  sent_by_user_id?: string | null
  sent_by_display_name?: string | null
  fee_earner_user_id?: string | null
  fee_earner_display_name?: string | null
  created_at?: string | null
  /** Present for quote rows — used to call quote-portal resend. */
  file_id?: string | null
}

export type PortalSummaryOut = {
  bucket: PortalSummaryBucket
  rows: PortalSummaryRowOut[]
}
