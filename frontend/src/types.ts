export type TokenResponse = { access_token: string; token_type: string }

export type UserPublic = {
  id: string
  email: string
  display_name: string
  /** Present once API/backend expose user initials; legacy responses may omit. */
  initials?: string
  job_title?: string | null
  role: 'admin' | 'user'
  is_active: boolean
  is_2fa_enabled: boolean
  is_master_recovery?: boolean
  /** TOTP setup was started but not confirmed — resume requires Canary password. */
  pending_authenticator_setup?: boolean
  /** Organisation policy: user must enable TOTP or register at least one passkey (non-admin enforcement). */
  organization_requires_second_factor?: boolean
  has_passkeys?: boolean
  /** Matter compose: `mailto:` vs Outlook web URL */
  email_launch_preference?: 'desktop' | 'outlook_web'
  email_outlook_web_url?: string | null
  /** Org-wide: Admin → E-mail — desktop mailto vs Microsoft 365 Graph drafts. */
  email_integration_mode?: 'mailto' | 'microsoft_graph'
  /** True when mode is Graph and tenant/client/secret resolve (DB or env). */
  m365_graph_drafts_configured?: boolean
  /** From GET /auth/me — category Admin or built-in admin role. */
  admin_console_access?: boolean
  /** From GET /auth/me — firm-wide Accounts desk (admin or cashier approve permissions). */
  accounts_workspace_access?: boolean
  /**
   * From GET /auth/me — false when org mandates a second factor but this JWT did not verify one at sign-in
   * (e.g. password-only session). Omitted on older APIs (treat as unrestricted).
   */
  session_second_factor_verified?: boolean
  organization_requires_password_rotation?: boolean
  password_rotation_days?: number | null
  session_password_change_required?: boolean
  appearance?: UserAppearanceOut
  ui_preferences?: UserUiPreferencesOut
}

export function userIsMasterRecovery(me: UserPublic | null | undefined): boolean {
  return Boolean(me?.is_master_recovery)
}

export function userCanAccessAdminConsole(me: UserPublic | null | undefined): boolean {
  if (userIsMasterRecovery(me)) return false
  return Boolean(me?.admin_console_access || me?.role === 'admin')
}

export type CalendarView = 'dayGridMonth' | 'timeGridWeek' | 'timeGridDay' | 'listYear'
export type TaskLayout = 'list' | 'kanban'
export type TaskSortKey = 'reference' | 'client' | 'matter' | 'task' | 'date' | 'assigned' | 'priority'
export type MainMenuSortKey = 'reference' | 'client' | 'matter' | 'feeEarner' | 'status' | 'created'
export type ContactsSortKey = 'name' | 'type' | 'email' | 'phone'
export type CaseStatusFilter = '' | 'open' | 'closed' | 'archived' | 'quote' | 'post_completion'
export type SortDir = 'asc' | 'desc'

export type UserUiPreferencesOut = {
  calendar_view: CalendarView
  case_calendar_view: CalendarView
  tasks_menu_layout: TaskLayout
  case_tasks_layout: TaskLayout
  tasks_menu_sort_key: TaskSortKey
  tasks_menu_sort_dir: SortDir
  case_tasks_sort_key: TaskSortKey
  case_tasks_sort_dir: SortDir
  main_menu_sort_key: MainMenuSortKey
  main_menu_sort_dir: SortDir
  main_menu_search: string
  main_menu_filter_matter_type: string
  main_menu_filter_fee_earner_user_id: string
  main_menu_filter_case_status: CaseStatusFilter
  main_menu_filter_matter_types: string[]
  main_menu_filter_fee_earner_user_ids: string[]
  main_menu_filter_case_statuses: Exclude<CaseStatusFilter, ''>[]
  tasks_menu_search: string
  tasks_menu_filter_matter_type: string
  contacts_search: string
  contacts_sort_key: ContactsSortKey
  contacts_sort_dir: SortDir
  calendar_selected_calendar_ids: string[]
  main_menu_column_widths: number[]
  tasks_menu_column_widths: number[]
  contacts_column_widths: number[]
}

export type ChangePasswordResponse = TokenResponse & {
  user: UserPublic
}

export type ForgotPasswordResponse = {
  message: string
}

export type AdminSendPasswordResetResponse = {
  email_sent: boolean
  message?: string | null
}

export type UserAppearanceOut = {
  font: string
  accent: string
  mode: 'light' | 'dark'
  page_bg: string
}

/** POST /auth/2fa/verify — new JWT after enrolment (org mandate / session upgrade). */
export type Verify2FASessionResponse = TokenResponse & {
  user: UserPublic
}

/** Admin-only user row (includes permission category). */
export type AdminUserPublic = UserPublic & {
  permission_category_id?: string | null
  charge_rate_pence_per_hour?: number | null
}

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
  mandate_two_factor?: boolean
  mandate_password_rotation?: boolean
  password_rotation_days?: number | null
  client_bank_account_name?: string | null
  client_bank_sort_code?: string | null
  client_bank_account_number_last4?: string | null
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
export type WebAuthnCredentialOut = {
  id: string
  label: string | null
  transports: string | null
  created_at: string
}

export type UserPermissionCategoryOut = {
  id: string
  name: string
  perm_fee_earner: boolean
  perm_post_client: boolean
  perm_post_office: boolean
  perm_approve_payments: boolean
  perm_approve_invoices: boolean
  perm_admin: boolean
  created_at: string
  updated_at: string
  is_builtin_template?: boolean
}

export type LedgerPermissionsOut = {
  can_approve_ledger: boolean
  can_approve_invoices?: boolean
  accounts_workspace_access?: boolean
  can_post_client?: boolean
  can_post_office?: boolean
}

export function userCanAccessAccountsWorkspace(me: UserPublic | null | undefined): boolean {
  if (userCanAccessAdminConsole(me)) return true
  return Boolean(me?.accounts_workspace_access)
}

/** Cashiers (accounts desk, not admin) land on Accounts instead of the main menu by default. */
export function userIsCashierAccountsHome(me: UserPublic | null | undefined): boolean {
  if (!me || userCanAccessAdminConsole(me)) return false
  return Boolean(me.accounts_workspace_access)
}

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

export type UserCalDAVStatusOut = {
  enabled: boolean
  caldav_url: string
  caldav_username: string
}

export type UserCalDAVProvisionOut = {
  caldav_url: string
  caldav_username: string
  caldav_password: string
  note: string
}

export type CalendarEventOut = {
  id: string
  uid: string
  title: string
  start: string
  end: string
  all_day: boolean
  description?: string | null
  calendar_name?: string | null
  calendar_id?: string | null
  can_edit?: boolean
  /** Canary-only; not in Radicale. */
  category_id?: string | null
  category_name?: string | null
  category_color?: string | null
  case_id?: string | null
  case_event_id?: string | null
  track_in_calendar?: boolean | null
  matter_template_id?: string | null
  email_alert_enabled?: boolean
}

export type CalendarCategoryOut = {
  id: string
  calendar_id: string
  name: string
  color?: string | null
}

export type UserCalendarListItem = {
  id: string
  name: string
  radicale_slug: string
  is_public: boolean
  access: 'owner' | 'read' | 'write'
  source: 'owned' | 'share' | 'subscription'
  owner: { id: string; display_name: string; email: string }
}

export type CalendarDirectoryRow = {
  id: string
  name: string
  owner: { id: string; display_name: string; email: string }
  is_public: boolean
  shared_directly: boolean
  already_in_my_list: boolean
  can_subscribe: boolean
}

export type CalendarShareOut = {
  grantee_user_id: string
  grantee_display_name: string
  grantee_email: string
  can_write: boolean
}

export type MatterSubTypeMenuOut = {
  id: string
  name: string
}

export type MatterSubTypeOut = {
  id: string
  name: string
  prefix?: string | null
  menus: MatterSubTypeMenuOut[]
}

export type MatterHeadTypeOut = {
  id: string
  name: string
  /** When true, non-admin matter pickers omit this head; admins can still configure sub-types. */
  is_hidden?: boolean
  sub_types: MatterSubTypeOut[]
}

export type MatterMenuItemOut = {
  id: string
  name: string
}

/** Stored case workflow status (`open` is shown as Active in the UI). */
export type CaseWorkflowStatus = 'open' | 'closed' | 'archived' | 'quote' | 'post_completion'

export function formatCaseStatusLabel(status: string): string {
  switch (status) {
    case 'open':
      return 'Active'
    case 'closed':
      return 'Closed'
    case 'archived':
      return 'Archived'
    case 'quote':
      return 'Quote'
    case 'post_completion':
      return 'Post-completion'
    default:
      return status
  }
}

export type CaseOut = {
  id: string
  case_number: string
  client_name?: string | null
  matter_description: string
  fee_earner_user_id: string
  status: CaseWorkflowStatus
  practice_area?: string | null
  matter_sub_type_id?: string | null
  /** Derived from the matter sub-type; may be set without sub for legacy rows. */
  matter_head_type_id?: string | null
  matter_sub_type_name?: string | null
  matter_head_type_name?: string | null
  matter_menus?: MatterMenuItemOut[]
  source_id?: string | null
  source_name?: string | null
  created_by: string
  is_locked: boolean
  lock_mode: 'none' | 'open_by_default' | 'allow_list'
  portal_enabled?: boolean
  created_at: string
  updated_at: string
}

/** True when the matter should show as access-locked (🔒 / “Locked”). */
export function caseHasRevokedUserAccess(c: Pick<CaseOut, 'is_locked' | 'lock_mode'>): boolean {
  if (c.lock_mode === 'allow_list') return true
  if (c.lock_mode === 'open_by_default') return Boolean(c.is_locked)
  return false
}

export type CaseAccessRuleOut = {
  id: string
  case_id: string
  user_id: string
  mode: 'allow' | 'deny'
}

export type CasePropertyUK = {
  line1?: string | null
  line2?: string | null
  town?: string | null
  county?: string | null
  postcode?: string | null
  country?: string | null
}

export type CasePropertyTenure = 'freehold' | 'leasehold' | 'commonhold'

export type CasePropertyPayload = {
  is_non_postal: boolean
  uk: CasePropertyUK
  free_lines: string[]
  title_numbers: string[]
  tenure?: CasePropertyTenure | null
}

export type CasePropertyDetailsOut = {
  has_details: boolean
  payload: CasePropertyPayload
  updated_at?: string | null
}

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

export type FeeScaleLineKind = 'section_header' | 'item' | 'vat' | 'subtotal' | 'total'
export type FeeScaleAmountKind = 'fixed' | 'editable' | 'band'

export type FeeScaleOut = {
  id: string
  name: string
  reference: string
  vat_rate_bps: number
  matter_head_type_id?: string | null
  matter_sub_type_id?: string | null
  matter_head_type_name?: string | null
  matter_sub_type_name?: string | null
  scope_summary?: string | null
  is_favorited?: boolean
  created_at: string
  updated_at: string
}

export type FeeScaleLineOut = {
  id: string
  category_id: string
  name: string
  line_kind: FeeScaleLineKind
  amount_kind?: FeeScaleAmountKind | null
  default_amount_pence?: number | null
  band_set_id?: string | null
  vat_treatment: 'included' | 'plus_vat'
  sort_order: number
}

export type FeeScaleCategoryOut = {
  id: string
  fee_scale_id: string
  name: string
  sort_order: number
  lines: FeeScaleLineOut[]
}

export type FeeScaleBandRowOut = {
  id: string
  band_set_id: string
  min_value_pence: number
  max_value_pence?: number | null
  amount_pence: number
  sort_order: number
}

export type FeeScaleBandSetOut = {
  id: string
  fee_scale_id: string
  name: string
  sort_order: number
  rows: FeeScaleBandRowOut[]
}

export type FeeScaleDetailOut = FeeScaleOut & {
  categories: FeeScaleCategoryOut[]
  band_sets: FeeScaleBandSetOut[]
}

export type QuotePreviewLineOut = {
  key?: string | null
  line_id?: string | null
  name: string
  line_kind: string
  amount_pence?: number | null
  amount_display?: string | null
  editable: boolean
  is_bold: boolean
  vat_pence?: number | null
  vat_treatment?: 'included' | 'plus_vat' | null
  amount_kind?: string | null
  band_set_id?: string | null
  sort_order?: number
}

export type QuotePreviewCategoryOut = {
  key: string
  category_id?: string | null
  name: string
  sort_order: number
  lines: QuotePreviewLineOut[]
}

export type QuotePreviewOut = {
  fee_scale_id: string
  property_value_pence?: number | null
  needs_property_value: boolean
  lines: QuotePreviewLineOut[]
  categories?: QuotePreviewCategoryOut[]
}

export type QuoteDraftLine = {
  key: string
  line_id?: string | null
  name: string
  line_kind: FeeScaleLineKind
  amount_kind?: FeeScaleAmountKind | null
  amount_pence?: number | null
  vat_treatment: 'included' | 'plus_vat'
  band_set_id?: string | null
  sort_order: number
}

export type QuoteDraftCategory = {
  key: string
  category_id?: string | null
  name: string
  sort_order: number
  lines: QuoteDraftLine[]
}

export type UserSummary = {
  id: string
  email: string
  display_name: string
  initials?: string
  role: string
  is_active: boolean
  can_be_fee_earner?: boolean
  has_charge_rate?: boolean
}

export type CaseNoteOut = {
  id: string
  case_id: string
  author_user_id: string
  body: string
  created_at: string
  updated_at: string
}

export type CaseTaskPriority = 'low' | 'normal' | 'high'

export type CaseTaskOut = {
  id: string
  case_id: string
  created_by_user_id: string
  title: string
  description?: string | null
  status: 'open' | 'done' | 'cancelled'
  due_at?: string | null
  standard_task_id?: string | null
  assigned_to_user_id?: string | null
  assigned_display_name?: string | null
  priority?: CaseTaskPriority
  case_event_id?: string | null
  is_private?: boolean
  created_at: string
  updated_at: string
}

export type CaseTimeEntryOut = {
  id: string
  case_id: string
  user_id: string
  user_display_name: string
  created_by_user_id: string
  work_date: string
  duration_minutes: number
  duration_tenths: number
  description: string
  status: 'unbilled' | 'billed' | 'written_off'
  invoice_line_id?: string | null
  non_billable?: boolean
  charge_rate_pence_per_hour?: number | null
  value_pence?: number | null
  created_at: string
  updated_at: string
}

export type MatterSubTypeStandardTaskOut = {
  id: string
  matter_sub_type_id: string | null
  title: string
  sort_order: number
  is_system?: boolean
  created_at: string
  updated_at: string
}

/** One row on the top-level Tasks list. Filled when task/case rules are configured; empty by default. */
export type TaskMenuRow = {
  id: string
  case_id: string
  case_number: string
  client_name: string | null
  matter_description: string | null
  /** Same shape as main-menu matter type filter (e.g. head · sub). */
  matter_type_label: string
  task_title: string
  is_private?: boolean
  /** Due date or other relevant task date (ISO 8601). */
  date: string
  assigned_display_name: string | null
  priority: CaseTaskPriority
  status: 'open' | 'done' | 'cancelled'
  standard_task_id?: string | null
  standard_task_category_title?: string | null
}

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
}

export type PortalQuoteDeliveryViewOut = {
  id: string
  file_id: string
  grant_id: string | null
  original_filename: string
  mime_type?: string
  size_bytes?: number
  folder_display?: string
  status: string
  can_respond: boolean
  decline_reason: string | null
  responded_at: string | null
}

export type PortalQuoteExchangeOut = {
  session_token: string
  contact_name: string
  grants: PortalGrantSummaryOut[]
  quote: PortalQuoteDeliveryViewOut
}

/** Response from ``POST /cases/{id}/files/email-drafts/m365`` (Microsoft Graph draft). */
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

/** Response from ``POST /cases/{id}/files/email-mailto``. */
export type CaseEmailMailtoOut = {
  to: string
  subject: string
  body: string
  attachment_count: number
  note: string
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

export type AdminAuditEvent = {
  id: string
  actor_user_id: string | null
  actor_display_name: string | null
  actor_initials: string | null
  action: string
  summary: string
  entity_type: string | null
  entity_id: string | null
  case_id: string | null
  case_number: string | null
  case_title: string | null
  ip: string | null
  user_agent: string | null
  meta: Record<string, unknown> | null
  created_at: string
}

export type ContactOut = {
  id: string
  type: 'person' | 'organisation'
  name: string
  email?: string | null
  phone?: string | null
  // Person name fields
  title?: string | null
  first_name?: string | null
  middle_name?: string | null
  last_name?: string | null
  // Organisation fields
  company_name?: string | null
  trading_name?: string | null
  // Address
  address_line1?: string | null
  address_line2?: string | null
  city?: string | null
  county?: string | null
  postcode?: string | null
  country?: string | null
  created_at: string
  updated_at: string
}

export type CaseContactOut = {
  id: string
  case_id: string
  contact_id: string | null
  is_linked_to_master: boolean
  type: 'person' | 'organisation'
  name: string
  email?: string | null
  phone?: string | null
  // Person name fields
  title?: string | null
  first_name?: string | null
  middle_name?: string | null
  last_name?: string | null
  // Organisation fields
  company_name?: string | null
  trading_name?: string | null
  // Address
  address_line1?: string | null
  address_line2?: string | null
  city?: string | null
  county?: string | null
  postcode?: string | null
  country?: string | null
  /** Matter-specific; not stored on the global contact card. */
  matter_contact_type?: string | null
  /** Matter-specific free text; not stored on the global contact card. */
  matter_contact_reference?: string | null
  /** When matter contact type is Lawyers: linked matter contacts (max 4). */
  lawyer_client_ids?: string[]
  created_at: string
  updated_at: string
}

export type MatterContactTypeOut = {
  id: string
  slug: string
  label: string
  sort_order: number
  is_system: boolean
}

// ---------------------------------------------------------------------------
// Ledger
// ---------------------------------------------------------------------------

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

export type FinanceItemTemplateOut = {
  id: string
  category_id: string
  name: string
  direction: 'debit' | 'credit'
  sort_order: number
}

export type FinanceCategoryTemplateOut = {
  id: string
  matter_sub_type_id: string
  name: string
  sort_order: number
  credit_only: boolean
  items: FinanceItemTemplateOut[]
}

export type FinanceTemplateOut = {
  matter_sub_type_id: string
  categories: FinanceCategoryTemplateOut[]
}

// ---------------------------------------------------------------------------
// Finance case data
// ---------------------------------------------------------------------------

export type FinanceItemOut = {
  id: string
  category_id: string
  template_item_id?: string | null
  name: string
  direction: 'debit' | 'credit'
  amount_pence?: number | null
  vat_pence?: number | null
  vat_treatment?: 'included' | 'plus_vat' | null
  sort_order: number
}

export type FinanceCategoryOut = {
  id: string
  case_id: string
  template_category_id?: string | null
  name: string
  sort_order: number
  credit_only: boolean
  items: FinanceItemOut[]
}

export type FinanceOut = {
  case_id: string
  categories: FinanceCategoryOut[]
  has_finance_preset?: boolean
  has_quote_snapshot?: boolean
  vat_rate_bps?: number
}

export type CaseSourceOut = {
  id: string
  name: string
  sort_order: number
  is_system: boolean
}

// Sub-menu Events (admin template + case rows)
export type MatterSubTypeEventTemplateOut = {
  id: string
  matter_sub_type_id: string
  name: string
  sort_order: number
  notify_on_day?: boolean
  notify_every_n?: number | null
  notify_every_unit?: 'days' | 'weeks' | 'months' | null
  created_at: string
  updated_at: string
}

/** Admin calendar template lines for quick-fill on the main CalDAV calendar. */
export type CalendarEventTemplatePickOut = {
  id: string
  matter_sub_type_id: string
  matter_sub_type_name: string
  name: string
  sort_order: number
  notify_on_day?: boolean
  notify_every_n?: number | null
  notify_every_unit?: 'days' | 'weeks' | 'months' | null
}

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

export type CaseEventOut = {
  id: string
  case_id: string
  template_id?: string | null
  name: string
  sort_order: number
  event_date?: string | null
  event_all_day?: boolean
  event_start_time?: string | null
  calendar_block_start?: string | null
  calendar_block_end?: string | null
  calendar_block_all_day?: boolean | null
  track_in_calendar?: boolean
  calendar_event_uid?: string | null
  email_alert_enabled?: boolean
  created_at: string
  updated_at: string
}

export type CaseEventsOut = {
  case_id: string
  events: CaseEventOut[]
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
}

export type PortalAuthOut = {
  session_token: string
  contact_name: string
  grants: PortalGrantSummaryOut[]
}

export type PortalSessionOut = {
  contact_name: string
  grants: PortalGrantSummaryOut[]
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
}

export type PortalBrowseOut = {
  subfolder: string
  breadcrumb: string[]
  subfolders: string[]
  files: PortalFileOut[]
  pending_approvals?: PortalQuoteDeliveryViewOut[]
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
}

export type CasePortalFolderAccessGrantOut = {
  folder_path: string
  contact_id: string
  contact_name: string
}

