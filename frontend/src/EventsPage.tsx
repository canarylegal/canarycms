import type { EventClickArg, EventInput } from '@fullcalendar/core'
import interactionPlugin from '@fullcalendar/interaction'
import listPlugin from '@fullcalendar/list'
import FullCalendar from '@fullcalendar/react'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from './api'
import type { ApiError } from './api'
import type { CalendarEventOut, CaseEventOut, CaseEventsOut } from './types'

interface Props {
  caseId: string
  token: string
  /** Shown in linked calendar event titles (e.g. case number + short description). */
  caseLabel?: string
  onClose: () => void
  /** In the case documents panel: slimmer chrome (no duplicate title block). */
  embedded?: boolean
  /** Open the parent “New case event” popup (Documents / Calendar toolbar). */
  onRequestNewEvent?: () => void
}

function toInputDate(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = iso.slice(0, 10)
  return /^\d{4}-\d{2}-\d{2}$/.test(d) ? d : ''
}

function datesEqual(a: string | null | undefined, b: string | null | undefined): boolean {
  const na = !a || !a.trim()
  const nb = !b || !b.trim()
  if (na && nb) return true
  if (na !== nb) return false
  return new Date(a as string).getTime() === new Date(b as string).getTime()
}

function eventRowChanged(was: CaseEventOut | undefined, ev: CaseEventOut): boolean {
  if (!was) return true
  if (!datesEqual(was.event_date, ev.event_date)) return true
  if ((was.track_in_calendar ?? false) !== (ev.track_in_calendar ?? false)) return true
  if ((was.event_all_day ?? true) !== (ev.event_all_day ?? true)) return true
  const wt = was.event_start_time?.slice(0, 8) ?? ''
  const et = ev.event_start_time?.slice(0, 8) ?? ''
  if (wt !== et) return true
  if (was.name !== ev.name) return true
  return false
}

/** All-day UTC range for CalDAV (exclusive end date). */
function allDayExclusiveEnd(iso: string | null | undefined): { start: string; end: string } | null {
  const d = iso?.slice(0, 10)
  if (!d || !/^\d{4}-\d{2}-\d{2}$/.test(d)) return null
  const [y, m, day] = d.split('-').map(Number)
  const next = new Date(Date.UTC(y, m - 1, day))
  next.setUTCDate(next.getUTCDate() + 1)
  return { start: d, end: next.toISOString().slice(0, 10) }
}

function caseEventToFullCalendar(ev: CaseEventOut): EventInput | null {
  if (
    ev.calendar_block_start &&
    ev.calendar_block_end &&
    ev.calendar_block_all_day === false
  ) {
    return {
      id: ev.id,
      title: ev.name,
      allDay: false,
      start: ev.calendar_block_start,
      end: ev.calendar_block_end,
      extendedProps: { caseEvent: ev },
      backgroundColor: ev.track_in_calendar ? 'var(--primary)' : 'var(--border)',
      borderColor: 'transparent',
      textColor: ev.track_in_calendar ? '#fff' : 'var(--text)',
    }
  }
  const d = toInputDate(ev.event_date ?? undefined)
  if (!d) return null
  const [y, mo, day] = d.split('-').map(Number)
  const next = new Date(Date.UTC(y, mo - 1, day))
  next.setUTCDate(next.getUTCDate() + 1)
  const endExclusive = next.toISOString().slice(0, 10)
  return {
    id: ev.id,
    title: ev.name,
    allDay: true,
    start: d,
    end: endExclusive,
    extendedProps: { caseEvent: ev },
    backgroundColor: ev.track_in_calendar ? 'var(--primary)' : 'var(--border)',
    borderColor: 'transparent',
    textColor: ev.track_in_calendar ? '#fff' : 'var(--text)',
  }
}

async function syncCalendarsForCaseEvents(
  events: CaseEventOut[],
  caseId: string,
  token: string,
  caseLabel: string,
): Promise<void> {
  const label = caseLabel.trim() || 'Case'
  for (const ev of events) {
    const rangeAllDay = allDayExclusiveEnd(ev.event_date ?? null)
    const timed =
      ev.calendar_block_all_day === false && ev.calendar_block_start && ev.calendar_block_end
    const track = Boolean(ev.track_in_calendar && (timed || rangeAllDay))

    if (!track) {
      if (ev.calendar_event_uid) {
        try {
          await apiFetch(`/users/me/calendar/events/${encodeURIComponent(ev.calendar_event_uid)}`, {
            method: 'DELETE',
            token,
          })
        } catch {
          /* event already removed */
        }
        try {
          await apiFetch(`/cases/${caseId}/events/${ev.id}`, {
            token,
            method: 'PATCH',
            json: { calendar_event_uid: null },
          })
        } catch {
          /* best effort */
        }
      }
      continue
    }

    const title = `${label}: ${ev.name}`.slice(0, 500)
    const desc = `Canary tracked case event (${label}).`
    const calBody = timed
      ? {
          title,
          start: ev.calendar_block_start,
          end: ev.calendar_block_end,
          all_day: false,
          description: desc,
        }
      : {
          title,
          start: rangeAllDay!.start,
          end: rangeAllDay!.end,
          all_day: true,
          description: desc,
        }

    if (ev.calendar_event_uid) {
      try {
        await apiFetch(`/users/me/calendar/events/${encodeURIComponent(ev.calendar_event_uid)}`, {
          token,
          method: 'PATCH',
          json: calBody,
        })
      } catch {
        try {
          const created = await apiFetch<CalendarEventOut>(`/users/me/calendar/events`, {
            token,
            method: 'POST',
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
    } else {
      try {
        const created = await apiFetch<CalendarEventOut>(`/users/me/calendar/events`, {
          token,
          method: 'POST',
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
  }
}

export function EventsPage({
  caseId,
  token,
  caseLabel = '',
  onClose,
  embedded = false,
  onRequestNewEvent,
}: Props) {
  const [data, setData] = useState<CaseEventsOut | null>(null)
  const [baseline, setBaseline] = useState<CaseEventsOut | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [eventDetail, setEventDetail] = useState<CaseEventOut | null>(null)

  const load = useCallback(async () => {
    setBusy(true)
    setErr(null)
    try {
      const out = await apiFetch<CaseEventsOut>(`/cases/${caseId}/events`, { token })
      setData(out)
      setBaseline(JSON.parse(JSON.stringify(out)) as CaseEventsOut)
    } catch (e) {
      setErr((e as ApiError).message ?? 'Failed to load events')
      setData(null)
      setBaseline(null)
    } finally {
      setBusy(false)
    }
  }, [caseId, token])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (!eventDetail) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setEventDetail(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [eventDetail])

  const fcEvents = useMemo((): EventInput[] => {
    if (!data?.events?.length) return []
    const out: EventInput[] = []
    for (const ev of data.events) {
      const mapped = caseEventToFullCalendar(ev)
      if (mapped) out.push(mapped)
    }
    return out
  }, [data?.events])

  const undatedEvents = useMemo(() => {
    if (!data?.events?.length) return []
    return data.events.filter((e) => !toInputDate(e.event_date ?? undefined))
  }, [data?.events])

  function discard() {
    if (baseline) {
      setData(JSON.parse(JSON.stringify(baseline)) as CaseEventsOut)
    }
    onClose()
  }

  async function saveAllAndClose() {
    if (!data) {
      onClose()
      return
    }
    setBusy(true)
    setErr(null)
    try {
      const baseEv = new Map((baseline?.events ?? []).map((e) => [e.id, e]))
      for (const ev of data.events) {
        const was = baseEv.get(ev.id)
        if (!eventRowChanged(was, ev)) continue
        const raw = ev.event_date
        const d = raw != null && String(raw).trim() !== '' ? String(raw).slice(0, 10) : null
        const allDay = ev.event_all_day !== false
        const tm = ev.event_start_time
        const timeApi = allDay
          ? null
          : tm && String(tm).trim() !== ''
            ? `${String(tm).slice(0, 5)}:00`
            : '09:00:00'
        await apiFetch<CaseEventOut>(`/cases/${caseId}/events/${ev.id}`, {
          token,
          method: 'PATCH',
          json: {
            name: ev.name,
            event_date: d,
            event_all_day: allDay,
            event_start_time: timeApi,
            track_in_calendar: ev.track_in_calendar ?? false,
          },
        })
      }
      let fresh = await apiFetch<CaseEventsOut>(`/cases/${caseId}/events`, { token })
      await syncCalendarsForCaseEvents(fresh.events, caseId, token, caseLabel)
      fresh = await apiFetch<CaseEventsOut>(`/cases/${caseId}/events`, { token })
      setBaseline(JSON.parse(JSON.stringify(fresh)) as CaseEventsOut)
      onClose()
    } catch (e) {
      setErr((e as ApiError).message ?? 'Failed to save events')
    } finally {
      setBusy(false)
    }
  }

  function onFcEventClick(arg: EventClickArg) {
    const raw = arg.event.extendedProps.caseEvent as CaseEventOut | undefined
    if (raw) setEventDetail({ ...raw })
  }

  function applyEventDetailFromModal() {
    if (!eventDetail || !data) return
    setData((prev) => {
      if (!prev) return prev
      return {
        ...prev,
        events: prev.events.map((x) => (x.id === eventDetail.id ? { ...eventDetail } : x)),
      }
    })
    setEventDetail(null)
  }

  return (
    <div
      className={`stack${embedded ? ' eventsPageEmbed' : ''}`}
      style={{
        padding: embedded ? '0' : '4px 4px 0',
        ...(embedded ? { flex: 1, minHeight: 0, height: '100%' } : {}),
      }}
    >
      {embedded ? (
        <div
          className="row"
          style={{
            justifyContent: 'space-between',
            alignItems: 'flex-start',
            flexWrap: 'wrap',
            gap: 8,
            marginBottom: 8,
          }}
        >
          <div className="muted" style={{ fontSize: 13, flex: '1 1 200px' }}>
            Click an event to edit details; use the calendar header for month, week, day, or list. Save when done.
          </div>
          <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            {onRequestNewEvent ? (
              <button type="button" className="btn primary" disabled={busy} onClick={() => onRequestNewEvent()}>
                New event
              </button>
            ) : null}
            <button type="button" className="btn" disabled={busy} onClick={discard}>
              Discard changes
            </button>
            <button
              type="button"
              className="btn"
              style={{ background: 'var(--primary)', color: '#fff', borderColor: 'var(--primary)' }}
              disabled={busy}
              onClick={() => void saveAllAndClose()}
            >
              Save and close
            </button>
          </div>
        </div>
      ) : (
        <div className="paneHead" style={{ marginBottom: 12 }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 18 }}>Calendar</h2>
            <div className="muted" style={{ marginTop: 4 }}>
              Set dates and optionally track in your calendar. When you track an event (with a date), Canary adds a task for
              the fee earner with higher priority when the date is within five UK working days or overdue. Save and close to
              apply.
            </div>
          </div>
          <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            {onRequestNewEvent ? (
              <button type="button" className="btn primary" disabled={busy} onClick={() => onRequestNewEvent()}>
                New event
              </button>
            ) : null}
            <button type="button" className="btn" disabled={busy} onClick={discard}>
              Discard changes
            </button>
            <button
              type="button"
              className="btn"
              style={{ background: 'var(--primary)', color: '#fff', borderColor: 'var(--primary)' }}
              disabled={busy}
              onClick={() => void saveAllAndClose()}
            >
              Save and close
            </button>
          </div>
        </div>
      )}

      {err ? <div className="error">{err}</div> : null}

      {busy && !data ? <div className="muted">Loading…</div> : null}

      {data && data.events.length === 0 ? (
        <div className="muted" style={{ marginBottom: 10 }}>
          No events yet. Use New event, or ask an administrator to configure template lines under Admin → Sub-Menus.
        </div>
      ) : null}

      {data ? (
        <div
          className={`stack${embedded ? ' eventsPageEmbedGrow' : ''}`}
          style={{ gap: 8, marginBottom: embedded ? 0 : 12 }}
        >
          {undatedEvents.length > 0 ? (
            <div className="muted stack" style={{ fontSize: 13, gap: 6 }}>
              <span>Events without a date do not appear on the grid — click a name to set a date and tracking:</span>
              <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
                {undatedEvents.map((ev) => (
                  <button
                    key={ev.id}
                    type="button"
                    className="btn"
                    disabled={busy}
                    onClick={() => setEventDetail({ ...ev })}
                  >
                    {ev.name}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          <div
            className="card canaryCalendar"
            style={{
              padding: 12,
              flex: 1,
              minHeight: embedded ? 0 : undefined,
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
            }}
          >
            <div className="canaryCalendarInner" style={{ minHeight: embedded ? 0 : 440 }}>
              <FullCalendar
                plugins={[dayGridPlugin, timeGridPlugin, listPlugin, interactionPlugin]}
                initialView="dayGridMonth"
                headerToolbar={{
                  left: 'prev,next today',
                  center: 'title',
                  right: 'dayGridMonth,timeGridWeek,timeGridDay,listWeek',
                }}
                height={embedded ? '100%' : 440}
                weekends
                editable={false}
                selectable={false}
                events={fcEvents}
                eventClick={onFcEventClick}
                nowIndicator
                eventTimeFormat={{ hour: '2-digit', minute: '2-digit', hour12: false }}
              />
            </div>
          </div>
        </div>
      ) : null}

      {eventDetail ? (
        <div
          className="modalOverlay"
          style={{ zIndex: 40 }}
          role="dialog"
          aria-modal="true"
          aria-labelledby="caseEventDetailTitle"
          onClick={() => setEventDetail(null)}
        >
          <div
            className="modal card"
            style={{ maxWidth: 440, padding: 20 }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="caseEventDetailTitle" style={{ margin: '0 0 12px', fontSize: 18 }}>
              Edit event
            </h2>
            <div className="stack" style={{ gap: 12 }}>
              <label className="field" style={{ marginBottom: 0 }}>
                <span>Name</span>
                <input
                  className="input"
                  value={eventDetail.name}
                  disabled={busy}
                  onChange={(e) => setEventDetail((prev) => (prev ? { ...prev, name: e.target.value } : prev))}
                />
              </label>
              <label className="field" style={{ marginBottom: 0 }}>
                <span>Date</span>
                <div className="row" style={{ gap: 8, alignItems: 'center' }}>
                  <input
                    type="date"
                    className="input"
                    style={{ flex: 1 }}
                    value={toInputDate(eventDetail.event_date ?? undefined)}
                    disabled={busy}
                    onChange={(e) => {
                      const v = e.target.value
                      const event_date = v === '' ? null : v
                      setEventDetail((prev) => (prev ? { ...prev, event_date } : prev))
                    }}
                  />
                  <button
                    type="button"
                    className="btn"
                    disabled={busy || !eventDetail.event_date}
                    onClick={() => setEventDetail((prev) => (prev ? { ...prev, event_date: null } : prev))}
                  >
                    Clear
                  </button>
                </div>
              </label>
              <label className="row" style={{ gap: 8, alignItems: 'center', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={eventDetail.event_all_day !== false}
                  disabled={busy || !eventDetail.event_date}
                  onChange={(e) =>
                    setEventDetail((prev) =>
                      prev ? { ...prev, event_all_day: e.target.checked, event_start_time: e.target.checked ? null : prev.event_start_time } : prev,
                    )
                  }
                />
                <span>All day</span>
              </label>
              {eventDetail.event_date && eventDetail.event_all_day === false ? (
                <label className="field" style={{ marginBottom: 0 }}>
                  <span>Start time</span>
                  <input
                    type="time"
                    className="input"
                    value={
                      eventDetail.event_start_time && eventDetail.event_start_time.length >= 5
                        ? eventDetail.event_start_time.slice(0, 5)
                        : '09:00'
                    }
                    disabled={busy}
                    onChange={(e) =>
                      setEventDetail((prev) =>
                        prev ? { ...prev, event_start_time: `${e.target.value}:00` } : prev,
                      )
                    }
                  />
                </label>
              ) : null}
              <label className="row" style={{ gap: 8, alignItems: 'center', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={eventDetail.track_in_calendar ?? false}
                  disabled={busy || !eventDetail.event_date}
                  onChange={(e) =>
                    setEventDetail((prev) => (prev ? { ...prev, track_in_calendar: e.target.checked } : prev))
                  }
                />
                <span>Track in calendar</span>
              </label>
            </div>
            <div className="row" style={{ justifyContent: 'flex-end', gap: 8, marginTop: 20 }}>
              <button type="button" className="btn" onClick={() => setEventDetail(null)}>
                Cancel
              </button>
              <button type="button" className="btn primary" onClick={applyEventDetailFromModal}>
                Apply
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
