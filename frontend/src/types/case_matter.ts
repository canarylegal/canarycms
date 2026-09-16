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

export type CaseWorkflowStatus = 'open' | 'closed' | 'archived' | 'quote' | 'quote_closed' | 'post_completion'

export function isQuoteWorkflowStatus(status: string): boolean {
  return status === 'quote' || status === 'quote_closed'
}

export function formatCaseStatusLabel(status: string): string {
  switch (status) {
    case 'open':
      return 'Active'
    case 'closed':
      return 'Closed'
    case 'quote_closed':
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

/** Stored reference without a leading Q (API may already include display prefix). */

export function stripCaseNumberPrefix(caseNumber: string): string {
  const s = (caseNumber || '').trim()
  if (s.length > 1 && /^Q/i.test(s) && /\d/.test(s[1]!)) return s.slice(1)
  return s
}

/** Matter reference for UI — Q prefix while status is quote. */

export function displayCaseNumber(caseNumber: string, status: string): string {
  const raw = stripCaseNumberPrefix(caseNumber)
  if (!raw) return raw
  if (status === 'quote') return `Q${raw}`
  return raw
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
  existing_lender_case_contact_id?: string | null
  charge_date?: string | null
}

export type CasePropertyDetailsOut = {
  has_details: boolean
  payload: CasePropertyPayload
  updated_at?: string | null
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
