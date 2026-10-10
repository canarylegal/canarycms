export type HmlrIntegrationSettingsOut = {
  enabled: boolean
  sandbox: boolean
  username?: string | null
  password_configured: boolean
  customer_reference?: string | null
  contact_name?: string | null
  contact_phone?: string | null
  configured: boolean
  mock_mode: boolean
}

export type HmlrOrderOut = {
  id: string
  title_number: string
  external_reference: string
  want_register: boolean
  want_title_plan: boolean
  state: string
  fee_pence: number
  error_message?: string | null
  register_file_id?: string | null
  plan_file_id?: string | null
  sandbox: boolean
  placed_at?: string | null
  completed_at?: string | null
  created_at: string
}

export type HmlrSummaryOut = {
  configured: boolean
  enabled: boolean
  sandbox: boolean
  mock_mode: boolean
  orders: HmlrOrderOut[]
  suggested_title_numbers: string[]
}
