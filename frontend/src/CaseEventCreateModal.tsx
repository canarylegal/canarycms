import { useEffect, useState } from 'react'
import { apiFetch } from './api'
import type { ApiError } from './api'
import type { CaseEventOut, CaseEventsOut } from './types'

function timeToApi(t: string): string {
  const s = t.trim()
  if (/^\d{2}:\d{2}$/.test(s)) return `${s}:00`
  if (/^\d{2}:\d{2}:\d{2}$/.test(s)) return s
  return '09:00:00'
}

export function CaseEventCreateModal({
  open,
  caseId,
  token,
  caseLabel,
  onClose,
  onSaved,
}: {
  open: boolean
  caseId: string
  token: string
  caseLabel: string
  onClose: () => void
  onSaved: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [events, setEvents] = useState<CaseEventOut[]>([])
  const [category, setCategory] = useState<'custom' | string>('custom')
  const [name, setName] = useState('')
  const [eventDate, setEventDate] = useState('')
  const [allDay, setAllDay] = useState(true)
  const [startTime, setStartTime] = useState('09:00')
  const [track, setTrack] = useState(false)

  useEffect(() => {
    if (!open) return
    let cancel = false
    setErr(null)
    setBusy(true)
    void apiFetch<CaseEventsOut>(`/cases/${caseId}/events`, { token })
      .then((out) => {
        if (cancel) return
        setEvents(out.events ?? [])
        setCategory('custom')
        setName('')
        const t = new Date()
        setEventDate(t.toISOString().slice(0, 10))
        setAllDay(true)
        setStartTime('09:00')
        setTrack(false)
      })
      .catch((e: unknown) => {
        if (!cancel) setErr((e as ApiError).message ?? 'Failed to load events')
      })
      .finally(() => {
        if (!cancel) setBusy(false)
      })
    return () => {
      cancel = true
    }
  }, [open, caseId, token])

  useEffect(() => {
    if (category === 'custom') return
    const row = events.find((e) => e.id === category)
    if (!row) return
    setName(row.name)
    setTrack(Boolean(row.track_in_calendar))
    const d = row.event_date?.slice(0, 10) ?? ''
    setEventDate(d || new Date().toISOString().slice(0, 10))
    setAllDay(row.event_all_day !== false)
    const tm = row.event_start_time
    if (tm && typeof tm === 'string') {
      setStartTime(tm.slice(0, 5))
    } else {
      setStartTime('09:00')
    }
  }, [category, events])

  function onCategoryChange(v: 'custom' | string) {
    setCategory(v)
    if (v === 'custom') {
      setName('')
      setTrack(false)
      setEventDate(new Date().toISOString().slice(0, 10))
      setAllDay(true)
      setStartTime('09:00')
    }
  }

  async function submit() {
    const nm = name.trim()
    if (!nm) {
      setErr('Please enter an event name.')
      return
    }
    if (!eventDate.trim()) {
      setErr('Please choose a date.')
      return
    }
    if (!allDay && !startTime.trim()) {
      setErr('Please choose a start time or enable all day.')
      return
    }
    setBusy(true)
    setErr(null)
    try {
      const datePart = eventDate.trim().slice(0, 10)
      const bodyBase: Record<string, unknown> = {
        name: nm,
        event_date: datePart,
        event_all_day: allDay,
        track_in_calendar: track,
      }
      if (!allDay) bodyBase.event_start_time = timeToApi(startTime)
      else bodyBase.event_start_time = null
      if (category === 'custom') {
        await apiFetch(`/cases/${caseId}/events`, {
          token,
          method: 'POST',
          json: bodyBase,
        })
      } else {
        await apiFetch(`/cases/${caseId}/events/${encodeURIComponent(category)}`, {
          token,
          method: 'PATCH',
          json: bodyBase,
        })
      }
      onSaved()
      onClose()
    } catch (e: unknown) {
      setErr((e as ApiError).message ?? 'Failed to save event')
    } finally {
      setBusy(false)
    }
  }

  if (!open) return null

  return (
    <div
      className="modalOverlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="case-event-create-title"
      onClick={(e) => e.target === e.currentTarget && !busy && onClose()}
      onKeyDown={(e) => e.key === 'Escape' && !busy && onClose()}
    >
      <div className="modal card" style={{ maxWidth: 520 }} onClick={(e) => e.stopPropagation()}>
        <div className="paneHead">
          <h2 id="case-event-create-title" style={{ margin: 0, fontSize: 18 }}>
            New case event
          </h2>
          <button type="button" className="btn" disabled={busy} onClick={onClose}>
            Cancel
          </button>
        </div>
        <div className="stack" style={{ marginTop: 12, gap: 12 }}>
          {caseLabel ? <div className="muted" style={{ fontSize: 13 }}>{caseLabel}</div> : null}
          {err ? <div className="error">{err}</div> : null}
          <label className="field">
            <span>Event category</span>
            <select
              value={category}
              disabled={busy}
              onChange={(e) => onCategoryChange(e.target.value as 'custom' | string)}
              aria-label="Event category"
            >
              <option value="custom">Custom</option>
              {events.map((ev) => (
                <option key={ev.id} value={ev.id}>
                  {ev.name}
                  {ev.template_id ? '' : ' (custom line)'}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Name</span>
            <input value={name} disabled={busy} onChange={(e) => setName(e.target.value)} placeholder="Event name…" />
          </label>
          <label className="field">
            <span>Date</span>
            <input type="date" value={eventDate} disabled={busy} onChange={(e) => setEventDate(e.target.value)} />
          </label>
          <label className="row" style={{ gap: 8, alignItems: 'center' }}>
            <input type="checkbox" checked={allDay} disabled={busy} onChange={(e) => setAllDay(e.target.checked)} />
            <span>All day</span>
          </label>
          {!allDay ? (
            <label className="field">
              <span>Start time</span>
              <input type="time" value={startTime} disabled={busy} onChange={(e) => setStartTime(e.target.value)} />
            </label>
          ) : null}
          <label className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
            <input type="checkbox" checked={track} disabled={busy} onChange={(e) => setTrack(e.target.checked)} />
            <span className="muted" style={{ lineHeight: 1.4 }}>
              Track in calendar — adds the event to your CalDAV calendar and creates a fee-earner task when appropriate.
            </span>
          </label>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button type="button" className="btn primary" disabled={busy} onClick={() => void submit()}>
              {busy ? 'Saving…' : 'Save event'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
