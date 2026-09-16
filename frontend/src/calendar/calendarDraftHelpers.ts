import type { CalendarCategoryOut } from '../types'

export function pad2(n: number): string {
  return String(n).padStart(2, '0')
}

/** Options 00–23 */
export const HOURS_00_23 = Array.from({ length: 24 }, (_, i) => i)
/** Start minute column 00–59; bold 15, 30, 45 */
export const START_MINS_00_59 = Array.from({ length: 60 }, (_, i) => i)
/** Duration full days 0–99 (left of hours) */
export const DUR_DAYS_0_99 = Array.from({ length: 100 }, (_, i) => i)
/** Duration hours 0–24 */
export const DUR_HOURS_0_24 = Array.from({ length: 25 }, (_, i) => i)
/** Duration minutes 1–60; bold 15, 30, 45 in UI */
export const DUR_MINS_1_60 = Array.from({ length: 60 }, (_, i) => i + 1)

export const HOUR_SELECT_OPTIONS = HOURS_00_23.map((h) => ({ value: String(h), label: pad2(h) }))
export const START_MIN_SELECT_OPTIONS = START_MINS_00_59.map((m) => ({ value: String(m), label: pad2(m) }))
export const DUR_DAY_SELECT_OPTIONS = DUR_DAYS_0_99.map((d) => ({ value: String(d), label: String(d) }))
export const DUR_HOUR_SELECT_OPTIONS = DUR_HOURS_0_24.map((h) => ({ value: String(h), label: String(h) }))
export const DUR_MIN_SELECT_OPTIONS = DUR_MINS_1_60.map((m) => ({ value: String(m), label: String(m) }))

export type CalendarEventDropdownKey =
  | 'createCal'
  | 'createMatterType'
  | 'createCalLabel'
  | 'editCalLabel'
  | 'startH'
  | 'startM'
  | 'durD'
  | 'durH'
  | 'durM'

export function calendarLabelOptions(categories: CalendarCategoryOut[]) {
  return [
    { value: '', label: 'No label' },
    ...categories.map((c) => ({ value: c.id, label: c.name })),
  ]
}

export function buildCalDavTimesFromDraft(d: {
  allDay: boolean
  start: Date
  end: Date
  startHour: number
  startMinute: number
  durDays: number
  durHours: number
  durMinutes: number
}): { start: string; end: string; all_day: boolean } {
  if (d.allDay) {
    return { start: toBodyDate(d.start, true), end: toBodyDate(d.end, true), all_day: true }
  }
  const anchor = startOfLocalDay(d.start)
  const { start, end } = buildTimedStartEnd(
    anchor,
    d.startHour,
    d.startMinute,
    d.durDays,
    d.durHours,
    d.durMinutes,
  )
  return { start: toBodyDate(start, false), end: toBodyDate(end, false), all_day: false }
}

export function startOfLocalDay(d: Date): Date {
  const x = new Date(d)
  x.setHours(0, 0, 0, 0)
  return x
}

export function localYmdFromDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** Body for POST/PATCH ``/cases/{id}/events`` from the main calendar composer. */
export function buildCaseEventApiPayload(d: {
  title: string
  start: Date
  allDay: boolean
  startHour: number
  startMinute: number
  trackInCalendar: boolean
  emailAlert?: boolean
}): Record<string, unknown> {
  const datePart = localYmdFromDate(startOfLocalDay(d.start))
  const body: Record<string, unknown> = {
    name: d.title.trim(),
    event_date: datePart,
    event_all_day: d.allDay,
    track_in_calendar: d.trackInCalendar,
    email_alert: d.emailAlert ?? false,
  }
  if (!d.allDay) {
    body.event_start_time = `${pad2(d.startHour)}:${pad2(d.startMinute)}:00`
  } else {
    body.event_start_time = null
  }
  return body
}

export function addDaysLocal(d: Date, n: number): Date {
  const x = new Date(d)
  x.setDate(x.getDate() + n)
  return x
}

/** `startMinute` is 0–59. `durMinutes` is 1–60 for duration. */
export function buildTimedStartEnd(
  anchor: Date,
  startHour: number,
  startMinute: number,
  durDays: number,
  durHours: number,
  durMinutes: number,
): { start: Date; end: Date } {
  const s = new Date(anchor)
  const sm = Math.min(59, Math.max(0, Math.floor(startMinute)))
  s.setHours(startHour, sm, 0, 0)
  const dm = Math.min(60, Math.max(1, durMinutes))
  const dd = Math.min(99, Math.max(0, Math.floor(durDays)))
  let totalDurMin = dd * 24 * 60 + durHours * 60 + dm
  if (totalDurMin <= 0) {
    totalDurMin = 30
  }
  const e = new Date(s.getTime() + totalDurMin * 60_000)
  return { start: s, end: e }
}

export function splitRemainderToHoursMinutes(totalMin: number): { durHours: number; durMinutes: number } {
  let durH = Math.min(24, Math.floor(totalMin / 60))
  let rem = totalMin % 60
  if (rem === 0 && durH > 0) {
    durH -= 1
    rem = 60
  } else if (rem === 0) {
    rem = 1
  }
  return { durHours: durH, durMinutes: rem }
}

/** Split a timed range into days (0–99) + hours + minutes for the duration UI. */
export function timedDurationFromRange(start: Date, end: Date): { durDays: number; durHours: number; durMinutes: number } {
  const totalMin = Math.max(1, Math.round((end.getTime() - start.getTime()) / 60000))
  let durDays = Math.min(99, Math.floor(totalMin / (24 * 60)))
  let rem = totalMin - durDays * 24 * 60
  while (rem <= 0 && durDays > 0) {
    durDays -= 1
    rem += 24 * 60
  }
  if (rem <= 0) {
    rem = 1
  }
  const { durHours, durMinutes } = splitRemainderToHoursMinutes(rem)
  return { durDays, durHours, durMinutes }
}

export function startHourMinuteFromDate(d: Date): { startHour: number; startMinute: number } {
  return { startHour: d.getHours(), startMinute: d.getMinutes() }
}

export function toBodyDate(d: Date, allDay: boolean): string {
  if (allDay) {
    const y = d.getFullYear()
    const m = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    return `${y}-${m}-${day}`
  }
  return d.toISOString()
}

export type CalendarEventDraft =
  | {
      kind: 'create'
      title: string
      /** Selection anchor (date); times/duration apply when `allDay` is false. */
      start: Date
      end: Date
      allDay: boolean
      startHour: number
      /** 0–59 */
      startMinute: number
      durDays: number
      durHours: number
      /** 1–60 */
      durMinutes: number
      caseId: string
      /** Same as ``CaseEventCreateModal``: ``custom`` or existing case event row id. */
      eventCategory: 'custom' | string
      /** Calendar colour label (Canary-only; Radicale event gets category on sync). */
      categoryId: string | null
      /** Owned calendar used for labels and personal CalDAV events. */
      targetCalendarId: string
      trackInCalendar: boolean
      emailAlert: boolean
    }
  | {
      kind: 'edit'
      editSource: 'caldav' | 'case'
      id: string
      title: string
      description: string
      start: Date
      end: Date
      allDay: boolean
      startHour: number
      /** 0–59 */
      startMinute: number
      durDays: number
      durHours: number
      /** 1–60 */
      durMinutes: number
      canEdit: boolean
      calendarId: string
      categoryId: string | null
      categoryLabel: string | null
      targetCalendarId: string
      caseId?: string
      caseEventId?: string
      calendarEventUid?: string | null
      trackInCalendar?: boolean
      emailAlert: boolean
      /** CalDAV: optional matter template UUID stored on the event (X-CANARY-TEMPLATE-ID). */
      matterTemplateId?: string | null
    }
