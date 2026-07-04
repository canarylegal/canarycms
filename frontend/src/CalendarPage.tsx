import type {
  DateSelectArg,
  EventChangeArg,
  EventClickArg,
  EventInput,
  EventMountArg,
} from '@fullcalendar/core'
import interactionPlugin from '@fullcalendar/interaction'
import listPlugin from '@fullcalendar/list'
import FullCalendar from '@fullcalendar/react'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import type { CSSProperties } from 'react'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { apiFetch } from './api'
import type { ApiError } from './api'
import { ConfirmModal } from './ConfirmModal'
import { useDialogs } from './DialogProvider'
import { MatterSearchPicker } from './MatterSearchPicker'
import { SearchInput } from './SearchInput'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import { useExclusiveDropdownOpen } from './useExclusiveDropdownOpen'
import { CALENDAR_LIST_YEAR_VIEW, calendarListEventContent, calendarNoEventsContent } from './calendarListView'
import {
  calendarEventCacheKey,
  invalidateCalendarEventCache,
  readCalendarEventCache,
  writeCalendarEventCache,
} from './calendarEventCache'
import {
  addOneCalendarDayYmd,
  eventInputToYmd,
  mapCalendarEventsToFullCalendar,
} from './calendarEventMapping'
import { useUserUiPreferences, type CalendarView } from './useUserUiPreferences'
import {
  defaultWritableCalendarId,
  syncCaseEventToCalDav,
  writableCalendarPickerOptions,
} from './calendarEventSync'
import type {
  CalendarCategoryOut,
  CalendarDirectoryRow,
  CalendarEventOut,
  CalendarShareOut,
  CaseEventOut,
  CaseOut,
  UserCalendarListItem,
  UserPublic,
  UserSummary,
} from './types'

function CalendarCategoriesPanel({
  token,
  calendar,
  rows,
  isOwner,
  busy,
  setBusy,
  setErr,
  onRefresh,
  embedded = false,
}: {
  token: string
  calendar: UserCalendarListItem
  rows: CalendarCategoryOut[]
  isOwner: boolean
  busy: boolean
  setBusy: (v: boolean) => void
  setErr: (v: string | null) => void
  onRefresh: () => void
  /** Hide calendar name row when nested under calendar Edit screen */
  embedded?: boolean
}) {
  const { askConfirm } = useDialogs()
  const [newName, setNewName] = useState('')
  const [newColor, setNewColor] = useState('')

  async function add() {
    const name = newName.trim()
    if (!name) return
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/users/me/calendars/${calendar.id}/categories`, {
        method: 'POST',
        token,
        json: { name, color: newColor.trim() || null },
      })
      setNewName('')
      setNewColor('')
      onRefresh()
    } catch (e: unknown) {
      setErr((e as ApiError).message ?? 'Add failed')
    } finally {
      setBusy(false)
    }
  }

  async function removeCategory(catId: string) {
    const ok = await askConfirm({
      title: 'Delete category',
      message: 'Delete this category? Events keep their times but lose this colour in Canary.',
      danger: true,
      confirmLabel: 'Delete',
    })
    if (!ok) return
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/users/me/calendars/${calendar.id}/categories/${catId}`, { method: 'DELETE', token })
      onRefresh()
    } catch (e: unknown) {
      setErr((e as ApiError).message ?? 'Delete failed')
    } finally {
      setBusy(false)
    }
  }

  async function patchColor(catId: string, raw: string) {
    const c = raw.trim()
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/users/me/calendars/${calendar.id}/categories/${catId}`, {
        method: 'PATCH',
        token,
        json: { color: c || null },
      })
      onRefresh()
    } catch (e: unknown) {
      setErr((e as ApiError).message ?? 'Update failed')
    } finally {
      setBusy(false)
    }
  }

  const colorInputStyle: CSSProperties = {
    width: 40,
    height: 32,
    padding: 0,
    border: '1px solid var(--border)',
    borderRadius: 6,
    cursor: busy ? 'not-allowed' : 'pointer',
    background: 'transparent',
    verticalAlign: 'middle',
  }

  return (
    <div style={{ marginBottom: embedded ? 0 : 16, padding: embedded ? 0 : 12, border: embedded ? 'none' : '1px solid var(--border)', borderRadius: embedded ? 0 : 8 }}>
      {embedded ? null : (
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 8 }}>
          <strong>{calendar.name}</strong>
          <span className="muted" style={{ fontSize: 12 }}>
            {calendar.source !== 'owned' ? `${calendar.owner.display_name} · ` : ''}
            {isOwner ? 'owner' : calendar.access === 'read' ? 'read-only' : 'can edit events'}
          </span>
        </div>
      )}
      {rows.length === 0 ? (
        <div className="muted" style={{ fontSize: 13, marginTop: 8 }}>No categories yet.</div>
      ) : (
        <ul style={{ margin: '10px 0 0', paddingLeft: 18 }}>
          {rows.map((cat) => (
            <li key={cat.id} style={{ marginBottom: 8 }}>
              <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <span
                  title={cat.color ?? 'No colour'}
                  style={{
                    width: 14,
                    height: 14,
                    borderRadius: 4,
                    background: cat.color || 'var(--border)',
                    border: '1px solid var(--border)',
                    flexShrink: 0,
                  }}
                />
                <span>{cat.name}</span>
                {isOwner ? (
                  <>
                    <input
                      type="color"
                      aria-label={`Colour for ${cat.name}`}
                      title="Choose colour"
                      value={cat.color ?? '#888888'}
                      disabled={busy}
                      style={colorInputStyle}
                      onChange={(e) => void patchColor(cat.id, e.target.value)}
                    />
                    {cat.color ? (
                      <button
                        type="button"
                        className="btn"
                        style={{ fontSize: 12, padding: '2px 8px' }}
                        disabled={busy}
                        onClick={() => void patchColor(cat.id, '')}
                      >
                        Clear colour
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="btn"
                      style={{ fontSize: 12, padding: '2px 8px' }}
                      disabled={busy}
                      onClick={() => void removeCategory(cat.id)}
                    >
                      Delete
                    </button>
                  </>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
      {isOwner ? (
        <div className="row" style={{ gap: 8, flexWrap: 'wrap', marginTop: 12, alignItems: 'center' }}>
          <input
            placeholder="New category name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            style={{ flex: '1 1 160px', minWidth: 140 }}
            disabled={busy}
          />
          <label className="row" style={{ gap: 6, alignItems: 'center' }}>
            <span className="muted" style={{ fontSize: 13 }}>
              Colour
            </span>
            <input
              type="color"
              aria-label="Pick colour for new category"
              title="Choose colour (optional)"
              value={newColor || '#888888'}
              disabled={busy}
              style={colorInputStyle}
              onChange={(e) => setNewColor(e.target.value)}
            />
          </label>
          {newColor ? (
            <button type="button" className="btn" style={{ fontSize: 12, padding: '2px 8px' }} disabled={busy} onClick={() => setNewColor('')}>
              Clear colour
            </button>
          ) : null}
          <button type="button" className="btn primary" disabled={busy || !newName.trim()} onClick={() => void add()}>
            Add category
          </button>
        </div>
      ) : null}
    </div>
  )
}

function pad2(n: number): string {
  return String(n).padStart(2, '0')
}

/** Options 00–23 */
const HOURS_00_23 = Array.from({ length: 24 }, (_, i) => i)
/** Start minute column 00–59; bold 15, 30, 45 */
const START_MINS_00_59 = Array.from({ length: 60 }, (_, i) => i)
/** Duration full days 0–99 (left of hours) */
const DUR_DAYS_0_99 = Array.from({ length: 100 }, (_, i) => i)
/** Duration hours 0–24 */
const DUR_HOURS_0_24 = Array.from({ length: 25 }, (_, i) => i)
/** Duration minutes 1–60; bold 15, 30, 45 in UI */
const DUR_MINS_1_60 = Array.from({ length: 60 }, (_, i) => i + 1)

const HOUR_SELECT_OPTIONS = HOURS_00_23.map((h) => ({ value: String(h), label: pad2(h) }))
const START_MIN_SELECT_OPTIONS = START_MINS_00_59.map((m) => ({ value: String(m), label: pad2(m) }))
const DUR_DAY_SELECT_OPTIONS = DUR_DAYS_0_99.map((d) => ({ value: String(d), label: String(d) }))
const DUR_HOUR_SELECT_OPTIONS = DUR_HOURS_0_24.map((h) => ({ value: String(h), label: String(h) }))
const DUR_MIN_SELECT_OPTIONS = DUR_MINS_1_60.map((m) => ({ value: String(m), label: String(m) }))

type CalendarEventDropdownKey =
  | 'createCal'
  | 'createMatterType'
  | 'createCalLabel'
  | 'editCalLabel'
  | 'startH'
  | 'startM'
  | 'durD'
  | 'durH'
  | 'durM'

function calendarLabelOptions(categories: CalendarCategoryOut[]) {
  return [
    { value: '', label: 'No label' },
    ...categories.map((c) => ({ value: c.id, label: c.name })),
  ]
}

function buildCalDavTimesFromDraft(d: {
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

function startOfLocalDay(d: Date): Date {
  const x = new Date(d)
  x.setHours(0, 0, 0, 0)
  return x
}

function localYmdFromDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** Body for POST/PATCH ``/cases/{id}/events`` from the main calendar composer. */
function buildCaseEventApiPayload(d: {
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

function addDaysLocal(d: Date, n: number): Date {
  const x = new Date(d)
  x.setDate(x.getDate() + n)
  return x
}

/** `startMinute` is 0–59. `durMinutes` is 1–60 for duration. */
function buildTimedStartEnd(
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

function splitRemainderToHoursMinutes(totalMin: number): { durHours: number; durMinutes: number } {
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
function timedDurationFromRange(start: Date, end: Date): { durDays: number; durHours: number; durMinutes: number } {
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

function startHourMinuteFromDate(d: Date): { startHour: number; startMinute: number } {
  return { startHour: d.getHours(), startMinute: d.getMinutes() }
}

function toBodyDate(d: Date, allDay: boolean): string {
  if (allDay) {
    const y = d.getFullYear()
    const m = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    return `${y}-${m}-${day}`
  }
  return d.toISOString()
}

export function CalendarPage({
  token,
  me,
  onOpenSettings,
}: {
  token: string
  me?: UserPublic | null
  onOpenSettings: () => void
}) {
  const calRef = useRef<FullCalendar>(null)
  const calWrapRef = useRef<HTMLDivElement | null>(null)
  const calendarSelectionHydratedRef = useRef(false)
  const calendarsRef = useRef<UserCalendarListItem[]>([])
  const selectedCalIdsRef = useRef<string[]>([])
  const selectionKeyRef = useRef('')
  const prevSelectionKeyRef = useRef<string | null>(null)
  const fetchGenRef = useRef(0)
  const { prefs, setPreference } = useUserUiPreferences(me, token)
  const [calendarPixelHeight, setCalendarPixelHeight] = useState(480)
  const [needCaldav, setNeedCaldav] = useState(false)
  const [calendarsLoaded, setCalendarsLoaded] = useState(false)
  const [selectionReady, setSelectionReady] = useState(false)
  const [eventsLoading, setEventsLoading] = useState(true)
  const [caldavSyncing, setCaldavSyncing] = useState(false)
  const [banner, setBanner] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [confirmDeleteEventOpen, setConfirmDeleteEventOpen] = useState(false)

  const [calendars, setCalendars] = useState<UserCalendarListItem[]>([])
  const [selectedCalIds, setSelectedCalIds] = useState<string[]>([])
  const [showManage, setShowManage] = useState(false)
  const [eventCategories, setEventCategories] = useState<CalendarCategoryOut[]>([])
  const [caseEventsForCreate, setCaseEventsForCreate] = useState<CaseEventOut[]>([])

  const [draft, setDraft] = useState<
    | null
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
  >(null)

  const createEventCategory = draft?.kind === 'create' ? draft.eventCategory : null
  const createCaseId = draft?.kind === 'create' ? draft.caseId : ''
  const eventDropdown = useExclusiveDropdownOpen<CalendarEventDropdownKey>()

  const createEventCategoryOptions = useMemo(
    () => [
      { value: 'custom', label: 'Custom' },
      ...caseEventsForCreate.map((ev) => ({
        value: ev.id,
        label: `${ev.name}${ev.template_id ? '' : ' (custom line)'}`,
      })),
    ],
    [caseEventsForCreate],
  )

  const editEventCategoryOptions = useMemo(
    () => calendarLabelOptions(eventCategories),
    [eventCategories],
  )

  const createCalendarLabelOptions = useMemo(
    () => calendarLabelOptions(eventCategories),
    [eventCategories],
  )

  const createTargetCalendarOptions = useMemo(
    () => writableCalendarPickerOptions(calendars),
    [calendars],
  )

  const createTargetCalendarName = useMemo(() => {
    if (draft?.kind !== 'create') return null
    return calendars.find((c) => c.id === draft.targetCalendarId)?.name ?? null
  }, [calendars, draft])

  useEffect(() => {
    if (!draft) eventDropdown.closeAll()
  }, [draft, eventDropdown.closeAll])

  useEffect(() => {
    if (!createCaseId || !token) {
      setCaseEventsForCreate([])
      return
    }
    let cancel = false
    void apiFetch<{ events: CaseEventOut[] }>(`/cases/${createCaseId}/events`, { token })
      .then((out) => {
        if (!cancel) setCaseEventsForCreate(Array.isArray(out.events) ? out.events : [])
      })
      .catch(() => {
        if (!cancel) setCaseEventsForCreate([])
      })
    return () => {
      cancel = true
    }
  }, [createCaseId, token])

  /** When a case template row is chosen, mirror ``CaseEventCreateModal`` name + track defaults. */
  useEffect(() => {
    if (createEventCategory == null || createEventCategory === 'custom') return
    const row = caseEventsForCreate.find((e) => e.id === createEventCategory)
    if (!row) return
    setDraft((d) => {
      if (!d || d.kind !== 'create' || d.eventCategory !== createEventCategory) return d
      return { ...d, title: row.name, trackInCalendar: Boolean(row.track_in_calendar) }
    })
  }, [createEventCategory, caseEventsForCreate])

  const refresh = useCallback(() => {
    invalidateCalendarEventCache()
    calRef.current?.getApi().refetchEvents()
  }, [])

  const loadCalendars = useCallback(async () => {
    try {
      const rows = await apiFetch<UserCalendarListItem[]>('/users/me/calendars', { token })
      setCalendars(rows)
    } catch (e: unknown) {
      const err = e as ApiError
      if (err.status === 403) setNeedCaldav(true)
    } finally {
      setCalendarsLoaded(true)
    }
  }, [token])

  useEffect(() => {
    if (needCaldav) return
    void loadCalendars()
  }, [needCaldav, loadCalendars])

  useEffect(() => {
    if (!calendarsLoaded) {
      setSelectionReady(false)
      return
    }
    if (calendars.length === 0) {
      setSelectionReady(true)
      return
    }
    const valid = new Set(calendars.map((c) => c.id))
    const saved = prefs.calendar_selected_calendar_ids.filter((id) => valid.has(id))
    if (prefs.calendar_selected_calendar_ids.length > 0 && saved.length > 0) {
      setSelectedCalIds(saved)
    } else {
      setSelectedCalIds(calendars.map((c) => c.id))
    }
    calendarSelectionHydratedRef.current = true
    setSelectionReady(true)
  }, [calendars, prefs.calendar_selected_calendar_ids, calendarsLoaded])

  useEffect(() => {
    const api = calRef.current?.getApi()
    if (api && api.view.type !== prefs.calendar_view) {
      api.changeView(prefs.calendar_view)
    }
  }, [prefs.calendar_view])

  useLayoutEffect(() => {
    const el = calWrapRef.current
    if (!el) return
    const apply = () => {
      const h = el.getBoundingClientRect().height
      if (h > 0) setCalendarPixelHeight(Math.floor(h))
    }
    apply()
    const ro = new ResizeObserver(() => apply())
    ro.observe(el)
    return () => ro.disconnect()
  }, [needCaldav])

  const selectionKey = selectedCalIds.join(',')
  calendarsRef.current = calendars
  selectedCalIdsRef.current = selectedCalIds
  selectionKeyRef.current = selectionKey

  useEffect(() => {
    if (!selectionReady || needCaldav) return
    if (prevSelectionKeyRef.current === null) {
      prevSelectionKeyRef.current = selectionKey
      return
    }
    if (prevSelectionKeyRef.current === selectionKey) return
    prevSelectionKeyRef.current = selectionKey
    calRef.current?.getApi().refetchEvents()
  }, [selectionReady, needCaldav, selectionKey])

  useEffect(() => {
    if (!draft) {
      setEventCategories([])
      return
    }
    let calId = ''
    if (draft.kind === 'create') {
      calId = draft.targetCalendarId || defaultWritableCalendarId(calendars, selectedCalIds) || ''
    } else if (draft.kind === 'edit' && draft.editSource === 'caldav') {
      calId = draft.calendarId
    } else if (draft.kind === 'edit' && draft.editSource === 'case') {
      calId = draft.targetCalendarId || defaultWritableCalendarId(calendars, selectedCalIds) || ''
    } else {
      setEventCategories([])
      return
    }
    if (!calId) {
      setEventCategories([])
      return
    }
    let cancel = false
    void apiFetch<CalendarCategoryOut[]>(`/users/me/calendars/${calId}/categories`, { token })
      .then((rows) => {
        if (!cancel) setEventCategories(rows)
      })
      .catch(() => {
        if (!cancel) setEventCategories([])
      })
    return () => {
      cancel = true
    }
  }, [draft, calendars, selectedCalIds, token])

  /** Keep create draft on a writable calendar when calendars load or selection changes. */
  useEffect(() => {
    if (draft?.kind !== 'create') return
    const writableIds = new Set(writableCalendarPickerOptions(calendars).map((o) => o.value))
    if (writableIds.size === 0) return
    setDraft((d) => {
      if (!d || d.kind !== 'create') return d
      if (d.targetCalendarId && writableIds.has(d.targetCalendarId)) return d
      const nextId = defaultWritableCalendarId(calendars, selectedCalIds)
      if (!nextId || nextId === d.targetCalendarId) return d
      return { ...d, targetCalendarId: nextId, categoryId: null }
    })
  }, [draft?.kind, calendars, selectedCalIds])

  /** Load CalDAV category for a tracked case event being edited. */
  useEffect(() => {
    if (draft?.kind !== 'edit' || draft.editSource !== 'case' || !draft.calendarEventUid) return
    const uid = draft.calendarEventUid
    let cancel = false
    const winStart = new Date(draft.start)
    winStart.setDate(winStart.getDate() - 1)
    const winEnd = new Date(draft.end)
    winEnd.setDate(winEnd.getDate() + 1)
    const params = new URLSearchParams({
      start: winStart.toISOString(),
      end: winEnd.toISOString(),
    })
    void apiFetch<CalendarEventOut[]>(`/users/me/calendar/events?${params}`, { token })
      .then((rows) => {
        if (cancel) return
        const match = rows.find((r) => r.id === uid)
        if (!match?.category_id) return
        setDraft((d) => {
          if (d?.kind !== 'edit' || d.editSource !== 'case' || d.calendarEventUid !== uid) return d
          if (d.categoryId) return d
          return {
            ...d,
            categoryId: match.category_id ? String(match.category_id) : null,
            categoryLabel: match.category_name ?? null,
          }
        })
      })
      .catch(() => {
        /* ignore */
      })
    return () => {
      cancel = true
    }
  }, [
    draft?.kind,
    draft?.kind === 'edit' ? draft.editSource : null,
    draft?.kind === 'edit' ? draft.calendarEventUid : null,
    draft?.start,
    draft?.end,
    token,
  ])

  useEffect(() => {
    if (draft?.kind !== 'edit' || draft.editSource !== 'case' || !draft.caseId || !draft.caseEventId) return
    let cancel = false
    void apiFetch<{ events: CaseEventOut[] }>(`/cases/${draft.caseId}/events`, { token })
      .then((out) => {
        if (cancel) return
        const row = (out.events ?? []).find((e) => e.id === draft.caseEventId)
        if (!row) return
        setDraft((d) => {
          if (d?.kind !== 'edit' || d.editSource !== 'case' || d.caseEventId !== row.id) return d
          return {
            ...d,
            calendarEventUid: row.calendar_event_uid ?? null,
            emailAlert: Boolean(row.email_alert_enabled),
            trackInCalendar: Boolean(row.track_in_calendar),
          }
        })
      })
      .catch(() => {
        /* ignore */
      })
    return () => {
      cancel = true
    }
  }, [
    draft?.kind,
    draft?.kind === 'edit' ? draft.editSource : null,
    draft?.kind === 'edit' ? draft.caseId : null,
    draft?.kind === 'edit' ? draft.caseEventId : null,
    token,
  ])

  const transformEventFromApi = useCallback((event: EventInput): EventInput => {
    const ep = event.extendedProps as { api_all_day?: boolean } | undefined
    if (ep?.api_all_day !== true) return event
    const startY = eventInputToYmd(event.start)
    let endY = eventInputToYmd(event.end ?? event.start)
    if (!startY) return { ...event, allDay: true }
    if (!endY || endY <= startY) {
      endY = addOneCalendarDayYmd(startY)
    }
    return {
      ...event,
      allDay: true,
      start: startY,
      end: endY,
    }
  }, [])

  const onEventDidMount = useCallback((info: EventMountArg) => {
    const apiAll = info.event.extendedProps?.api_all_day === true
    const row = info.el.closest('tr.fc-list-event') as HTMLElement | null

    if (apiAll) {
      info.el.setAttribute('data-canary-allday', '1')
      info.el.querySelectorAll('.fc-event-time').forEach((node) => {
        ;(node as HTMLElement).style.setProperty('display', 'none', 'important')
      })
      if (row) {
        row.setAttribute('data-canary-allday', '1')
        row.querySelectorAll('td.fc-list-event-time').forEach((td) => {
          ;(td as HTMLElement).style.setProperty('display', 'none', 'important')
        })
      }
    }

    if (!row) return
    const bg = info.event.backgroundColor
    if (!bg) return
    const fg = info.event.textColor
    const chip = row.querySelector(
      'td.fc-list-event-title a, td.fc-list-event-title .canary-list-event-title',
    ) as HTMLElement | null
    if (chip) {
      chip.style.backgroundColor = bg
      if (fg) chip.style.color = fg
    }
  }, [])

  const noEventsContent = useMemo(() => calendarNoEventsContent(eventsLoading), [eventsLoading])

  const fetchEvents = useCallback(
    async (
      info: { startStr: string; endStr: string },
      successCallback: (events: EventInput[]) => void,
      failureCallback: (error: Error) => void,
    ) => {
      const gen = ++fetchGenRef.current
      setBanner(null)
      setNeedCaldav(false)

      const params = new URLSearchParams({ start: info.startStr, end: info.endStr })
      const cals = calendarsRef.current
      const sel = selectedCalIdsRef.current
      const selectionKey = selectionKeyRef.current
      if (cals.length > 0 && sel.length > 0 && sel.length < cals.length) {
        params.set('calendar_ids', sel.join(','))
      }

      const cacheKey = calendarEventCacheKey(info.startStr, info.endStr, selectionKey)
      const cached = readCalendarEventCache(cacheKey)
      let painted = false

      if (cached) {
        successCallback(mapCalendarEventsToFullCalendar(cached))
        painted = true
        setCaldavSyncing(true)
      }

      if (!cached) {
        try {
          const localParams = new URLSearchParams(params)
          localParams.set('include_caldav', 'false')
          const localRows = await apiFetch<CalendarEventOut[]>(`/users/me/calendar/events?${localParams}`, {
            token,
          })
          if (gen !== fetchGenRef.current) return
          if (localRows.length > 0) {
            successCallback(mapCalendarEventsToFullCalendar(localRows))
            painted = true
            setCaldavSyncing(true)
          }
        } catch {
          /* local-only feed is best-effort */
        }
      }

      try {
        const rows = await apiFetch<CalendarEventOut[]>(`/users/me/calendar/events?${params}`, { token })
        if (gen !== fetchGenRef.current) return
        writeCalendarEventCache(cacheKey, rows)
        successCallback(mapCalendarEventsToFullCalendar(rows))
        setCaldavSyncing(false)
      } catch (e: unknown) {
        if (gen !== fetchGenRef.current) return
        const err = e as ApiError
        if (err.status === 403) {
          setNeedCaldav(true)
          setCaldavSyncing(false)
          successCallback([])
          return
        }
        setCaldavSyncing(false)
        if (painted) {
          setBanner(err.message ?? 'Could not refresh personal calendar events from CalDAV')
          return
        }
        setBanner(err.message ?? 'Could not load events')
        failureCallback(err instanceof Error ? err : new Error(String(e)))
      }
    },
    [token],
  )

  function toggleCal(id: string) {
    setSelectedCalIds((prev) => {
      let next: string[]
      if (prev.includes(id)) {
        if (prev.length <= 1) return prev
        next = prev.filter((x) => x !== id)
      } else {
        next = [...prev, id]
      }
      if (calendarSelectionHydratedRef.current) {
        setPreference('calendar_selected_calendar_ids', next)
      }
      return next
    })
  }

  function onSelect(selectInfo: DateSelectArg) {
    if (needCaldav) return
    const start = selectInfo.start
    const end = selectInfo.end
    const allDaySel = Boolean(selectInfo.allDay)
    let durD = 0
    let durH = 1
    let durM = 30
    if (!allDaySel && start && end) {
      const dur = timedDurationFromRange(start, end)
      durD = dur.durDays
      durH = dur.durHours
      durM = dur.durMinutes
    }
    setDraft({
      kind: 'create',
      title: '',
      start,
      end,
      allDay: allDaySel,
      startHour: start.getHours(),
      startMinute: start.getMinutes(),
      durDays: allDaySel ? 0 : durD,
      durHours: allDaySel ? 0 : durH,
      durMinutes: allDaySel ? 30 : durM,
      caseId: '',
      eventCategory: 'custom',
      categoryId: null,
      targetCalendarId: defaultWritableCalendarId(calendars, selectedCalIds) || '',
      trackInCalendar: true,
      emailAlert: false,
    })
    selectInfo.view.calendar.unselect()
  }

  function openRibbonNewEventDraft() {
    setBanner(null)
    if (needCaldav) {
      setBanner('Turn on CalDAV in User settings to create events.')
      return
    }
    const start = new Date()
    start.setSeconds(0, 0)
    start.setMilliseconds(0)
    const mins = start.getMinutes()
    const rem = mins % 30
    if (rem !== 0) start.setMinutes(mins + (30 - rem))
    const end = new Date(start.getTime() + 90 * 60 * 1000)
    const dur = timedDurationFromRange(start, end)
    setDraft({
      kind: 'create',
      title: '',
      start,
      end,
      allDay: false,
      startHour: start.getHours(),
      startMinute: start.getMinutes(),
      durDays: dur.durDays,
      durHours: dur.durHours,
      durMinutes: dur.durMinutes,
      caseId: '',
      eventCategory: 'custom',
      categoryId: null,
      targetCalendarId: defaultWritableCalendarId(calendars, selectedCalIds) || '',
      trackInCalendar: true,
      emailAlert: false,
    })
    try {
      calRef.current?.getApi().unselect()
    } catch {
      /* ignore */
    }
  }

  function onEventClick(clickInfo: EventClickArg) {
    const ev = clickInfo.event
    const s = ev.start
    const e = ev.end
    if (!s) return
    const end = e ?? s
    const canEdit = ev.extendedProps.can_edit !== false
    const ep = ev.extendedProps as {
      category_id?: string | null
      category_name?: string | null
      calendar_id?: string | null
      case_id?: string | null
      case_event_id?: string | null
      track_in_calendar?: boolean | null
      email_alert_enabled?: boolean
      matter_template_id?: string | null
    }
    let startHour = 9
    let startMinute = 0
    let durDays = 0
    let durHours = 1
    let durMinutes = 30
    if (!ev.allDay) {
      const sm = startHourMinuteFromDate(s)
      startHour = sm.startHour
      startMinute = sm.startMinute
      const dur = timedDurationFromRange(s, end)
      durDays = dur.durDays
      durHours = dur.durHours
      durMinutes = dur.durMinutes
    }
    if (ep.case_id && ep.case_event_id) {
      setDraft({
        kind: 'edit',
        editSource: 'case',
        id: ev.id,
        title: ev.title || '(no title)',
        description: '',
        start: s,
        end,
        allDay: ev.allDay,
        startHour,
        startMinute,
        durDays,
        durHours,
        durMinutes,
        canEdit,
        calendarId: '',
        categoryId: ep.category_id ? String(ep.category_id) : null,
        categoryLabel: ep.category_name != null && ep.category_name !== '' ? String(ep.category_name) : null,
        targetCalendarId: defaultWritableCalendarId(calendars, selectedCalIds) || '',
        caseId: ep.case_id,
        caseEventId: ep.case_event_id,
        calendarEventUid: null,
        trackInCalendar: Boolean(ep.track_in_calendar),
        emailAlert: Boolean(ep.email_alert_enabled),
      })
      return
    }
    setDraft({
      kind: 'edit',
      editSource: 'caldav',
      id: ev.id,
      title: ev.title || '(no title)',
      description: String(ev.extendedProps.description ?? ''),
      start: s,
      end: end,
      allDay: ev.allDay,
      startHour,
      startMinute,
      durDays,
      durHours,
      durMinutes,
      canEdit,
      calendarId: String(ep.calendar_id ?? ''),
      categoryId: ep.category_id ? String(ep.category_id) : null,
      categoryLabel: ep.category_name != null && ep.category_name !== '' ? String(ep.category_name) : null,
      targetCalendarId: String(ep.calendar_id ?? ''),
      emailAlert: Boolean(ep.email_alert_enabled),
      matterTemplateId: ep.matter_template_id != null && ep.matter_template_id !== '' ? String(ep.matter_template_id) : null,
    })
  }

  const onEventChange = useCallback(
    async (changeInfo: EventChangeArg) => {
      if (changeInfo.event.extendedProps.case_event_id) {
        changeInfo.revert()
        return
      }
      if (changeInfo.event.extendedProps.can_edit === false) {
        changeInfo.revert()
        return
      }
      const ev = changeInfo.event
      const s = ev.start
      const e = ev.end
      if (!s) {
        changeInfo.revert()
        return
      }
      const endDt = e ?? s
      try {
        await apiFetch<CalendarEventOut>(`/users/me/calendar/events/${encodeURIComponent(ev.id)}`, {
          method: 'PATCH',
          token,
          json: {
            start: toBodyDate(s, ev.allDay),
            end: toBodyDate(endDt, ev.allDay),
            all_day: ev.allDay,
          },
        })
      } catch {
        changeInfo.revert()
        setBanner('Could not update event')
      }
    },
    [token],
  )

  async function saveCreate() {
    if (!draft || draft.kind !== 'create') return
    const title = draft.title.trim()
    if (!title) {
      setBanner('Please enter an event name.')
      return
    }
    const cid = draft.caseId.trim()
    setBusy(true)
    setBanner(null)
    try {
      if (!cid) {
        const times = buildCalDavTimesFromDraft(draft)
        const calId = draft.targetCalendarId || defaultWritableCalendarId(calendars, selectedCalIds)
        if (!calId) {
          setBanner('No writable calendar found. Create a calendar under Calendars… first.')
          return
        }
        await apiFetch<CalendarEventOut>(`/users/me/calendar/events`, {
          method: 'POST',
          token,
          json: {
            title,
            ...times,
            description: null,
            calendar_id: calId,
            category_id: draft.categoryId || null,
            email_alert: draft.emailAlert,
          },
        })
        setDraft(null)
        refresh()
        return
      }

      const payload = buildCaseEventApiPayload({
        title,
        start: draft.start,
        allDay: draft.allDay,
        startHour: draft.startHour,
        startMinute: draft.startMinute,
        trackInCalendar: draft.trackInCalendar,
        emailAlert: draft.emailAlert,
      })
      let saved: CaseEventOut
      if (draft.eventCategory === 'custom') {
        saved = await apiFetch<CaseEventOut>(`/cases/${cid}/events`, {
          method: 'POST',
          token,
          json: payload,
        })
      } else {
        saved = await apiFetch<CaseEventOut>(`/cases/${cid}/events/${encodeURIComponent(draft.eventCategory)}`, {
          method: 'PATCH',
          token,
          json: payload,
        })
      }
      if (draft.trackInCalendar) {
        const caseRow = await apiFetch<CaseOut>(`/cases/${cid}`, { token })
        await syncCaseEventToCalDav(token, cid, saved, {
          caseLabel: caseRow.case_number,
          categoryId: draft.categoryId,
          calendarId: draft.targetCalendarId || defaultWritableCalendarId(calendars, selectedCalIds),
        })
      }
      setDraft(null)
      refresh()
    } catch (e: unknown) {
      setBanner((e as ApiError).message ?? 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  async function saveEdit() {
    if (!draft || draft.kind !== 'edit' || !draft.canEdit) return
    const title = draft.title.trim()
    if (!title) {
      setBanner('Please enter an event name.')
      return
    }
    if (draft.editSource === 'case') {
      const cid = draft.caseId
      const eid = draft.caseEventId
      if (!cid || !eid) {
        setBanner('Missing matter or event reference.')
        return
      }
    }
    const allDay = draft.allDay
    setBusy(true)
    setBanner(null)
    try {
      if (draft.editSource === 'case') {
        const cid = draft.caseId!
        const eid = draft.caseEventId!
        const payload = buildCaseEventApiPayload({
          title,
          start: draft.start,
          allDay,
          startHour: draft.startHour,
          startMinute: draft.startMinute,
          trackInCalendar: Boolean(draft.trackInCalendar),
          emailAlert: draft.emailAlert,
        })
        const saved = await apiFetch<CaseEventOut>(`/cases/${cid}/events/${encodeURIComponent(eid)}`, {
          method: 'PATCH',
          token,
          json: payload,
        })
        if (draft.trackInCalendar) {
          const caseRow = await apiFetch<CaseOut>(`/cases/${cid}`, { token })
          await syncCaseEventToCalDav(token, cid, saved, {
            caseLabel: caseRow.case_number,
            categoryId: draft.categoryId,
            calendarId: draft.targetCalendarId || defaultWritableCalendarId(calendars, selectedCalIds),
          })
        }
      } else {
        let bodyStart: string
        let bodyEnd: string
        if (allDay) {
          bodyStart = toBodyDate(draft.start, true)
          bodyEnd = toBodyDate(draft.end, true)
        } else {
          const anchor = startOfLocalDay(draft.start)
          const { start, end } = buildTimedStartEnd(
            anchor,
            draft.startHour,
            draft.startMinute,
            draft.durDays,
            draft.durHours,
            draft.durMinutes,
          )
          bodyStart = toBodyDate(start, false)
          bodyEnd = toBodyDate(end, false)
        }
        await apiFetch<CalendarEventOut>(`/users/me/calendar/events/${encodeURIComponent(draft.id)}`, {
          method: 'PATCH',
          token,
          json: {
            title,
            description: draft.description.trim() || null,
            start: bodyStart,
            end: bodyEnd,
            all_day: allDay,
            category_id: draft.categoryId,
            email_alert: draft.emailAlert,
            matter_sub_type_event_template_id: draft.matterTemplateId ?? null,
          },
        })
      }
      setDraft(null)
      refresh()
    } catch (e: unknown) {
      setBanner((e as ApiError).message ?? 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  function requestDeleteEdit() {
    if (!draft || draft.kind !== 'edit' || !draft.canEdit || draft.editSource !== 'caldav') return
    setConfirmDeleteEventOpen(true)
  }

  async function performDeleteEditEvent() {
    if (!draft || draft.kind !== 'edit' || !draft.canEdit || draft.editSource !== 'caldav') return
    setConfirmDeleteEventOpen(false)
    setBusy(true)
    setBanner(null)
    try {
      await apiFetch(`/users/me/calendar/events/${encodeURIComponent(draft.id)}`, { method: 'DELETE', token })
      setDraft(null)
      refresh()
    } catch (e: unknown) {
      setBanner((e as ApiError).message ?? 'Delete failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="mainMenuShell mainMenuShell--surface"
      style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}
    >
      <div className="paneHead">
        <div>
          <h2 style={{ margin: 0 }}>Calendar</h2>
          <div className="muted" style={{ marginTop: 4 }}>
            In Canary you see your calendars plus any shared with you or subscribed from the directory. External CalDAV
            apps (Outlook, Apple Calendar, etc.) only sync calendars under your own login — not colleagues&apos; shared
            calendars.
          </div>
        </div>
        <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <button
            type="button"
            className="btn"
            disabled={needCaldav}
            onClick={() => void openRibbonNewEventDraft()}
          >
            New event
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => {
              void loadCalendars().then(() => refresh())
            }}
            disabled={needCaldav}
          >
            Refresh
          </button>
          <button type="button" className="btn" onClick={() => setShowManage(true)} disabled={needCaldav}>
            Calendars…
          </button>
        </div>
      </div>
      {needCaldav ? (
        <div className="card" style={{ marginTop: 12, padding: 16 }}>
          <p style={{ margin: 0 }}>Turn on CalDAV in User settings to use this calendar.</p>
          <button type="button" className="btn primary" style={{ marginTop: 12 }} onClick={onOpenSettings}>
            Open User settings
          </button>
        </div>
      ) : null}
      {banner ? <div className="error" style={{ marginTop: 12 }}>{banner}</div> : null}
      {caldavSyncing && !needCaldav ? (
        <div className="muted" style={{ marginTop: 8, fontSize: 13 }}>
          Syncing personal calendar events…
        </div>
      ) : null}
      {!needCaldav && calendars.length > 0 ? (
        <div className="card" style={{ marginTop: 12, padding: 12 }}>
          <div className="muted" style={{ marginBottom: 8, fontSize: 13 }}>
            Show calendars (at least one):
          </div>
          <div className="row" style={{ gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
            {calendars.map((c) => (
              <label key={c.id} className="row" style={{ gap: 6, alignItems: 'center', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={selectedCalIds.includes(c.id)}
                  onChange={() => toggleCal(c.id)}
                />
                <span>
                  {c.name}
                  {c.source !== 'owned' ? (
                    <span className="muted" style={{ fontSize: 12 }}>
                      {' '}
                      — {c.owner.display_name}
                      {c.access === 'read' ? ' (read-only)' : ''}
                    </span>
                  ) : null}
                </span>
              </label>
            ))}
          </div>
        </div>
      ) : null}
      <div
        className="card canaryCalendar"
        style={{
          marginTop: 12,
          padding: 12,
          flex: 1,
          minHeight: 0,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        <div ref={calWrapRef} className="canaryCalendarInner">
          {!calendarsLoaded && !needCaldav ? (
            <div className="muted" style={{ padding: 24, textAlign: 'center' }}>
              Loading calendars…
            </div>
          ) : null}
          {selectionReady && !needCaldav ? (
          <FullCalendar
          ref={calRef}
          plugins={[dayGridPlugin, timeGridPlugin, listPlugin, interactionPlugin]}
          initialView={prefs.calendar_view}
          views={{
            listYear: CALENDAR_LIST_YEAR_VIEW,
          }}
          headerToolbar={{
            left: 'prev,next today',
            center: 'title',
            right: 'dayGridMonth,timeGridWeek,timeGridDay,listYear',
          }}
          datesSet={(arg) => {
            const viewType = arg.view.type as CalendarView
            if (viewType !== prefs.calendar_view) setPreference('calendar_view', viewType)
          }}
          height={calendarPixelHeight}
          editable={!needCaldav}
          selectable={!needCaldav}
          selectMirror
          dayMaxEvents
          weekends
          events={fetchEvents}
          loading={setEventsLoading}
          noEventsText="No events in this range"
          noEventsContent={noEventsContent}
          eventDataTransform={needCaldav ? undefined : transformEventFromApi}
          eventContent={needCaldav ? undefined : calendarListEventContent}
          eventDidMount={needCaldav ? undefined : onEventDidMount}
          select={needCaldav ? undefined : onSelect}
          eventClick={needCaldav ? undefined : onEventClick}
          eventDrop={needCaldav ? undefined : onEventChange}
          eventResize={needCaldav ? undefined : onEventChange}
          nowIndicator
          eventTimeFormat={{ hour: '2-digit', minute: '2-digit', hour12: false }}
        />
          ) : null}
        </div>
      </div>

      {showManage ? (
        <CalendarManageModal
          token={token}
          calendars={calendars}
          onClose={() => setShowManage(false)}
          onChanged={() => {
            void loadCalendars().then(() => refresh())
          }}
        />
      ) : null}

      {draft ? (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15,23,42,0.35)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 20,
            padding: 16,
          }}
          onClick={() => !busy && setDraft(null)}
          onKeyDown={(e) => e.key === 'Escape' && !busy && setDraft(null)}
          role="presentation"
        >
          <div
            className="card"
            style={{
              maxWidth:
                draft.kind === 'create' || (draft.kind === 'edit' && draft.canEdit) ? 480 : 440,
              width: '100%',
              minWidth: 0,
              padding: 20,
              boxSizing: 'border-box',
            }}
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => e.stopPropagation()}
            role="presentation"
          >
            <h3 style={{ marginTop: 0 }}>{draft.kind === 'create' ? 'New event' : 'Edit event'}</h3>
            <div className="stack" style={{ gap: 12, minWidth: 0 }}>
              {draft.kind === 'create' ? (
                createTargetCalendarOptions.length > 0 ? (
                  <SingleSelectDropdown
                    label="Calendar"
                    options={createTargetCalendarOptions}
                    value={draft.targetCalendarId}
                    disabled={busy || createTargetCalendarOptions.length === 0}
                    open={eventDropdown.isOpen('createCal')}
                    onOpenChange={(next) => eventDropdown.setOpen('createCal', next)}
                    onChange={(v) =>
                      setDraft({
                        ...draft,
                        targetCalendarId: v,
                        categoryId: null,
                      })
                    }
                  />
                ) : (
                  <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                    No writable calendar found. Create one under Calendars… first.
                  </p>
                )
              ) : null}
              {draft.kind === 'create' ? (
                <div className="field" style={{ minWidth: 0 }}>
                  <span>Matter (optional)</span>
                  <MatterSearchPicker
                    token={token}
                    value={draft.caseId}
                    disabled={busy}
                    onChange={(caseId) => {
                      setDraft({
                        ...draft,
                        caseId,
                        eventCategory: 'custom',
                        title: '',
                        trackInCalendar: true,
                        emailAlert: false,
                      })
                    }}
                  />
                  <p className="muted" style={{ margin: '6px 0 0', fontSize: 13, lineHeight: 1.4 }}>
                    Leave blank for a personal calendar event (not linked to a matter).
                  </p>
                </div>
              ) : null}
              {draft.kind === 'create' || (draft.kind === 'edit' && draft.canEdit) ? (
                <SingleSelectDropdown
                  label="Calendar label"
                  options={draft.kind === 'create' ? createCalendarLabelOptions : editEventCategoryOptions}
                  value={draft.categoryId ?? ''}
                  disabled={busy || eventCategories.length === 0}
                  open={eventDropdown.isOpen(draft.kind === 'create' ? 'createCalLabel' : 'editCalLabel')}
                  onOpenChange={(next) =>
                    eventDropdown.setOpen(draft.kind === 'create' ? 'createCalLabel' : 'editCalLabel', next)
                  }
                  onChange={(v) =>
                    setDraft({
                      ...draft,
                      categoryId: v || null,
                    })
                  }
                />
              ) : null}
              {draft.kind === 'create' && draft.caseId ? (
                <SingleSelectDropdown
                  label="Matter event type"
                  options={createEventCategoryOptions}
                  value={draft.eventCategory}
                  disabled={busy}
                  open={eventDropdown.isOpen('createMatterType')}
                  onOpenChange={(next) => eventDropdown.setOpen('createMatterType', next)}
                  onChange={(v) => {
                    if (v === 'custom') {
                      setDraft({ ...draft, eventCategory: 'custom', title: '', trackInCalendar: true, emailAlert: false })
                    } else {
                      setDraft({ ...draft, eventCategory: v })
                    }
                  }}
                />
              ) : null}
              {draft.kind === 'edit' && !draft.canEdit ? (
                <p className="muted">You can view this event but not edit it (read-only share or subscription).</p>
              ) : null}
              <label className="field">
                <span>{draft.kind === 'create' && !draft.caseId ? 'Title' : draft.kind === 'create' ? 'Name' : 'Title'}</span>
                <input
                  value={draft.title}
                  onChange={(e) =>
                    setDraft(
                      draft.kind === 'create'
                        ? { ...draft, title: e.target.value }
                        : { ...draft, title: e.target.value },
                    )
                  }
                  disabled={busy || (draft.kind === 'edit' && !draft.canEdit)}
                  placeholder={draft.kind === 'create' ? (draft.caseId ? 'Event name…' : 'Event title…') : undefined}
                  autoFocus={draft.kind === 'create' || (draft.kind === 'edit' && draft.canEdit)}
                />
              </label>
              {draft.kind === 'create' && draft.caseId ? (
                <label className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
                  <input
                    type="checkbox"
                    checked={draft.trackInCalendar}
                    disabled={busy}
                    onChange={(e) => setDraft({ ...draft, trackInCalendar: e.target.checked })}
                  />
                  <span className="muted" style={{ lineHeight: 1.4 }}>
                    Track in calendar — shows on this calendar and creates a fee-earner task when appropriate.
                  </span>
                </label>
              ) : null}
              {draft.kind === 'create' ? (
                <label className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
                  <input
                    type="checkbox"
                    checked={draft.emailAlert}
                    disabled={busy}
                    onChange={(e) => setDraft({ ...draft, emailAlert: e.target.checked })}
                  />
                  <span className="muted" style={{ lineHeight: 1.4 }}>
                    E-mail reminders for this event (requires Admin → E-mail → SMTP). Other users can opt in separately.
                  </span>
                </label>
              ) : null}
              {draft.kind === 'edit' && draft.editSource === 'case' && draft.canEdit ? (
                <label className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
                  <input
                    type="checkbox"
                    checked={Boolean(draft.trackInCalendar)}
                    disabled={busy}
                    onChange={(e) => setDraft({ ...draft, trackInCalendar: e.target.checked })}
                  />
                  <span className="muted" style={{ lineHeight: 1.4 }}>
                    Track in calendar — shows on this calendar and creates a fee-earner task when appropriate.
                  </span>
                </label>
              ) : null}
              {draft.kind === 'edit' && draft.editSource === 'case' && draft.canEdit ? (
                <label className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
                  <input
                    type="checkbox"
                    checked={draft.emailAlert}
                    disabled={busy}
                    onChange={(e) => setDraft({ ...draft, emailAlert: e.target.checked })}
                  />
                  <span className="muted" style={{ lineHeight: 1.4 }}>
                    E-mail reminders for this event (requires Admin → E-mail → SMTP). Other users can opt in separately.
                  </span>
                </label>
              ) : null}
              {draft.kind === 'edit' && draft.editSource === 'caldav' ? (
                <label className="field">
                  <span>Description</span>
                  <textarea
                    rows={3}
                    value={draft.description}
                    onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                    disabled={busy || !draft.canEdit}
                  />
                </label>
              ) : null}
              {draft.kind === 'edit' && draft.editSource === 'caldav' && draft.canEdit ? (
                <label className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
                  <input
                    type="checkbox"
                    checked={draft.emailAlert}
                    disabled={busy}
                    onChange={(e) => setDraft({ ...draft, emailAlert: e.target.checked })}
                  />
                  <span className="muted" style={{ lineHeight: 1.4 }}>
                    E-mail reminders for this event (requires Admin → E-mail → SMTP). Other users can opt in separately.
                  </span>
                </label>
              ) : null}
              {draft.kind === 'create' || (draft.kind === 'edit' && draft.canEdit) ? (
                <>
                  <label className="field">
                    <span>Date</span>
                    <input
                      type="date"
                      disabled={busy}
                      value={localYmdFromDate(startOfLocalDay(draft.start))}
                      onChange={(e) => {
                        const v = e.target.value
                        if (!v) return
                        const [yy, mm, dd] = v.split('-').map(Number)
                        const anchor = startOfLocalDay(draft.start)
                        anchor.setFullYear(yy, mm - 1, dd)
                        if (draft.allDay) {
                          const en = addDaysLocal(anchor, 1)
                          setDraft({ ...draft, start: anchor, end: en })
                        } else {
                          const { start, end } = buildTimedStartEnd(
                            anchor,
                            draft.startHour,
                            draft.startMinute,
                            draft.durDays,
                            draft.durHours,
                            draft.durMinutes,
                          )
                          setDraft({ ...draft, start, end })
                        }
                      }}
                    />
                  </label>
                  {!draft.allDay ? (
                    <>
                      <div className="field" style={{ marginBottom: 0 }}>
                        <span>Start</span>
                        <div className="row" style={{ gap: 8, marginTop: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                          <SingleSelectDropdown
                            hideLabel
                            label="Start hour"
                            options={HOUR_SELECT_OPTIONS}
                            value={String(draft.startHour)}
                            disabled={busy}
                            open={eventDropdown.isOpen('startH')}
                            onOpenChange={(next) => eventDropdown.setOpen('startH', next)}
                            onChange={(v) =>
                              setDraft({ ...draft, startHour: Number.parseInt(v, 10) })
                            }
                          />
                          <span className="muted">:</span>
                          <SingleSelectDropdown
                            hideLabel
                            label="Start minute"
                            options={START_MIN_SELECT_OPTIONS}
                            value={String(draft.startMinute)}
                            disabled={busy}
                            open={eventDropdown.isOpen('startM')}
                            onOpenChange={(next) => eventDropdown.setOpen('startM', next)}
                            onChange={(v) =>
                              setDraft({ ...draft, startMinute: Number.parseInt(v, 10) })
                            }
                          />
                        </div>
                      </div>
                      <div className="field" style={{ marginBottom: 0 }}>
                        <span>Duration</span>
                        <div className="row" style={{ gap: 8, marginTop: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                          <SingleSelectDropdown
                            hideLabel
                            label="Duration days"
                            options={DUR_DAY_SELECT_OPTIONS}
                            value={String(draft.durDays)}
                            disabled={busy}
                            open={eventDropdown.isOpen('durD')}
                            onOpenChange={(next) => eventDropdown.setOpen('durD', next)}
                            onChange={(v) =>
                              setDraft({ ...draft, durDays: Number.parseInt(v, 10) })
                            }
                          />
                          <span className="muted">d</span>
                          <SingleSelectDropdown
                            hideLabel
                            label="Duration hours"
                            options={DUR_HOUR_SELECT_OPTIONS}
                            value={String(draft.durHours)}
                            disabled={busy}
                            open={eventDropdown.isOpen('durH')}
                            onOpenChange={(next) => eventDropdown.setOpen('durH', next)}
                            onChange={(v) =>
                              setDraft({ ...draft, durHours: Number.parseInt(v, 10) })
                            }
                          />
                          <span className="muted">h</span>
                          <SingleSelectDropdown
                            hideLabel
                            label="Duration minutes"
                            options={DUR_MIN_SELECT_OPTIONS}
                            value={String(draft.durMinutes)}
                            disabled={busy}
                            open={eventDropdown.isOpen('durM')}
                            onOpenChange={(next) => eventDropdown.setOpen('durM', next)}
                            onChange={(v) =>
                              setDraft({ ...draft, durMinutes: Number.parseInt(v, 10) })
                            }
                          />
                          <span className="muted">m</span>
                        </div>
                      </div>
                    </>
                  ) : null}
                  <label className="row" style={{ gap: 8, alignItems: 'center', cursor: 'pointer', marginTop: 4 }}>
                    <input
                      type="checkbox"
                      checked={draft.allDay}
                      disabled={busy}
                      onChange={(e) => {
                        const checked = e.target.checked
                        if (checked) {
                          const s = startOfLocalDay(draft.start)
                          const en = addDaysLocal(s, 1)
                          setDraft({ ...draft, allDay: true, start: s, end: en })
                        } else {
                          const { start, end } = buildTimedStartEnd(
                            startOfLocalDay(draft.start),
                            draft.startHour,
                            draft.startMinute,
                            draft.durDays,
                            draft.durHours,
                            draft.durMinutes,
                          )
                          setDraft({ ...draft, allDay: false, start, end })
                        }
                      }}
                    />
                    <span>All day</span>
                  </label>
                </>
              ) : null}
              {draft.kind === 'edit' && !draft.canEdit ? (
                <div className="muted" style={{ fontSize: 13 }}>
                  Category (Canary): {draft.categoryLabel ?? '—'}
                </div>
              ) : null}
              <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                {draft.kind === 'create'
                  ? !draft.caseId
                    ? draft.allDay
                      ? `Saved as an all-day event on ${createTargetCalendarName ?? 'your calendar'}.`
                      : `Saved as a personal event on ${createTargetCalendarName ?? 'your calendar'} with the start time and duration above.`
                    : draft.allDay
                      ? `Saved as an all-day matter event on ${createTargetCalendarName ?? 'your calendar'} — you can edit it from this calendar or the matter.`
                      : `Saved as a matter event on ${createTargetCalendarName ?? 'your calendar'} with the start time and duration above — you can edit it from this calendar or the matter.`
                  : draft.kind === 'edit' && draft.canEdit && draft.editSource === 'caldav'
                    ? draft.allDay
                      ? 'All-day — drag the event on the calendar to change the date, or adjust options above.'
                      : 'Start time and duration are set above; you can also drag or resize the event on the calendar.'
                    : draft.kind === 'edit' && draft.canEdit && draft.editSource === 'case'
                      ? draft.allDay
                        ? 'All-day matter event — change the date and options above (not draggable on the grid).'
                        : 'Timed matter event — adjust start and duration above (not draggable on the grid).'
                    : draft.kind === 'edit' && !draft.canEdit
                      ? draft.editSource === 'case'
                        ? 'Read-only matter event — open the matter to change it if you have access.'
                        : draft.allDay
                          ? 'All-day event — drag on the grid to reschedule when you can edit.'
                          : 'Timed event — drag on the grid to reschedule when you can edit.'
                      : null}
              </p>
            </div>
            <div className="row" style={{ gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
              {draft.kind === 'edit' && draft.canEdit ? (
                <button type="button" className="btn primary" disabled={busy} onClick={() => void saveEdit()}>
                  Save
                </button>
              ) : null}
              {draft.kind === 'create' ? (
                <button
                  type="button"
                  className="btn primary"
                  disabled={
                    busy ||
                    !draft.title.trim() ||
                    !draft.targetCalendarId ||
                    createTargetCalendarOptions.length === 0
                  }
                  onClick={() => void saveCreate()}
                >
                  Save
                </button>
              ) : null}
              <button type="button" className="btn" disabled={busy} onClick={() => setDraft(null)}>
                Close
              </button>
              {draft.kind === 'edit' && draft.canEdit && draft.editSource === 'caldav' ? (
                <button
                  type="button"
                  className="btn"
                  disabled={busy}
                  onClick={() => requestDeleteEdit()}
                  style={{ marginLeft: 'auto', color: 'var(--danger)' }}
                >
                  Delete
                </button>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

      <ConfirmModal
        open={confirmDeleteEventOpen}
        title="Delete event?"
        message="Delete this calendar event? This cannot be undone."
        confirmLabel="Delete"
        cancelLabel="Cancel"
        danger
        busy={busy}
        onConfirm={() => void performDeleteEditEvent()}
        onCancel={() => setConfirmDeleteEventOpen(false)}
      />
    </div>
  )
}

function CalendarManageModal({
  token,
  calendars,
  onClose,
  onChanged,
}: {
  token: string
  calendars: UserCalendarListItem[]
  onClose: () => void
  onChanged: () => void
}) {
  const { askConfirm } = useDialogs()
  const [newName, setNewName] = useState('')
  const [dirQ, setDirQ] = useState('')
  const [dirRows, setDirRows] = useState<CalendarDirectoryRow[] | null>(null)
  const [dirBusy, setDirBusy] = useState(false)
  const [users, setUsers] = useState<UserSummary[]>([])
  const [shares, setShares] = useState<CalendarShareOut[]>([])
  const [pickGrantee, setPickGrantee] = useState('')
  const [pickCanWrite, setPickCanWrite] = useState(false)
  const [granteeDropdownOpen, setGranteeDropdownOpen] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [editCalId, setEditCalId] = useState<string | null>(null)
  const [editCategoryRows, setEditCategoryRows] = useState<CalendarCategoryOut[]>([])

  const owned = useMemo(() => calendars.filter((c) => c.access === 'owner'), [calendars])

  const granteeOptions = useMemo(
    () =>
      users.map((u) => ({
        value: u.id,
        label: `${u.display_name} (${u.email})`,
      })),
    [users],
  )

  const editingCal = useMemo(
    () => (editCalId ? calendars.find((c) => c.id === editCalId) : undefined),
    [calendars, editCalId],
  )

  const loadEditCategories = useCallback(async () => {
    if (!editCalId) {
      setEditCategoryRows([])
      return
    }
    try {
      const rows = await apiFetch<CalendarCategoryOut[]>(`/users/me/calendars/${editCalId}/categories`, { token })
      setEditCategoryRows(rows)
    } catch {
      setEditCategoryRows([])
    }
  }, [editCalId, token])

  useEffect(() => {
    void loadEditCategories()
  }, [loadEditCategories])

  useEffect(() => {
    if (editCalId && !calendars.some((c) => c.id === editCalId)) {
      setEditCalId(null)
    }
  }, [calendars, editCalId])

  useEffect(() => {
    void apiFetch<UserSummary[]>('/users', { token })
      .then(setUsers)
      .catch(() => setUsers([]))
  }, [token])

  async function searchDir() {
    const q = dirQ.trim()
    if (q.length < 1) return
    setDirBusy(true)
    setErr(null)
    try {
      const rows = await apiFetch<CalendarDirectoryRow[]>(
        `/users/me/calendars/directory?q=${encodeURIComponent(q)}`,
        { token },
      )
      setDirRows(rows)
    } catch (e: unknown) {
      setErr((e as ApiError).message ?? 'Search failed')
    } finally {
      setDirBusy(false)
    }
  }

  async function createCal() {
    const name = newName.trim()
    if (name.length < 1) return
    setBusy(true)
    setErr(null)
    try {
      await apiFetch('/users/me/calendars', { method: 'POST', token, json: { name } })
      setNewName('')
      onChanged()
    } catch (e: unknown) {
      setErr((e as ApiError).message ?? 'Create failed')
    } finally {
      setBusy(false)
    }
  }

  async function loadSharesForEdit(calId: string) {
    try {
      const rows = await apiFetch<CalendarShareOut[]>(`/users/me/calendars/${calId}/shares`, { token })
      setShares(rows)
    } catch {
      setShares([])
    }
  }

  function openCalendarEdit(calId: string) {
    setErr(null)
    setEditCalId(calId)
    void loadSharesForEdit(calId)
  }

  async function togglePublic(calId: string, cur: boolean) {
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/users/me/calendars/${calId}`, { method: 'PATCH', token, json: { is_public: !cur } })
      onChanged()
    } catch (e: unknown) {
      setErr((e as ApiError).message ?? 'Update failed')
    } finally {
      setBusy(false)
    }
  }

  async function addShare(calId: string) {
    const id = pickGrantee
    if (!id) return
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/users/me/calendars/${calId}/shares`, {
        method: 'POST',
        token,
        json: { grantee_user_id: id, can_write: pickCanWrite },
      })
      setPickGrantee('')
      setPickCanWrite(false)
      await loadSharesForEdit(calId)
      onChanged()
    } catch (e: unknown) {
      setErr((e as ApiError).message ?? 'Share failed')
    } finally {
      setBusy(false)
    }
  }

  async function removeShare(calId: string, granteeId: string) {
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/users/me/calendars/${calId}/shares/${granteeId}`, { method: 'DELETE', token })
      await loadSharesForEdit(calId)
      onChanged()
    } catch (e: unknown) {
      setErr((e as ApiError).message ?? 'Remove share failed')
    } finally {
      setBusy(false)
    }
  }

  async function subscribe(calId: string) {
    setBusy(true)
    setErr(null)
    try {
      await apiFetch('/users/me/calendars/subscribe', { method: 'POST', token, json: { calendar_id: calId } })
      onChanged()
      setDirRows(null)
    } catch (e: unknown) {
      setErr((e as ApiError).message ?? 'Subscribe failed')
    } finally {
      setBusy(false)
    }
  }

  async function unsubscribe(calId: string) {
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/users/me/calendars/${calId}/subscription`, { method: 'DELETE', token })
      onChanged()
    } catch (e: unknown) {
      setErr((e as ApiError).message ?? 'Unsubscribe failed')
    } finally {
      setBusy(false)
    }
  }

  async function deleteOwnedCalendar(calId: string, name: string) {
    const ok = await askConfirm({
      title: 'Delete calendar',
      message: `Delete calendar “${name}”? All events in this calendar will be removed from the server. Shares and Canary categories for it will be removed. This cannot be undone.`,
      danger: true,
      confirmLabel: 'Delete',
    })
    if (!ok) return
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/users/me/calendars/${calId}`, { method: 'DELETE', token })
      setEditCalId((prev) => (prev === calId ? null : prev))
      onChanged()
    } catch (e: unknown) {
      setErr((e as ApiError).message ?? 'Delete failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(15,23,42,0.35)',
        zIndex: 30,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
      }}
      onClick={onClose}
      onKeyDown={(e) => e.key === 'Escape' && (editCalId ? setEditCalId(null) : onClose())}
      role="presentation"
    >
      <div
        className="card"
        style={{ maxWidth: 560, width: '100%', maxHeight: '90vh', overflow: 'auto', padding: 20 }}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.stopPropagation()}
        role="presentation"
      >
        {err ? <div className="error" style={{ marginBottom: 12 }}>{err}</div> : null}

        {editCalId && editingCal && editingCal.access === 'owner' ? (
          <>
            <div className="row" style={{ marginBottom: 16, gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <button type="button" className="btn" disabled={busy} onClick={() => setEditCalId(null)}>
                ← Back
              </button>
            </div>
            <h3 style={{ marginTop: 0 }}>{editingCal.name}</h3>
            <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
              Change who can see this calendar, whether it appears in the public directory, and Canary-only event
              categories (not synced to external CalDAV).
            </p>

            <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
              <span className="muted" style={{ fontSize: 13 }}>
                Public directory
              </span>
              <label className="row" style={{ gap: 8, alignItems: 'center' }}>
                <input
                  type="checkbox"
                  checked={editingCal.is_public}
                  disabled={busy}
                  onChange={() => void togglePublic(editingCal.id, editingCal.is_public)}
                />
              </label>
            </div>

            <h4 style={{ margin: '0 0 8px' }}>Access</h4>
            <div className="muted" style={{ fontSize: 13, marginBottom: 8 }}>
              Other Canary users you add here see this calendar in the app (merged by the server). It does not appear in
              their external CalDAV client — only calendars on their own account sync there.
            </div>
            <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 8 }}>
              <div style={{ flex: '1 1 220px', minWidth: 0 }}>
                <SingleSelectDropdown
                  label="User"
                  placeholder="Select user…"
                  options={granteeOptions}
                  value={pickGrantee}
                  disabled={busy}
                  open={granteeDropdownOpen}
                  onOpenChange={setGranteeDropdownOpen}
                  onChange={setPickGrantee}
                />
              </div>
              <label className="row" style={{ gap: 6, alignItems: 'center' }}>
                <input type="checkbox" checked={pickCanWrite} onChange={(e) => setPickCanWrite(e.target.checked)} />
                <span className="muted" style={{ fontSize: 13 }}>Can edit</span>
              </label>
              <button
                type="button"
                className="btn primary"
                disabled={busy || !pickGrantee}
                onClick={() => void addShare(editingCal.id)}
              >
                Add
              </button>
            </div>
            <ul style={{ margin: '0 0 20px', paddingLeft: 18 }}>
              {shares.map((s) => (
                <li key={s.grantee_user_id} style={{ marginBottom: 4 }}>
                  {s.grantee_display_name} ({s.grantee_email}) — {s.can_write ? 'edit' : 'view'}
                  <button
                    type="button"
                    className="btn"
                    style={{ marginLeft: 8, padding: '2px 8px', fontSize: 12 }}
                    disabled={busy}
                    onClick={() => void removeShare(editingCal.id, s.grantee_user_id)}
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>

            <h4 style={{ margin: '0 0 8px' }}>Event categories (Canary only)</h4>
            <p className="muted" style={{ marginTop: 0, fontSize: 13, marginBottom: 8 }}>
              Labels and colours for the in-app calendar. Everyone who can see this calendar can view its categories.
            </p>
            <CalendarCategoriesPanel
              token={token}
              calendar={editingCal}
              rows={editCategoryRows}
              isOwner
              busy={busy}
              setBusy={setBusy}
              setErr={setErr}
              onRefresh={() => void loadEditCategories()}
              embedded
            />

            <div style={{ marginTop: 20, display: 'flex', justifyContent: 'flex-end' }}>
              <button type="button" className="btn" onClick={() => setEditCalId(null)}>
                Done
              </button>
            </div>
          </>
        ) : (
          <>
        <h3 style={{ marginTop: 0 }}>Calendars</h3>
        <section style={{ marginBottom: 20 }}>
          <h4 style={{ margin: '0 0 8px' }}>New calendar</h4>
          <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
            <input
              placeholder="Name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              style={{ flex: '1 1 200px' }}
            />
            <button type="button" className="btn primary" disabled={busy} onClick={() => void createCal()}>
              Create
            </button>
          </div>
        </section>

        <section style={{ marginBottom: 20 }}>
          <h4 style={{ margin: '0 0 8px' }}>Find calendar by name</h4>
          <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
            Lists public calendars and calendars already shared with you. Subscribe to add a public calendar to your list.
          </p>
          <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
            <SearchInput
              placeholder="Search…"
              value={dirQ}
              onChange={(e) => setDirQ(e.target.value)}
              onClear={() => setDirQ('')}
              style={{ flex: '1 1 200px' }}
              aria-label="Search calendars"
            />
            <button type="button" className="btn" disabled={dirBusy} onClick={() => void searchDir()}>
              Search
            </button>
          </div>
          {dirRows ? (
            <div className="stack" style={{ marginTop: 12, gap: 8 }}>
              {dirRows.length === 0 ? (
                <div className="muted">No matches.</div>
              ) : (
                dirRows.map((r) => (
                  <div
                    key={r.id}
                    className="row"
                    style={{
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      padding: '8px 10px',
                      border: '1px solid var(--border)',
                      borderRadius: 8,
                      flexWrap: 'wrap',
                      gap: 8,
                    }}
                  >
                    <div>
                      <strong>{r.name}</strong>
                      <div className="muted" style={{ fontSize: 12 }}>
                        {r.owner.display_name} — {r.is_public ? 'public' : 'shared with you'}
                        {r.shared_directly ? ' — already shared' : ''}
                      </div>
                    </div>
                    {r.can_subscribe ? (
                      <button type="button" className="btn primary" disabled={busy} onClick={() => void subscribe(r.id)}>
                        Subscribe
                      </button>
                    ) : (
                      <span className="muted" style={{ fontSize: 13 }}>
                        {r.already_in_my_list ? 'In your list' : '—'}
                      </span>
                    )}
                  </div>
                ))
              )}
            </div>
          ) : null}
        </section>

        <section>
          <h4 style={{ margin: '0 0 8px' }}>Your calendars</h4>
          {owned.map((c) => (
            <div key={c.id} style={{ marginBottom: 16, padding: 12, border: '1px solid var(--border)', borderRadius: 8 }}>
              <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
                <strong>{c.name}</strong>
              </div>
              <div className="row" style={{ marginTop: 8, gap: 8, flexWrap: 'wrap' }}>
                <button type="button" className="btn primary" disabled={busy} onClick={() => openCalendarEdit(c.id)}>
                  Edit
                </button>
                <button
                  type="button"
                  className="btn"
                  disabled={busy}
                  onClick={() => void deleteOwnedCalendar(c.id, c.name)}
                  style={{ color: 'var(--danger)' }}
                >
                  Delete calendar…
                </button>
              </div>
            </div>
          ))}
        </section>

        <section style={{ marginTop: 20 }}>
          <h4 style={{ margin: '0 0 8px' }}>Subscriptions</h4>
          {calendars.filter((c) => c.source === 'subscription').map((c) => (
            <div key={c.id} className="row" style={{ justifyContent: 'space-between', marginBottom: 8, flexWrap: 'wrap', gap: 8 }}>
              <span>
                {c.name} <span className="muted">— {c.owner.display_name}</span>
              </span>
              <button type="button" className="btn" disabled={busy} onClick={() => void unsubscribe(c.id)}>
                Unsubscribe
              </button>
            </div>
          ))}
          {calendars.every((c) => c.source !== 'subscription') ? (
            <div className="muted" style={{ fontSize: 13 }}>No subscriptions yet.</div>
          ) : null}
        </section>

        <div style={{ marginTop: 20, display: 'flex', justifyContent: 'flex-end' }}>
          <button type="button" className="btn" onClick={onClose}>
            Done
          </button>
        </div>
          </>
        )}
      </div>
    </div>
  )
}
