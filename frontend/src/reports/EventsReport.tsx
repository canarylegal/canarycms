import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../api'
import type { CalendarEventTemplatePickOut } from '../types'
import { scrollPanelClassName } from '../dropdownSizing'
import { FilterDropdown } from './FilterDropdown'
import { runReportJson, runReportXlsx } from './reportRunner'
import type { FilterChrome, ReportSectionShared } from './sectionTypes'
import { dateRangeSummary } from './utils'

type Preview = {
  rows?: {
    event_id?: string
    event_name: string
    event_date?: string | null
    event_category: string
    case_number: string
    matter_description: string
    fee_earner_name: string
  }[]
} | null

export function useEventsReport(active: boolean, token: string) {
  const [evFrom, setEvFrom] = useState('')
  const [evTo, setEvTo] = useState('')
  const [evTemplates, setEvTemplates] = useState<CalendarEventTemplatePickOut[]>([])
  const [evTemplateSel, setEvTemplateSel] = useState<Set<string>>(new Set())
  const [preview, setPreview] = useState<Preview>(null)

  const loadEventTemplates = useCallback(async () => {
    try {
      const rows = await apiFetch<CalendarEventTemplatePickOut[]>('/users/me/calendar/event-line-templates', { token })
      setEvTemplates(rows)
    } catch {
      setEvTemplates([])
    }
  }, [token])

  useEffect(() => {
    void loadEventTemplates()
  }, [loadEventTemplates])

  useEffect(() => {
    if (!active) setPreview(null)
  }, [active])

  const body = useMemo(() => {
    const o: Record<string, unknown> = {}
    if (evFrom.trim()) o.date_from = evFrom.trim()
    if (evTo.trim()) o.date_to = evTo.trim()
    if (evTemplateSel.size > 0) o.template_ids = Array.from(evTemplateSel)
    return o
  }, [evFrom, evTo, evTemplateSel])

  const dateSummary = useMemo(() => dateRangeSummary(evFrom, evTo), [evFrom, evTo])
  const templateSummary = useMemo(() => {
    if (evTemplateSel.size === 0) return 'All templates'
    if (evTemplateSel.size === 1) {
      const id = Array.from(evTemplateSel)[0]
      const t = evTemplates.find((x) => x.id === id)
      return t?.name ?? '1 template'
    }
    return `${evTemplateSel.size} templates`
  }, [evTemplateSel, evTemplates])

  function toggleEvTemplate(id: string) {
    setEvTemplateSel((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return {
    evFrom,
    setEvFrom,
    evTo,
    setEvTo,
    evTemplates,
    evTemplateSel,
    setEvTemplateSel,
    preview,
    setPreview,
    body,
    dateSummary,
    templateSummary,
    toggleEvTemplate,
  }
}

type State = ReturnType<typeof useEventsReport>

export function EventsReportFilters({ state, chrome }: { state: State; chrome: FilterChrome }) {
  return (
    <>
      <FilterDropdown
        id="evDates"
        label="Event date range"
        summary={state.dateSummary}
        openId={chrome.openFilterId}
        setOpenId={chrome.setOpenFilterId}
      >
        <div className="reportsDdDateFields">
          <label className="field">
            <span>From</span>
            <input type="date" value={state.evFrom} onChange={(e) => state.setEvFrom(e.target.value)} />
          </label>
          <label className="field">
            <span>To</span>
            <input type="date" value={state.evTo} onChange={(e) => state.setEvTo(e.target.value)} />
          </label>
          <p className="muted" style={{ margin: '4px 0 0', fontSize: 12 }}>
            Leave both empty to ignore event date.
          </p>
        </div>
      </FilterDropdown>
      <FilterDropdown
        id="evTpl"
        label="Calendar template"
        summary={state.templateSummary}
        openId={chrome.openFilterId}
        setOpenId={chrome.setOpenFilterId}
        footer={
          <button type="button" className="btn btn--small" onClick={() => state.setEvTemplateSel(new Set())}>
            Clear (all templates)
          </button>
        }
      >
        <p className="muted" style={{ margin: '0 0 8px', fontSize: 12 }}>
          Admin → Sub-menus → Events. Leave none ticked for all templates.
        </p>
        <div className={scrollPanelClassName('reportsDdCheckList reportsDdCheckList--tall', state.evTemplates.length)}>
          {state.evTemplates.map((t) => (
            <label key={t.id} className="reportsCheckbox">
              <input type="checkbox" checked={state.evTemplateSel.has(t.id)} onChange={() => state.toggleEvTemplate(t.id)} />
              <span>
                {t.name}
                <span className="muted" style={{ fontSize: 12 }}>
                  {' '}
                  — {t.matter_sub_type_name}
                </span>
              </span>
            </label>
          ))}
        </div>
      </FilterDropdown>
    </>
  )
}

export function EventsReportBody({ shared, state }: { shared: ReportSectionShared; state: State }) {
  const body = { ...shared.feeEarnerPayload, ...state.body }
  return (
    <section className="reportsSection">
      <div className="row" style={{ gap: 8, marginTop: 10 }}>
        <button
          type="button"
          className="btn primary"
          disabled={shared.busy}
          onClick={() => void runReportJson(shared, '/reports/events', body, state.setPreview)}
        >
          Run report
        </button>
        <button
          type="button"
          className="btn"
          disabled={shared.busy}
          onClick={() => void runReportXlsx(shared, '/reports/events', body, 'canary-report-events.xlsx')}
        >
          Export Excel
        </button>
      </div>
      {state.preview?.rows ? (
        <div className="reportsPreviewScroll">
          <table className="reportsTable">
            <thead>
              <tr>
                <th>Event</th>
                <th>Date</th>
                <th>Template</th>
                <th>Reference</th>
                <th>Matter</th>
                <th>Fee earner</th>
              </tr>
            </thead>
            <tbody>
              {state.preview.rows.map((r) => (
                <tr key={r.event_id ?? `${r.case_number}-${r.event_name}-${r.event_date ?? ''}`}>
                  <td>{r.event_name}</td>
                  <td>{r.event_date ?? ''}</td>
                  <td>{r.event_category ?? ''}</td>
                  <td>{r.case_number}</td>
                  <td>{r.matter_description}</td>
                  <td>{r.fee_earner_name}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  )
}
