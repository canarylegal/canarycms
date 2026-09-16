import { useEffect, useMemo, useState } from 'react'
import { FilterDropdown } from './FilterDropdown'
import { runReportJson, runReportXlsx } from './reportRunner'
import type { FilterChrome, ReportSectionShared } from './sectionTypes'
import { AGED_DEBT_BUCKETS } from './types'
import { formatMoneyPence } from './utils'

type Preview = {
  rows?: {
    invoice_id: string
    case_number: string
    client_name?: string | null
    matter_description: string
    fee_earner_name: string
    invoice_number: string
    approved_at: string
    age_days: number
    age_bucket: string
    invoice_total_pence: number
    office_balance_pence: number
  }[]
  bucket_totals_pence?: Record<string, number>
} | null

export function useAgedDebtReport(active: boolean) {
  const [agedDebtAsOf, setAgedDebtAsOf] = useState('')
  const [preview, setPreview] = useState<Preview>(null)
  useEffect(() => {
    if (!active) setPreview(null)
  }, [active])
  const body = useMemo(() => {
    const o: Record<string, unknown> = {}
    if (agedDebtAsOf.trim()) o.as_of = agedDebtAsOf.trim()
    return o
  }, [agedDebtAsOf])
  const asOfSummary = useMemo(() => (agedDebtAsOf.trim() ? agedDebtAsOf.trim() : 'Today'), [agedDebtAsOf])
  return { agedDebtAsOf, setAgedDebtAsOf, preview, setPreview, body, asOfSummary }
}

type State = ReturnType<typeof useAgedDebtReport>

export function AgedDebtReportFilters({ state, chrome }: { state: State; chrome: FilterChrome }) {
  return (
    <FilterDropdown
      id="agedDebtAsOf"
      label="Age as of"
      summary={state.asOfSummary}
      openId={chrome.openFilterId}
      setOpenId={chrome.setOpenFilterId}
    >
      <div className="reportsDdDateFields">
        <label className="field">
          <span>As of date</span>
          <input type="date" value={state.agedDebtAsOf} onChange={(e) => state.setAgedDebtAsOf(e.target.value)} />
        </label>
        <p className="muted" style={{ margin: '4px 0 0', fontSize: 12 }}>
          Leave empty to use today. Age buckets are measured from invoice approval date.
        </p>
      </div>
    </FilterDropdown>
  )
}

export function AgedDebtReportBody({ shared, state }: { shared: ReportSectionShared; state: State }) {
  const body = { ...shared.feeEarnerPayload, ...state.body }
  return (
    <section className="reportsSection">
      <p className="muted" style={{ marginTop: 0 }}>
        Approved invoices on matters whose office balance is still debit (client owes). There is no separate
        paid flag — matter office balance is the debt indicator.
      </p>
      <div className="row" style={{ gap: 8, marginTop: 10 }}>
        <button
          type="button"
          className="btn primary"
          disabled={shared.busy}
          onClick={() => void runReportJson(shared, '/reports/aged-debt', body, state.setPreview)}
        >
          Run report
        </button>
        <button
          type="button"
          className="btn"
          disabled={shared.busy}
          onClick={() => void runReportXlsx(shared, '/reports/aged-debt', body, 'canary-report-aged-debt.xlsx')}
        >
          Export Excel
        </button>
      </div>
      {state.preview?.rows ? (
        <div className="reportsPreviewScroll">
          {state.preview.bucket_totals_pence ? (
            <div className="row" style={{ gap: 16, marginTop: 14, marginBottom: 8, flexWrap: 'wrap' }}>
              {AGED_DEBT_BUCKETS.map((b) => (
                <span key={b} className="muted" style={{ fontSize: 13 }}>
                  <strong>{b} days:</strong> {formatMoneyPence(state.preview?.bucket_totals_pence?.[b] ?? 0)}
                </span>
              ))}
            </div>
          ) : null}
          <table className="reportsTable">
            <thead>
              <tr>
                <th>Bucket</th>
                <th>Days</th>
                <th>Reference</th>
                <th>Client</th>
                <th>Invoice</th>
                <th>Fee earner</th>
                <th>Approved</th>
                <th>Invoice total</th>
                <th>Office balance</th>
              </tr>
            </thead>
            <tbody>
              {state.preview.rows.map((r) => (
                <tr key={r.invoice_id}>
                  <td>{r.age_bucket}</td>
                  <td>{r.age_days}</td>
                  <td>{r.case_number}</td>
                  <td>{r.client_name ?? ''}</td>
                  <td>{r.invoice_number}</td>
                  <td>{r.fee_earner_name}</td>
                  <td>{r.approved_at?.slice(0, 10) ?? ''}</td>
                  <td>{formatMoneyPence(r.invoice_total_pence)}</td>
                  <td>{formatMoneyPence(r.office_balance_pence)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  )
}
