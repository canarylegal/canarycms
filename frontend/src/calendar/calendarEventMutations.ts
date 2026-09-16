import { apiFetch } from '../api'
import type { ApiError } from '../api'
import {
  defaultWritableCalendarId,
  syncCaseEventToCalDav,
} from '../calendarEventSync'
import type { CalendarEventOut, CaseEventOut, CaseOut, UserCalendarListItem } from '../types'
import {
  buildCalDavTimesFromDraft,
  buildCaseEventApiPayload,
  buildTimedStartEnd,
  startOfLocalDay,
  toBodyDate,
  type CalendarEventDraft,
} from './calendarDraftHelpers'

type BannerSetter = (v: string | null) => void
type BusySetter = (v: boolean) => void
type DraftSetter = (v: CalendarEventDraft | null) => void

export async function saveCalendarCreate(opts: {
  draft: CalendarEventDraft
  token: string
  calendars: UserCalendarListItem[]
  selectedCalIds: string[]
  setBanner: BannerSetter
  setBusy: BusySetter
  setDraft: DraftSetter
  refresh: () => void
}): Promise<void> {
  const { draft, token, calendars, selectedCalIds, setBanner, setBusy, setDraft, refresh } = opts
  if (draft.kind !== 'create') return
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

export async function saveCalendarEdit(opts: {
  draft: CalendarEventDraft
  token: string
  calendars: UserCalendarListItem[]
  selectedCalIds: string[]
  setBanner: BannerSetter
  setBusy: BusySetter
  setDraft: DraftSetter
  refresh: () => void
}): Promise<void> {
  const { draft, token, calendars, selectedCalIds, setBanner, setBusy, setDraft, refresh } = opts
  if (draft.kind !== 'edit' || !draft.canEdit) return
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

export async function deleteCalendarEditEvent(opts: {
  draft: CalendarEventDraft
  token: string
  setBanner: BannerSetter
  setBusy: BusySetter
  setDraft: DraftSetter
  refresh: () => void
}): Promise<void> {
  const { draft, token, setBanner, setBusy, setDraft, refresh } = opts
  if (draft.kind !== 'edit' || !draft.canEdit || draft.editSource !== 'caldav') return
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
