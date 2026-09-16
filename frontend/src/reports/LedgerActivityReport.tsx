import { useEffect, useMemo, useState } from 'react'
import { scrollPanelClassName } from '../dropdownSizing'
import { FilterDropdown } from './FilterDropdown'
import { runReportJson, runReportXlsx } from './reportRunner'
import type { FilterChrome, ReportSectionShared } from './sectionTypes'
import { dateRangeSummary, formatLedgerLegs, formatMoneyPence } from './utils'

type Preview = {
  rows?: {
    pair_id: string
    case_number: string
    client_name?: string | null
    matter_description: string
    fee_earner_name: string
    posted_at: string
    posted_by_name: string
    description: string
    reference?: string
    amount_pence: number
    client_direction?: string | null
    office_direction?: string | null
    is_approved: boolean
    contact_label?: string | null
  }[]
} | null

export function useLedgerActivityReport(active: boolean) {
  const [ledgerFrom, setLedgerFrom] = useState('')
  const [ledgerTo, setLedgerTo] = useState('')
  const [ledgerApprovedOnly, setLedgerApprovedOnly] = useState(false)
  const [preview, setPreview] = useState<Preview>(null)
  useEffect(() => {
    if (!active) setPreview(null)
  }, [active])
  const body = useMemo(() => {
    const o: Record<string, unknown> = { approved_only: ledgerApprovedOnly }
    if (ledgerFrom.trim()) o.date_from = ledgerFrom.trim()
    if (ledgerTo.trim()) o.date_to = ledgerTo.trim()
    return o
  }, [ledgerFrom, ledgerTo, ledgerApprovedOnly])
  const dateSummary = useMemo(() => dateRangeSummary(ledgerFrom, ledgerTo), [ledgerFrom, ledgerTo])
  const approvedSummary = useMemo(
    () => (ledgerApprovedOnly ? 'Approved only' : 'All postings'),
    [ledgerApprovedOnly],
  )
  return {
    ledgerFrom,
    setLedgerFrom,
    ledgerTo,
    setLedgerTo,
    ledgerApprovedOnly,
    setLedgerApprovedOnly,
    preview,
    setPreview,
    body,
    dateSummary,
    approvedSummary,
  }
}

type State = ReturnType<typeof useLedgerActivityReport>

export function LedgerActivityReportFilters({ state, chrome }: { state: State; chrome: FilterChrome }) {
  return (
    <>
      <FilterDropdown
        id="ledgerDates"
        label="Posted date range"
        summary={state.dateSummary}
        openId={chrome.openFilterId}
        setOpenId={chrome.setOpenFilterId}
      >
        <div className="reportsDdDateFields">
          <label className="field">
            <span>From</span>
            <input type="date" value={state.ledgerFrom} onChange={(e) => state.setLedgerFrom(e.target.value)} />
          </label>
          <label className="field">
            <span>To</span>
            <input type="date" value={state.ledgerTo} onChange={(e) => state.setLedgerTo(e.target.value)} />
          </label>
          <p className="muted" style={{ margin: '4px 0 0', fontSize: 12 }}>
            Leave both empty for all time.
          </p>
        </div>
      </FilterDropdown>
      <FilterDropdown
        id="ledgerApproved"
        label="Approval status"
        summary={state.approvedSummary}
        openId={chrome.openFilterId}
        setOpenId={chrome.setOpenFilterId}
      >
        <div className={scrollPanelClassName('reportsDdCheckList', 1)}>
          <label className="reportsCheckbox">
            <input
              type="checkbox"
              checked={state.ledgerApprovedOnly}
              onChange={(e) => state.setLedgerApprovedOnly(e.target.checked)}
            />
            <span>Approved postings only</span>
          </label>
        </div>
      </FilterDropdown>
    </>
  )
}

export function LedgerActivityReportBody({ shared, state }: { shared: ReportSectionShared; state: State }) {
  const body = { ...shared.feeEarnerPayload, ...state.body }
  return (
    <section className="reportsSection">
      <p className="muted" style={{ marginTop: 0 }}>
        All ledger postings for matters in scope, newest first. Pending postings appear until approved.
      </p>
      <div className="row" style={{ gap: 8, marginTop: 10 }}>
        <button
          type="button"
          className="btn primary"
          disabled={shared.busy}
          onClick={() => void runReportJson(shared, '/reports/ledger-activity', body, state.setPreview)}
        >
          Run report
        </button>
        <button
          type="button"
          className="btn"
          disabled={shared.busy}
          onClick={() => void runReportXlsx(shared, '/reports/ledger-activity', body, 'canary-report-ledger-activity.xlsx')}
        >
          Export Excel
        </button>
      </div>
      {state.preview?.rows ? (
        <div className="reportsPreviewScroll">
          <table className="reportsTable">
            <thead>
              <tr>
                <th>Posted</th>
                <th>Reference</th>
                <th>Client</th>
                <th>Description</th>
                <th>Amount</th>
                <th>Legs</th>
                <th>Status</th>
                <th>Posted by</th>
              </tr>
            </thead>
            <tbody>
              {state.preview.rows.map((r) => (
                <tr key={r.pair_id}>
                  <td>{r.posted_at?.slice(0, 16)?.replace('T', ' ') ?? ''}</td>
                  <td>{r.case_number}</td>
                  <td>{r.client_name ?? ''}</td>
                  <td>
                    {r.description}
                    {r.reference ? (
                      <span className="muted" style={{ display: 'block', fontSize: 12 }}>
                        Ref: {r.reference}
                      </span>
                    ) : null}
                  </td>
                  <td>{formatMoneyPence(r.amount_pence)}</td>
                  <td>{formatLedgerLegs(r.client_direction, r.office_direction)}</td>
                  <td>{r.is_approved ? 'Approved' : 'Pending'}</td>
                  <td>{r.posted_by_name}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  )
}
