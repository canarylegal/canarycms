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
