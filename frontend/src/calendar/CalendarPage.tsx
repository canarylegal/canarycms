import type {
  DateSelectArg,
  EventChangeArg,
  EventClickArg,
} from '@fullcalendar/core'
import interactionPlugin from '@fullcalendar/interaction'
import listPlugin from '@fullcalendar/list'
import FullCalendar from '@fullcalendar/react'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../api'
import { ConfirmModal } from '../ConfirmModal'
import { CALENDAR_LIST_YEAR_VIEW, calendarListEventContent } from '../calendarListView'
import {
  defaultWritableCalendarId,
  writableCalendarPickerOptions,
} from '../calendarEventSync'
import { useExclusiveDropdownOpen } from '../useExclusiveDropdownOpen'
import type {
  CalendarCategoryOut,
  CalendarEventOut,
  CaseEventOut,
  UserPublic,
} from '../types'
import type { CalendarView } from '../useUserUiPreferences'
import { CalendarEventDraftModal } from './CalendarEventDraftModal'
import { CalendarManageModal } from './CalendarManageModal'
import {
  startHourMinuteFromDate,
  timedDurationFromRange,
  toBodyDate,
  type CalendarEventDraft,
  type CalendarEventDropdownKey,
} from './calendarDraftHelpers'
import {
  deleteCalendarEditEvent,
  saveCalendarCreate,
  saveCalendarEdit,
} from './calendarEventMutations'
import { useCalendarGrid } from './useCalendarGrid'

export function CalendarPage({
  token,
  me,
  onOpenSettings,
}: {
  token: string
  me?: UserPublic | null
  onOpenSettings: () => void
}) {
  const {
    calRef,
    calWrapRef,
    prefs,
    setPreference,
    calendarPixelHeight,
    needCaldav,
    calendarsLoaded,
    selectionReady,
    setEventsLoading,
    caldavSyncing,
    banner,
    setBanner,
    calendars,
    selectedCalIds,
    refresh,
    loadCalendars,
    transformEventFromApi,
    onEventDidMount,
    noEventsContent,
    fetchEvents,
    toggleCal,
  } = useCalendarGrid({ token, me })

  const [busy, setBusy] = useState(false)
  const [confirmDeleteEventOpen, setConfirmDeleteEventOpen] = useState(false)
  const [showManage, setShowManage] = useState(false)
  const [eventCategories, setEventCategories] = useState<CalendarCategoryOut[]>([])
  const [caseEventsForCreate, setCaseEventsForCreate] = useState<CaseEventOut[]>([])
  const [draft, setDraft] = useState<CalendarEventDraft | null>(null)

  const createEventCategory = draft?.kind === 'create' ? draft.eventCategory : null
  const createCaseId = draft?.kind === 'create' ? draft.caseId : ''
  const eventDropdown = useExclusiveDropdownOpen<CalendarEventDropdownKey>()

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
    [token, setBanner],
  )

  async function saveCreate() {
    if (!draft) return
    await saveCalendarCreate({
      draft,
      token,
      calendars,
      selectedCalIds,
      setBanner,
      setBusy,
      setDraft,
      refresh,
    })
  }

  async function saveEdit() {
    if (!draft) return
    await saveCalendarEdit({
      draft,
      token,
      calendars,
      selectedCalIds,
      setBanner,
      setBusy,
      setDraft,
      refresh,
    })
  }

  function requestDeleteEdit() {
    if (!draft || draft.kind !== 'edit' || !draft.canEdit || draft.editSource !== 'caldav') return
    setConfirmDeleteEventOpen(true)
  }

  async function performDeleteEditEvent() {
    if (!draft) return
    setConfirmDeleteEventOpen(false)
    await deleteCalendarEditEvent({
      draft,
      token,
      setBanner,
      setBusy,
      setDraft,
      refresh,
    })
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
        <CalendarEventDraftModal
          token={token}
          draft={draft}
          setDraft={setDraft}
          busy={busy}
          eventCategories={eventCategories}
          caseEventsForCreate={caseEventsForCreate}
          createTargetCalendarOptions={createTargetCalendarOptions}
          createTargetCalendarName={createTargetCalendarName}
          eventDropdown={eventDropdown}
          onSaveCreate={saveCreate}
          onSaveEdit={saveEdit}
          onRequestDelete={requestDeleteEdit}
        />
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
