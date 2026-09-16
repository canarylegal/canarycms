import { useEffect, useMemo, useState } from 'react'
import { FilterDropdown } from './FilterDropdown'
import { runReportJson, runReportXlsx } from './reportRunner'
import type { FilterChrome, ReportSectionShared } from './sectionTypes'
import { dateRangeSummary, formatMoneyPence } from './utils'

type Preview = {
  rows?: {
    invoice_id?: string
    case_number: string
    client_name?: string | null
    invoice_number: string
    invoice_status_label?: string
    fee_earner_name: string
    created_at: string
    fees_ex_vat_pence: number
    vat_pence: number
    disbursements_ex_vat_pence: number
  }[]
  totals?: { fees_ex_vat_pence: number; vat_pence: number; disbursements_ex_vat_pence: number }
} | null

export function useBillingReport(active: boolean) {
  const [billingFrom, setBillingFrom] = useState('')
  const [billingTo, setBillingTo] = useState('')
  const [preview, setPreview] = useState<Preview>(null)
  useEffect(() => {
    if (!active) setPreview(null)
  }, [active])
  const body = useMemo(() => {
    const o: Record<string, unknown> = {}
    if (billingFrom.trim()) o.date_from = billingFrom.trim()
    if (billingTo.trim()) o.date_to = billingTo.trim()
    return o
  }, [billingFrom, billingTo])
  const dateSummary = useMemo(() => dateRangeSummary(billingFrom, billingTo), [billingFrom, billingTo])
  return { billingFrom, setBillingFrom, billingTo, setBillingTo, preview, setPreview, body, dateSummary }
}

type State = ReturnType<typeof useBillingReport>

export function BillingReportFilters({ state, chrome }: { state: State; chrome: FilterChrome }) {
  return (
    <FilterDropdown
      id="billingDates"
      label="Invoice date range"
      summary={state.dateSummary}
      openId={chrome.openFilterId}
      setOpenId={chrome.setOpenFilterId}
    >
      <div className="reportsDdDateFields">
        <label className="field">
          <span>From</span>
          <input type="date" value={state.billingFrom} onChange={(e) => state.setBillingFrom(e.target.value)} />
        </label>
        <label className="field">
          <span>To</span>
          <input type="date" value={state.billingTo} onChange={(e) => state.setBillingTo(e.target.value)} />
        </label>
        <p className="muted" style={{ margin: '4px 0 0', fontSize: 12 }}>
          Leave both empty for all time.
        </p>
      </div>
    </FilterDropdown>
  )
}

export function BillingReportBody({ shared, state }: { shared: ReportSectionShared; state: State }) {
  const body = { ...shared.feeEarnerPayload, ...state.body }
  return (
    <section className="reportsSection">
      <p className="muted" style={{ marginTop: 0 }}>
        Invoices with status pending approval or approved (voided excluded).
      </p>
      <div className="row" style={{ gap: 8, marginTop: 10 }}>
        <button
          type="button"
          className="btn primary"
          disabled={shared.busy}
          onClick={() => void runReportJson(shared, '/reports/billing', body, state.setPreview)}
        >
          Run report
        </button>
        <button
          type="button"
          className="btn"
          disabled={shared.busy}
          onClick={() => void runReportXlsx(shared, '/reports/billing', body, 'canary-report-billing.xlsx')}
        >
          Export Excel
        </button>
      </div>
      {state.preview?.rows ? (
        <div className="reportsPreviewScroll">
          <table className="reportsTable">
            <thead>
              <tr>
                <th>Reference</th>
                <th>Client</th>
                <th>Invoice</th>
                <th>Status</th>
                <th>Fee earner</th>
                <th>Created</th>
                <th>Fees ex VAT</th>
                <th>VAT</th>
                <th>Disbursements ex VAT</th>
              </tr>
            </thead>
            <tbody>
              {state.preview.rows.map((r) => (
                <tr key={r.invoice_id ?? `${r.invoice_number}-${r.created_at}`}>
                  <td>{r.case_number}</td>
                  <td>{r.client_name ?? ''}</td>
                  <td>{r.invoice_number}</td>
                  <td>{r.invoice_status_label ?? ''}</td>
                  <td>{r.fee_earner_name}</td>
                  <td>{r.created_at?.slice(0, 16)?.replace('T', ' ') ?? ''}</td>
                  <td>{formatMoneyPence(r.fees_ex_vat_pence)}</td>
                  <td>{formatMoneyPence(r.vat_pence)}</td>
                  <td>{formatMoneyPence(r.disbursements_ex_vat_pence)}</td>
                </tr>
              ))}
              {state.preview.totals ? (
                <tr className="reportsTableTotalRow">
                  <td colSpan={6}>
                    <strong>Total</strong>
                  </td>
                  <td>
                    <strong>{formatMoneyPence(state.preview.totals.fees_ex_vat_pence)}</strong>
                  </td>
                  <td>
                    <strong>{formatMoneyPence(state.preview.totals.vat_pence)}</strong>
                  </td>
                  <td>
                    <strong>{formatMoneyPence(state.preview.totals.disbursements_ex_vat_pence)}</strong>
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  )
}
