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
