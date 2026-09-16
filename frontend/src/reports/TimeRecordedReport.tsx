import { useEffect, useMemo, useState } from 'react'
import { FilterDropdown } from './FilterDropdown'
import { runReportJson, runReportXlsx } from './reportRunner'
import type { FilterChrome, ReportSectionShared } from './sectionTypes'
import { dateRangeSummary, formatHoursFromMinutes, formatMoneyPence, timeStatusLabel } from './utils'

type Preview = {
  by_fee_earner?: {
    user_id: string
    display_name: string
    duration_hours: number
    billable_hours: number
    nil_rate_hours: number
    value_pence: number
    entry_count: number
    unbilled_minutes: number
    billed_minutes: number
    written_off_minutes: number
  }[]
  entries?: {
    entry_id: string
    case_number: string
    client_name?: string | null
    fee_earner_name: string
    work_date: string
    duration_minutes: number
    description: string
    non_billable: boolean
    status: string
    value_pence: number | null
  }[]
  totals?: {
    duration_minutes: number
    billable_minutes: number
    nil_rate_minutes: number
    value_pence: number
    entry_count: number
    unbilled_minutes: number
    billed_minutes: number
    written_off_minutes: number
  }
} | null

export function useTimeRecordedReport(active: boolean) {
  const [timeRecordedFrom, setTimeRecordedFrom] = useState('')
  const [timeRecordedTo, setTimeRecordedTo] = useState('')
  const [preview, setPreview] = useState<Preview>(null)
  useEffect(() => {
    if (!active) setPreview(null)
  }, [active])
  const body = useMemo(() => {
    const o: Record<string, unknown> = {}
    if (timeRecordedFrom.trim()) o.date_from = timeRecordedFrom.trim()
    if (timeRecordedTo.trim()) o.date_to = timeRecordedTo.trim()
    return o
  }, [timeRecordedFrom, timeRecordedTo])
  const dateSummary = useMemo(
    () => dateRangeSummary(timeRecordedFrom, timeRecordedTo),
    [timeRecordedFrom, timeRecordedTo],
  )
  return {
    timeRecordedFrom,
    setTimeRecordedFrom,
    timeRecordedTo,
    setTimeRecordedTo,
    preview,
    setPreview,
    body,
    dateSummary,
  }
}

type State = ReturnType<typeof useTimeRecordedReport>

export function TimeRecordedReportFilters({ state, chrome }: { state: State; chrome: FilterChrome }) {
  return (
    <FilterDropdown
      id="timeRecordedDates"
      label="Work date range"
      summary={state.dateSummary}
      openId={chrome.openFilterId}
      setOpenId={chrome.setOpenFilterId}
    >
      <div className="reportsDdDateFields">
        <label className="field">
          <span>From</span>
          <input type="date" value={state.timeRecordedFrom} onChange={(e) => state.setTimeRecordedFrom(e.target.value)} />
        </label>
        <label className="field">
          <span>To</span>
          <input type="date" value={state.timeRecordedTo} onChange={(e) => state.setTimeRecordedTo(e.target.value)} />
        </label>
        <p className="muted" style={{ margin: '4px 0 0', fontSize: 12 }}>
          Filter by work date on each time entry. Leave both empty for all time.
        </p>
      </div>
    </FilterDropdown>
  )
}

export function TimeRecordedReportBody({ shared, state }: { shared: ReportSectionShared; state: State }) {
  const body = { ...shared.feeEarnerPayload, ...state.body }
  return (
    <section className="reportsSection">
      <p className="muted" style={{ marginTop: 0 }}>
        Time logged on matters by work date — all statuses (unbilled, billed, written off) and nil-rate entries
        included. Value is at each fee earner&apos;s charge rate for billable entries only.
      </p>
      <div className="row" style={{ gap: 8, marginTop: 10 }}>
        <button
          type="button"
          className="btn primary"
          disabled={shared.busy}
          onClick={() => void runReportJson(shared, '/reports/time-recorded', body, state.setPreview)}
        >
          Run report
        </button>
        <button
          type="button"
          className="btn"
          disabled={shared.busy}
          onClick={() => void runReportXlsx(shared, '/reports/time-recorded', body, 'canary-report-time-recorded.xlsx')}
        >
          Export Excel
        </button>
      </div>
      {state.preview?.by_fee_earner ? (
        <div className="stack" style={{ gap: 16, marginTop: 12 }}>
          <div className="reportsPreviewScroll">
            <table className="reportsTable">
              <thead>
                <tr>
                  <th>Fee earner</th>
                  <th>Total hrs</th>
                  <th>Billable hrs</th>
                  <th>Nil-rate hrs</th>
                  <th>Value</th>
                  <th>Entries</th>
                  <th>Unbilled hrs</th>
                  <th>Billed hrs</th>
                  <th>Written-off hrs</th>
                </tr>
              </thead>
              <tbody>
                {state.preview.by_fee_earner.map((r) => (
                  <tr key={r.user_id}>
                    <td>{r.display_name}</td>
                    <td>{r.duration_hours}</td>
                    <td>{r.billable_hours}</td>
                    <td>{r.nil_rate_hours}</td>
                    <td>{formatMoneyPence(r.value_pence)}</td>
                    <td>{r.entry_count}</td>
                    <td>{formatHoursFromMinutes(r.unbilled_minutes)}</td>
                    <td>{formatHoursFromMinutes(r.billed_minutes)}</td>
                    <td>{formatHoursFromMinutes(r.written_off_minutes)}</td>
                  </tr>
                ))}
                {state.preview.totals ? (
                  <tr className="reportsTableTotalRow">
                    <td>
                      <strong>Total</strong>
                    </td>
                    <td>
                      <strong>{formatHoursFromMinutes(state.preview.totals.duration_minutes)}</strong>
                    </td>
                    <td>
                      <strong>{formatHoursFromMinutes(state.preview.totals.billable_minutes)}</strong>
                    </td>
                    <td>
                      <strong>{formatHoursFromMinutes(state.preview.totals.nil_rate_minutes)}</strong>
                    </td>
                    <td>
                      <strong>{formatMoneyPence(state.preview.totals.value_pence)}</strong>
                    </td>
                    <td>
                      <strong>{state.preview.totals.entry_count}</strong>
                    </td>
                    <td>
                      <strong>{formatHoursFromMinutes(state.preview.totals.unbilled_minutes)}</strong>
                    </td>
                    <td>
                      <strong>{formatHoursFromMinutes(state.preview.totals.billed_minutes)}</strong>
                    </td>
                    <td>
                      <strong>{formatHoursFromMinutes(state.preview.totals.written_off_minutes)}</strong>
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
          {state.preview.entries?.length ? (
            <div className="reportsPreviewScroll">
              <table className="reportsTable">
                <thead>
                  <tr>
                    <th>Reference</th>
                    <th>Client</th>
                    <th>Fee earner</th>
                    <th>Work date</th>
                    <th>Hours</th>
                    <th>Description</th>
                    <th>Nil rate</th>
                    <th>Status</th>
                    <th>Value</th>
                  </tr>
                </thead>
                <tbody>
                  {state.preview.entries.map((r) => (
                    <tr key={r.entry_id}>
                      <td>{r.case_number}</td>
                      <td>{r.client_name ?? ''}</td>
                      <td>{r.fee_earner_name}</td>
                      <td>{r.work_date}</td>
                      <td>{formatHoursFromMinutes(r.duration_minutes)}</td>
                      <td>{r.description}</td>
                      <td>{r.non_billable ? 'Yes' : 'No'}</td>
                      <td>{timeStatusLabel(r.status)}</td>
                      <td>{r.non_billable ? '—' : r.value_pence != null ? formatMoneyPence(r.value_pence) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
