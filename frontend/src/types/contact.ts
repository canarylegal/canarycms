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

export type ContactMergePreviewOut = {
  survivor: ContactOut
  source: ContactOut
  survivor_matter_links: number
  source_matter_links: number
  survivor_grants: number
  source_grants: number
  survivor_client_portal_active: boolean
  source_client_portal_active: boolean
  survivor_matter_portal_active: number
  source_matter_portal_active: number
  email_mismatch: boolean
  type_mismatch: boolean
  will_reset_client_portal: boolean
  will_reset_matter_portal_cases: number
}

export type ContactMergeOut = {
  survivor: ContactOut
  deleted_source_id: string
  client_portal_reset: boolean
  new_client_access_code?: string | null
  matter_portal_cases_reset: number
  grants_moved: number
  grants_deduped: number
  matter_links_moved: number
  email_sent?: boolean
  email_skip_reason?: string | null
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
  /** Letter opening salutation for precedents (matter snapshot only). */
  letter_salutation?: string | null
  letter_salutation_custom?: string | null
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
