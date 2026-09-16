import { useEffect, useMemo, useState } from 'react'
import { FilterDropdown } from './FilterDropdown'
import { runReportJson, runReportXlsx } from './reportRunner'
import type { FilterChrome, ReportSectionShared } from './sectionTypes'
import { formatMoneyPence } from './utils'

type Preview = {
  by_fee_earner?: {
    user_id: string
    display_name: string
    duration_minutes: number
    duration_hours: number
    value_pence: number
    entry_count: number
  }[]
  entries?: {
    entry_id: string
    case_id: string
    case_number: string
    client_name?: string | null
    fee_earner_name: string
    work_date: string
    duration_minutes: number
    description: string
    value_pence: number | null
    age_days: number
    age_bucket: string
  }[]
  totals?: { duration_minutes: number; value_pence: number; entry_count: number }
} | null

export function useWipReport(active: boolean) {
  const [wipAsOf, setWipAsOf] = useState('')
  const [preview, setPreview] = useState<Preview>(null)
  useEffect(() => {
    if (!active) setPreview(null)
  }, [active])
  const body = useMemo(() => {
    const o: Record<string, unknown> = {}
    if (wipAsOf.trim()) o.as_of = wipAsOf.trim()
    return o
  }, [wipAsOf])
  const asOfSummary = useMemo(() => (wipAsOf.trim() ? wipAsOf.trim() : 'Today'), [wipAsOf])
  return { wipAsOf, setWipAsOf, preview, setPreview, body, asOfSummary }
}

type State = ReturnType<typeof useWipReport>

export function WipReportFilters({ state, chrome }: { state: State; chrome: FilterChrome }) {
  return (
    <FilterDropdown
      id="wipAsOf"
      label="Age as of"
      summary={state.asOfSummary}
      openId={chrome.openFilterId}
      setOpenId={chrome.setOpenFilterId}
    >
      <div className="reportsDdDateFields">
        <label className="field">
          <span>As of date</span>
          <input type="date" value={state.wipAsOf} onChange={(e) => state.setWipAsOf(e.target.value)} />
        </label>
        <p className="muted" style={{ margin: '4px 0 0', fontSize: 12 }}>
          Leave empty to use today. Age buckets: 0–30, 31–90, and 90+ days from work date.
        </p>
      </div>
    </FilterDropdown>
  )
}

export function WipReportBody({ shared, state }: { shared: ReportSectionShared; state: State }) {
  const body = { ...shared.feeEarnerPayload, ...state.body }
  return (
    <section className="reportsSection">
      <p className="muted" style={{ marginTop: 0 }}>
        Unbilled time entries across matters, valued at each fee earner&apos;s charge rate. Written-off and billed
        time is excluded.
      </p>
      <div className="row" style={{ gap: 8, marginTop: 10 }}>
        <button
          type="button"
          className="btn primary"
          disabled={shared.busy}
          onClick={() => void runReportJson(shared, '/reports/wip', body, state.setPreview)}
        >
          Run report
        </button>
        <button
          type="button"
          className="btn"
          disabled={shared.busy}
          onClick={() => void runReportXlsx(shared, '/reports/wip', body, 'canary-report-wip.xlsx')}
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
                  <th>Hours</th>
                  <th>Value</th>
                  <th>Entries</th>
                </tr>
              </thead>
              <tbody>
                {state.preview.by_fee_earner.map((r) => (
                  <tr key={r.user_id}>
                    <td>{r.display_name}</td>
                    <td>{r.duration_hours}</td>
                    <td>{formatMoneyPence(r.value_pence)}</td>
                    <td>{r.entry_count}</td>
                  </tr>
                ))}
                {state.preview.totals ? (
                  <tr className="reportsTableTotalRow">
                    <td>
                      <strong>Total</strong>
                    </td>
                    <td>
                      <strong>{(state.preview.totals.duration_minutes / 60).toFixed(1)}</strong>
                    </td>
                    <td>
                      <strong>{formatMoneyPence(state.preview.totals.value_pence)}</strong>
                    </td>
                    <td>
                      <strong>{state.preview.totals.entry_count}</strong>
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
                    <th>Value</th>
                    <th>Age</th>
                    <th>Bucket</th>
                  </tr>
                </thead>
                <tbody>
                  {state.preview.entries.map((r) => (
                    <tr key={r.entry_id}>
                      <td>{r.case_number}</td>
                      <td>{r.client_name ?? ''}</td>
                      <td>{r.fee_earner_name}</td>
                      <td>{r.work_date}</td>
                      <td>{(r.duration_minutes / 60).toFixed(1)}</td>
                      <td>{r.description}</td>
                      <td>{r.value_pence != null ? formatMoneyPence(r.value_pence) : '—'}</td>
                      <td>{r.age_days}d</td>
                      <td>{r.age_bucket}</td>
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
