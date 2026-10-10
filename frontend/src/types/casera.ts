export type CaseraIntegrationSettingsOut = {
  enabled: boolean
  sandbox: boolean
  client_id?: string | null
  access_token_configured: boolean
  webhook_secret_configured: boolean
  webhook_path_token?: string | null
  webhook_url?: string | null
  api_base_uri?: string | null
  post_anticipated_disbursement?: boolean
  add_to_completion_statement?: boolean
  email_on_result_ready?: boolean
  configured: boolean
}

export type CaseraOrderProductOut = {
  id: string
  casera_product_id: string
  casera_order_product_id?: string | null
  name: string
  state: string
  price_pence: number
  due_at?: string | null
  file_id?: string | null
  file_ids?: string[]
}

export type CaseraRiskBadgeOut = {
  key: string
  label: string
  available: boolean
  level?: string | null
  product_ids: string[]
  detail?: string | null
}

export type CaseraOrderOut = {
  id: string
  casera_order_id: string
  category: string
  state: string
  total_pence: number
  due_at?: string | null
  placed_at?: string | null
  created_at: string
  products: CaseraOrderProductOut[]
  selected_product_ids?: string[]
  selected_pack_ids?: string[]
}

export type CaseraSearchesSummaryOut = {
  configured: boolean
  enabled: boolean
  /** Install-wide provider for the Searches menu (`none` | `casera` | …). */
  provider?: string
  orders: CaseraOrderOut[]
  total_pence: number
  suggested_reference?: string
  /** Set once this matter is linked to a Casera case. */
  casera_reference?: string | null
}

export type CaseraConveyancingDetails = {
  type: string
  new_build: boolean
  title_numbers: string[]
  building_identifier?: string | null
  street?: string | null
  locality?: string | null
  town_city?: string | null
  county?: string | null
  postcode?: string | null
  uprn?: string | null
  centroid?: number[] | null
  polygons?: number[][][] | null
  hectares?: number | null
  perimeter?: number | null
  local_authority?: string | null
  water_authority?: string | null
  drainage_authority?: string | null
}

export type CaseraPrefillOut = {
  conveyancing: CaseraConveyancingDetails
  from_property: boolean
  suggested_reference?: string
  casera_reference?: string | null
}

export type CaseraAvailableProductOut = {
  id: string
  name: string
  price_pence?: number | null
  subcategory?: string | null
  description?: string | null
  group?: string | null
}

export type CaseraAvailablePackOut = {
  id: string
  name: string
  price_pence?: number | null
  product_ids: string[]
  product_names?: string[]
}

export type CaseraCreateOrderOut = {
  order: CaseraOrderOut
  products: CaseraAvailableProductOut[]
  packs: CaseraAvailablePackOut[]
  risks: Record<string, unknown>
  risk_badges?: CaseraRiskBadgeOut[]
}

export type CaseraSearchFileSummary = {
  order_product_id: string
  product_name: string
  state: string
  due_at?: string | null
  status_label: string
}
