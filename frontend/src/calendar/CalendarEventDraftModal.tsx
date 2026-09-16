import type { Dispatch, SetStateAction } from 'react'
import { MatterSearchPicker } from '../MatterSearchPicker'
import { SingleSelectDropdown } from '../SingleSelectDropdown'
import type { CalendarCategoryOut, CaseEventOut } from '../types'
import {
  HOUR_SELECT_OPTIONS,
  START_MIN_SELECT_OPTIONS,
  DUR_DAY_SELECT_OPTIONS,
  DUR_HOUR_SELECT_OPTIONS,
  DUR_MIN_SELECT_OPTIONS,
  addDaysLocal,
  buildTimedStartEnd,
  calendarLabelOptions,
  localYmdFromDate,
  startOfLocalDay,
  type CalendarEventDraft,
  type CalendarEventDropdownKey,
} from './calendarDraftHelpers'

type EventDropdown = {
  isOpen: (key: CalendarEventDropdownKey) => boolean
  setOpen: (key: CalendarEventDropdownKey, next: boolean) => void
}

export function CalendarEventDraftModal({
  token,
  draft,
  setDraft,
  busy,
  eventCategories,
  caseEventsForCreate,
  createTargetCalendarOptions,
  createTargetCalendarName,
  eventDropdown,
  onSaveCreate,
  onSaveEdit,
  onRequestDelete,
}: {
  token: string
  draft: CalendarEventDraft
  setDraft: Dispatch<SetStateAction<CalendarEventDraft | null>>
  busy: boolean
  eventCategories: CalendarCategoryOut[]
  caseEventsForCreate: CaseEventOut[]
  createTargetCalendarOptions: { value: string; label: string }[]
  createTargetCalendarName: string | null
  eventDropdown: EventDropdown
  onSaveCreate: () => void | Promise<void>
  onSaveEdit: () => void | Promise<void>
  onRequestDelete: () => void
}) {
  const createEventCategoryOptions = [
    { value: 'custom', label: 'Custom' },
    ...caseEventsForCreate.map((ev) => ({
      value: ev.id,
      label: `${ev.name}${ev.template_id ? '' : ' (custom line)'}`,
    })),
  ]
  const editEventCategoryOptions = calendarLabelOptions(eventCategories)
  const createCalendarLabelOptions = calendarLabelOptions(eventCategories)

  return (

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
                <button type="button" className="btn primary" disabled={busy} onClick={() => void onSaveEdit()}>
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
                  onClick={() => void onSaveCreate()}
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
                  onClick={() => onRequestDelete()}
                  style={{ marginLeft: 'auto', color: 'var(--danger)' }}
                >
                  Delete
                </button>
              ) : null}
            </div>
          </div>
        </div>
  )
}
