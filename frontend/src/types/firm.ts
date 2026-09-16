export type LetterheadStyle = 'preprinted' | 'digital'

export type MergeCodeCatalogOut = {
  code: string
  description: string
  sort_order: number
}

export type MergeCodeCatalogImportResult = {
  updated: number
  skipped_unknown: number
}

export type FirmSettingsOut = {
  id: number
  trading_name: string
  registered_company_name?: string | null
  addr_line1?: string | null
  addr_line2?: string | null
  town_city?: string | null
  county?: string | null
  postcode?: string | null
  letterhead_style: LetterheadStyle
  letterhead_original_filename?: string | null
  quote_letterhead_style?: LetterheadStyle
  quote_letterhead_original_filename?: string | null
  portal_logo_configured?: boolean
  portal_logo_original_filename?: string | null
  /** `#RRGGBB` solid portal page background; null = product default. */
  portal_background_color?: string | null
  default_signature_configured?: boolean
  default_signature_original_filename?: string | null
  default_signature_scale?: number
  mandate_two_factor?: boolean
  mandate_password_rotation?: boolean
  password_rotation_days?: number | null
  client_bank_account_name?: string | null
  client_bank_sort_code?: string | null
  client_bank_account_number_last4?: string | null
  client_bank_account_number?: string | null
}

export type ClientAccountReconciliationOut = {
  id: string
  period_end_date: string
  ledger_client_total_pence: number
  ledger_office_total_pence: number
  bank_statement_balance_pence: number
  difference_pence: number
  prepared_by_user_id: string
  prepared_by_name?: string | null
  prepared_at: string
  approved_by_user_id?: string | null
  approved_by_name?: string | null
  approved_at?: string | null
  notes?: string | null
  status: 'draft' | 'approved'
}

export type ReconciliationPreviewOut = {
  ledger_client_total_pence: number
  ledger_office_total_pence: number
}

export type AccountantPackSectionOut = {
  key: string
  label: string
  included: boolean
  row_count?: number | null
  note?: string | null
}

export type AccountantPackPreviewOut = {
  period_end_date: string
  activity_date_from: string
  activity_date_to: string
  fee_earner_count: number
  reconcile_doc_available: boolean
  sections: AccountantPackSectionOut[]
}

/** Registered passkey row from GET /auth/webauthn/credentials */

export type PrecedentCategoryOut = {
  id: string
  matter_sub_type_id: string
  name: string
  sort_order: number
  created_at: string
  updated_at: string
}

export type PrecedentCategoryFlatOut = PrecedentCategoryOut & {
  matter_sub_type_name: string
}

/** Form/API token for Global scope (must match backend GLOBAL_SCOPE). */

export const GLOBAL_PRECEDENT_SCOPE = '__GLOBAL__'

export type PrecedentOut = {
  id: string
  name: string
  reference: string
  kind: 'letter' | 'email' | 'document'
  original_filename: string
  mime_type: string
  category_id?: string | null
  matter_head_type_id?: string | null
  matter_sub_type_id?: string | null
  category_name?: string | null
  matter_head_type_name?: string | null
  matter_sub_type_name?: string | null
  scope_summary?: string
  created_at: string
}

export type EmailIntegrationSettingsOut = {
  integration_mode: 'mailto' | 'microsoft_graph'
  graph_tenant_id: string | null
  graph_client_id: string | null
  graph_client_secret_configured: boolean
  outlook_web_mail_base: string | null
  alerts_enabled: boolean
  alert_transport: 'auto' | 'graph' | 'smtp'
  graph_send_mailbox: string | null
  graph_send_from_name: string | null
  graph_alert_ready: boolean
  smtp_alert_ready: boolean
  effective_alert_transport: 'graph' | 'smtp' | null
}

export type CaseSourceOut = {
  id: string
  name: string
  sort_order: number
  is_system: boolean
}

// Sub-menu Events (admin template + case rows)

export type AdminDeployUpdateCheckOut = {
  github_repo_configured: boolean
  deploy_trigger_configured: boolean
  compose_update_enabled: boolean
  compose_git_reset_enabled?: boolean
  compose_git_ref?: string
  prompt_enabled: boolean
  current_commit: string
  current_commit_short: string
  remote_ref: string
  remote_commit: string
  remote_commit_short: string
  update_available: boolean
  build_commit_unknown: boolean
  compare_html_url?: string | null
  latest_release_tag?: string | null
  latest_release_name?: string | null
  latest_release_body?: string | null
  commit_messages: string[]
  note?: string | null
}

export type AdminStorageCategoryOut = {
  category: string
  label: string
  bytes_used: number
  file_count: number
}

export type AdminStorageDeploymentComponentOut = {
  key: string
  label: string
  bytes_used: number
  detected: boolean
}

export type AdminStorageOut = {
  tracked_total_bytes: number
  files_on_disk_bytes: number
  compose_mount_bytes: number
  application_checkout_bytes: number
  database_bytes: number | null
  database_logical_bytes: number | null
  calendars_bytes: number | null
  deployment_total_bytes: number
  docker_detected: boolean
  docker_images_bytes: number
  docker_container_writable_bytes: number
  docker_dangling_images_bytes: number
  docker_build_cache_bytes: number | null
  deployment_active_bytes: number
  deployment_artifacts_bytes: number
  measurement_note: string | null
  deployment_components: AdminStorageDeploymentComponentOut[]
  categories: AdminStorageCategoryOut[]
  storage_limit_bytes: number | null
  files_root: string
  host_disk_detected: boolean
  host_disk_total_bytes: number | null
  host_disk_used_bytes: number | null
  host_disk_free_bytes: number | null
}

export type AdminDeployTriggerOut = {
  ok: boolean
  message: string
  async_mode?: boolean
  job_id?: string | null
}

export type AdminDeployComposeJobOut = {
  status: 'idle' | 'running' | 'succeeded' | 'failed'
  job_id?: string | null
  started_at?: string | null
  finished_at?: string | null
  message?: string | null
  error_detail?: string | null
  log_excerpt?: string | null
  journal_lines?: string[]
  progress_phase?: 'git' | 'build' | 'up' | null
  elapsed_seconds?: number | null
}

export type SmtpNotificationSettingsOut = {
  enabled: boolean
  host: string | null
  port: number
  use_tls: boolean
  username: string | null
  password_configured: boolean
  from_email: string | null
  from_name: string | null
}
