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
