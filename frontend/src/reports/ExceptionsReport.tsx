import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { FilterDropdown } from './FilterDropdown'
import { runReportJson, runReportXlsx } from './reportRunner'
import type { FilterChrome, ReportSectionShared } from './sectionTypes'
import { dateRangeSummary, formatLedgerLegs, formatMoneyPence } from './utils'

type ExceptionBalRow = {
  case_number: string
  client_name?: string | null
  matter_description: string
  status_label: string
  fee_earner_name: string
  client_balance_pence: number
  office_balance_pence: number
}

type ExceptionLedgerRow = {
  pair_id: string
  case_number: string
  client_name?: string | null
  matter_description: string
  fee_earner_name: string
  posted_at: string
  posted_by_name: string
  description: string
  amount_pence: number
  client_direction?: string | null
  office_direction?: string | null
  is_approved?: boolean
}

type Preview = {
  pending_ledger_approvals?: ExceptionLedgerRow[]
  pending_invoices?: {
    invoice_id: string
    case_number: string
    client_name?: string | null
    matter_description: string
    fee_earner_name: string
    invoice_number: string
    created_at: string
    total_pence: number
  }[]
  client_balance_closed_archived?: ExceptionBalRow[]
  negative_client_balance?: ExceptionBalRow[]
  large_postings?: ExceptionLedgerRow[]
} | null

function ExceptionSection({ title, empty, children }: { title: string; empty: boolean; children: ReactNode }) {
  return (
    <div style={{ marginTop: 20 }}>
      <h3 style={{ margin: '0 0 8px', fontSize: 15 }}>{title}</h3>
      {empty ? <p className="muted" style={{ margin: 0 }}>None.</p> : children}
    </div>
  )
}

export function useExceptionsReport(active: boolean) {
  const [excFrom, setExcFrom] = useState('')
  const [excTo, setExcTo] = useState('')
  const [excLargeMinPounds, setExcLargeMinPounds] = useState('5000')
  const [preview, setPreview] = useState<Preview>(null)
  useEffect(() => {
    if (!active) setPreview(null)
  }, [active])
  const body = useMemo(() => {
    const o: Record<string, unknown> = {}
    if (excFrom.trim()) o.date_from = excFrom.trim()
    if (excTo.trim()) o.date_to = excTo.trim()
    const pounds = parseFloat(excLargeMinPounds.replace(/,/g, ''))
    if (Number.isFinite(pounds) && pounds > 0) {
      o.large_posting_min_pence = Math.round(pounds * 100)
    }
    return o
  }, [excFrom, excTo, excLargeMinPounds])
  const dateSummary = useMemo(() => dateRangeSummary(excFrom, excTo), [excFrom, excTo])
  const largeSummary = useMemo(() => {
    const pounds = parseFloat(excLargeMinPounds.replace(/,/g, ''))
    return Number.isFinite(pounds) && pounds > 0 ? `≥ £${pounds.toLocaleString()}` : '≥ £5,000'
  }, [excLargeMinPounds])
  return {
    excFrom,
    setExcFrom,
    excTo,
    setExcTo,
    excLargeMinPounds,
    setExcLargeMinPounds,
    preview,
    setPreview,
    body,
    dateSummary,
    largeSummary,
  }
}

type State = ReturnType<typeof useExceptionsReport>

export function ExceptionsReportFilters({ state, chrome }: { state: State; chrome: FilterChrome }) {
  return (
    <>
      <FilterDropdown
        id="excDates"
        label="Large posting dates"
        summary={state.dateSummary}
        openId={chrome.openFilterId}
        setOpenId={chrome.setOpenFilterId}
      >
        <div className="reportsDdDateFields">
          <label className="field">
            <span>From</span>
            <input type="date" value={state.excFrom} onChange={(e) => state.setExcFrom(e.target.value)} />
          </label>
          <label className="field">
            <span>To</span>
            <input type="date" value={state.excTo} onChange={(e) => state.setExcTo(e.target.value)} />
          </label>
          <p className="muted" style={{ margin: '4px 0 0', fontSize: 12 }}>
            Applies to the large postings section only. Leave both empty for all time.
          </p>
        </div>
      </FilterDropdown>
      <FilterDropdown
        id="excLarge"
        label="Large posting minimum"
        summary={state.largeSummary}
        openId={chrome.openFilterId}
        setOpenId={chrome.setOpenFilterId}
      >
        <label className="field">
          <span>Minimum amount (£)</span>
          <input
            type="number"
            min={1}
            step={100}
            value={state.excLargeMinPounds}
            onChange={(e) => state.setExcLargeMinPounds(e.target.value)}
          />
        </label>
      </FilterDropdown>
    </>
  )
}

export function ExceptionsReportBody({ shared, state }: { shared: ReportSectionShared; state: State }) {
  const body = { ...shared.feeEarnerPayload, ...state.body }
  const preview = state.preview
  return (
    <section className="reportsSection">
      <p className="muted" style={{ marginTop: 0 }}>
        Month-end exception checks: pending approvals, closed matters with client money, negative client balances,
        and large postings.
      </p>
      <div className="row" style={{ gap: 8, marginTop: 10 }}>
        <button
          type="button"
          className="btn primary"
          disabled={shared.busy}
          onClick={() => void runReportJson(shared, '/reports/exceptions', body, state.setPreview)}
        >
          Run report
        </button>
        <button
          type="button"
          className="btn"
          disabled={shared.busy}
          onClick={() => void runReportXlsx(shared, '/reports/exceptions', body, 'canary-report-exceptions.xlsx')}
        >
          Export Excel
        </button>
      </div>
      {preview ? (
        <div className="reportsPreviewScroll">
          <ExceptionSection title="Pending ledger approvals" empty={!(preview.pending_ledger_approvals?.length)}>
            <table className="reportsTable">
              <thead>
                <tr>
                  <th>Posted</th>
                  <th>Reference</th>
                  <th>Description</th>
                  <th>Amount</th>
                  <th>Legs</th>
                  <th>Posted by</th>
                </tr>
              </thead>
              <tbody>
                {preview.pending_ledger_approvals?.map((r) => (
                  <tr key={r.pair_id}>
                    <td>{r.posted_at?.slice(0, 16)?.replace('T', ' ') ?? ''}</td>
                    <td>{r.case_number}</td>
                    <td>{r.description}</td>
                    <td>{formatMoneyPence(r.amount_pence)}</td>
                    <td>{formatLedgerLegs(r.client_direction, r.office_direction)}</td>
                    <td>{r.posted_by_name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ExceptionSection>

          <ExceptionSection title="Pending invoices" empty={!(preview.pending_invoices?.length)}>
            <table className="reportsTable">
              <thead>
                <tr>
                  <th>Created</th>
                  <th>Reference</th>
                  <th>Invoice</th>
                  <th>Fee earner</th>
                  <th>Total</th>
                </tr>
              </thead>
              <tbody>
                {preview.pending_invoices?.map((r) => (
                  <tr key={r.invoice_id}>
                    <td>{r.created_at?.slice(0, 16)?.replace('T', ' ') ?? ''}</td>
                    <td>{r.case_number}</td>
                    <td>{r.invoice_number}</td>
                    <td>{r.fee_earner_name}</td>
                    <td>{formatMoneyPence(r.total_pence)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ExceptionSection>

          <ExceptionSection
            title="Client balance on closed / archived matters"
            empty={!(preview.client_balance_closed_archived?.length)}
          >
            <table className="reportsTable">
              <thead>
                <tr>
                  <th>Reference</th>
                  <th>Client</th>
                  <th>Status</th>
                  <th>Fee earner</th>
                  <th>Client balance</th>
                  <th>Office balance</th>
                </tr>
              </thead>
              <tbody>
                {preview.client_balance_closed_archived?.map((r) => (
                  <tr key={`${r.case_number}-closed`}>
                    <td>{r.case_number}</td>
                    <td>{r.client_name ?? ''}</td>
                    <td>{r.status_label}</td>
                    <td>{r.fee_earner_name}</td>
                    <td>{formatMoneyPence(r.client_balance_pence)}</td>
                    <td>{formatMoneyPence(r.office_balance_pence)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ExceptionSection>

          <ExceptionSection title="Negative client balance" empty={!(preview.negative_client_balance?.length)}>
            <table className="reportsTable">
              <thead>
                <tr>
                  <th>Reference</th>
                  <th>Client</th>
                  <th>Status</th>
                  <th>Fee earner</th>
                  <th>Client balance</th>
                </tr>
              </thead>
              <tbody>
                {preview.negative_client_balance?.map((r) => (
                  <tr key={`${r.case_number}-neg`}>
                    <td>{r.case_number}</td>
                    <td>{r.client_name ?? ''}</td>
                    <td>{r.status_label}</td>
                    <td>{r.fee_earner_name}</td>
                    <td>{formatMoneyPence(r.client_balance_pence)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ExceptionSection>

          <ExceptionSection title="Large postings" empty={!(preview.large_postings?.length)}>
            <table className="reportsTable">
              <thead>
                <tr>
                  <th>Posted</th>
                  <th>Reference</th>
                  <th>Description</th>
                  <th>Amount</th>
                  <th>Status</th>
                  <th>Posted by</th>
                </tr>
              </thead>
              <tbody>
                {preview.large_postings?.map((r) => (
                  <tr key={r.pair_id}>
                    <td>{r.posted_at?.slice(0, 16)?.replace('T', ' ') ?? ''}</td>
                    <td>{r.case_number}</td>
                    <td>{r.description}</td>
                    <td>{formatMoneyPence(r.amount_pence)}</td>
                    <td>{r.is_approved ? 'Approved' : 'Pending'}</td>
                    <td>{r.posted_by_name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ExceptionSection>
        </div>
      ) : null}
    </section>
  )
}
