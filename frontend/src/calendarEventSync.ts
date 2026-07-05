import { apiFetch } from './api'
import type { CalendarEventOut, CaseEventOut } from './types'

/** All-day UTC range for CalDAV (exclusive end date). */
export function allDayExclusiveEnd(iso: string | null | undefined): { start: string; end: string } | null {
  const d = iso?.slice(0, 10)
  if (!d || !/^\d{4}-\d{2}-\d{2}$/.test(d)) return null
  const [y, m, day] = d.split('-').map(Number)
  const next = new Date(Date.UTC(y, m - 1, day))
  next.setUTCDate(next.getUTCDate() + 1)
  return { start: d, end: next.toISOString().slice(0, 10) }
}

export function isWritableCalendar(c: { access: string }): boolean {
  return c.access === 'owner' || c.access === 'write'
}

/** Calendars the user may create events on (owned or shared with write). */
export function writableCalendars<T extends { access: string }>(calendars: T[]): T[] {
  return calendars.filter(isWritableCalendar)
}

export function defaultOwnedCalendarId(
  calendars: { id: string; source: string; access: string }[],
): string | null {
  const owned = calendars.filter(
    (c) => c.source === 'owned' && (c.access === 'owner' || c.access === 'write'),
  )
  return owned.length > 0 ? owned[0].id : null
}

/** Default calendar for new events — prefers a visible writable calendar, then first owned. */
export function defaultWritableCalendarId(
  calendars: { id: string; source: string; access: string }[],
  preferredIds?: string[],
): string | null {
  const writable = writableCalendars(calendars)
  if (writable.length === 0) return null
  if (preferredIds?.length) {
    const pick = preferredIds.find((id) => writable.some((c) => c.id === id))
    if (pick) return pick
  }
  const owned = writable.find((c) => c.source === 'owned')
  return owned?.id ?? writable[0].id
}

export function writableCalendarPickerOptions(
  calendars: {
    id: string
    name: string
    source: string
    access: string
    owner: { display_name: string }
  }[],
) {
  return writableCalendars(calendars).map((c) => ({
    value: c.id,
    label: c.source === 'owned' ? c.name : `${c.name} (${c.owner.display_name})`,
  }))
}

type CalDavEventBody = {
  title: string
  start: string
  end: string
  all_day: boolean
  description?: string | null
  calendar_id?: string | null
  category_id?: string | null
  email_alert?: boolean
  matter_sub_type_event_template_id?: string | null
}

/** Sync a tracked case event row to the user's CalDAV calendar (optional colour category). */
export async function syncCaseEventToCalDav(
  token: string,
  caseId: string,
  ev: CaseEventOut,
  opts: {
    caseLabel?: string
    categoryId?: string | null
    calendarId?: string | null
  },
): Promise<void> {
  if (!ev.track_in_calendar) return

  const label = (opts.caseLabel || 'Case').trim() || 'Case'
  const rangeAllDay = allDayExclusiveEnd(ev.event_date ?? null)
  const timed =
    ev.calendar_block_all_day === false && ev.calendar_block_start && ev.calendar_block_end

  if (!timed && !rangeAllDay) return

  const title = `${label}: ${ev.name}`.slice(0, 500)
  const desc = `Canary tracked case event (${label}).`
  const tid = ev.template_id ?? null

  const calBody: CalDavEventBody = timed
    ? {
        title,
        start: ev.calendar_block_start!,
        end: ev.calendar_block_end!,
        all_day: false,
        description: desc,
        matter_sub_type_event_template_id: tid,
        category_id: opts.categoryId ?? null,
        calendar_id: opts.calendarId ?? null,
        email_alert: Boolean(ev.email_alert_enabled),
      }
    : {
        title,
        start: rangeAllDay!.start,
        end: rangeAllDay!.end,
        all_day: true,
        description: desc,
        matter_sub_type_event_template_id: tid,
        category_id: opts.categoryId ?? null,
        calendar_id: opts.calendarId ?? null,
        email_alert: Boolean(ev.email_alert_enabled),
      }

  if (ev.calendar_event_uid) {
    try {
      await apiFetch(`/users/me/calendar/events/${encodeURIComponent(ev.calendar_event_uid)}`, {
        method: 'PATCH',
        token,
        json: calBody,
      })
      return
    } catch {
      /* recreate below */
    }
  }

  try {
    const created = await apiFetch<CalendarEventOut>(`/users/me/calendar/events`, {
      method: 'POST',
      token,
      json: calBody,
    })
    await apiFetch(`/cases/${caseId}/events/${ev.id}`, {
      token,
      method: 'PATCH',
      json: { calendar_event_uid: created.id },
    })
  } catch {
    /* CalDAV unavailable */
  }
}
