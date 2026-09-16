export type DocusignIntegrationSettingsOut = {
  enabled: boolean
  use_demo: boolean
  allow_tier_a: boolean
  allow_tier_b: boolean
  allow_tier_c: boolean
  allow_wes: boolean
  allow_qes: boolean
  account_id?: string | null
  integration_key?: string | null
  user_id?: string | null
  rsa_private_key_configured: boolean
  connect_hmac_secret_configured: boolean
  api_base_uri?: string | null
  configured: boolean
  cost_standard_pence?: number | null
  cost_wes_pence?: number | null
  cost_qes_pence?: number | null
}

export type DocusignTemplateOut = {
  template_id: string
  name: string
  description?: string | null
  roles: string[]
}

export type DocusignStaffOptionsOut = {
  enabled: boolean
  allow_tier_a: boolean
  allow_tier_b: boolean
  allow_tier_c: boolean
  allow_wes: boolean
  allow_qes: boolean
}

export type DocusignMenuRowOut = {
  id: string
  case_id: string
  case_number: string
  client_name?: string | null
  matter_description?: string
  envelope_subject: string
  source_filename?: string
  status: string
  status_detail?: string | null
  sent_by_display_name?: string | null
  recipients_summary?: string
  created_at: string
  completed_at?: string | null
  voided_at?: string | null
}

export type DocusignSigningRecipientOut = {
  id: string
  name: string
  email: string
  routing_order: number
  role_name?: string | null
  status: string
  completed_at?: string | null
}

export type DocusignSigningRequestOut = {
  id: string
  case_id: string
  source_file_id?: string | null
  source_filename?: string
  docusign_envelope_id?: string | null
  docusign_template_id?: string | null
  envelope_subject: string
  document_tier: string
  signature_level: string
  status: string
  status_detail?: string | null
  signed_file_id?: string | null
  certificate_file_id?: string | null
  completed_at?: string | null
  voided_at?: string | null
  created_at?: string | null
  recipients: DocusignSigningRecipientOut[]
}

export type DocusignSendRecipientIn = {
  name: string
  email: string
  routing_order?: number
  role_name?: string | null
  case_contact_id?: string | null
  contact_id?: string | null
}

export type PortalDocusignSigningOut = {
  id: string
  envelope_subject: string
  status: string
  can_sign: boolean
  recipient_id: string
  sign_token: string
}
