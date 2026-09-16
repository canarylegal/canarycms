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
  /** When ``email_launch_preference`` is ``desktop``: Outlook (M365 handoff) vs Thunderbird/other (mailto). */
  email_desktop_client?: 'outlook' | 'other'
  email_outlook_web_url?: string | null
  /** Org-wide: Admin → E-mail — desktop mailto vs Microsoft 365 Graph drafts. */
  email_integration_mode?: 'mailto' | 'microsoft_graph'
  /** True when mode is Graph and tenant/client/secret resolve (DB or env). */
  m365_graph_drafts_configured?: boolean
  /** From GET /auth/me — category Admin or built-in admin role. */
  admin_console_access?: boolean
  has_signature?: boolean
  signature_original_filename?: string | null
  /** 1–10; 7 ≈ 2 inches wide in composed documents. */
  signature_scale?: number
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

export type CaseStatusFilter = '' | 'open' | 'closed' | 'archived' | 'quote' | 'quote_closed' | 'post_completion'

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
  perm_post_anticipated: boolean
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
  can_post_anticipated?: boolean
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
