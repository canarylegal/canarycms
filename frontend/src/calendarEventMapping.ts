import type { EventInput } from '@fullcalendar/core'
import type { CalendarEventOut } from './types'

function contrastTextForBg(hex: string): string {
  const h = hex.replace(/^#/, '')
  if (h.length !== 6) return '#ffffff'
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  const yiq = (r * 299 + g * 587 + b * 114) / 1000
  return yiq >= 128 ? '#1a1a1a' : '#ffffff'
}

function isoDateOnlyFromApi(s: string): string {
  const m = /^(\d{4}-\d{2}-\d{2})/.exec(s.trim())
  return m ? m[1] : s
}

export function addOneCalendarDayYmd(isoYmd: string): string {
  const [y, mo, d] = isoYmd.split('-').map(Number)
  const dt = new Date(y, mo - 1, d)
  dt.setDate(dt.getDate() + 1)
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`
}

export function fullCalendarRangeFromApi(r: CalendarEventOut): { start: string; end: string; allDay: boolean } {
  if (!r.all_day) {
    return { start: r.start, end: r.end, allDay: false }
  }
  const start = isoDateOnlyFromApi(r.start)
  let end = isoDateOnlyFromApi(r.end)
  if (end <= start) {
    end = addOneCalendarDayYmd(start)
  }
  return { start, end, allDay: true }
}

export function stripLeadingCalendarTitle(title: string): string {
  const once = title.replace(/^\s*\d{1,3}[.)]\s+/, '').replace(/^\s*\d{1,3}\)\s+/, '').trim()
  return once.length > 0 ? once : title
}

export function mapCalendarEventsToFullCalendar(rows: CalendarEventOut[]): EventInput[] {
  return rows.map((r) => {
    const range = fullCalendarRangeFromApi(r)
    const isCaseEvent = Boolean(r.case_event_id)
    return {
      id: r.id,
      title: stripLeadingCalendarTitle(r.title),
      start: range.start,
      end: range.end,
      allDay: range.allDay,
      editable: r.can_edit !== false && !isCaseEvent,
      display: 'block',
      backgroundColor: r.category_color ?? undefined,
      borderColor: r.category_color ?? undefined,
      textColor: r.category_color ? contrastTextForBg(r.category_color) : undefined,
      extendedProps: {
        description: r.description ?? '',
        calendar_id: r.calendar_id,
        can_edit: r.can_edit !== false,
        category_id: r.category_id ?? null,
        category_name: r.category_name ?? null,
        category_color: r.category_color ?? null,
        api_all_day: r.all_day,
        case_id: r.case_id ?? null,
        case_event_id: r.case_event_id ?? null,
        track_in_calendar: r.track_in_calendar ?? null,
        email_alert_enabled: r.email_alert_enabled ?? false,
        matter_template_id: r.matter_template_id ?? null,
      },
    }
  })
}

/** Coerce FullCalendar event start/end to YYYY-MM-DD for api_all_day transform. */
export function eventInputToYmd(v: EventInput['start']): string | undefined {
  if (v == null) return undefined
  if (typeof v === 'string') return isoDateOnlyFromApi(v)
  if (v instanceof Date) {
    const y = v.getFullYear()
    const m = String(v.getMonth() + 1).padStart(2, '0')
    const day = String(v.getDate()).padStart(2, '0')
    return `${y}-${m}-${day}`
  }
  return undefined
}
