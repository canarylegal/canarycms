import { useEffect, useMemo, useState } from 'react'
import { scrollPanelClassName } from '../dropdownSizing'
import { FilterDropdown } from './FilterDropdown'
import { runReportJson, runReportXlsx } from './reportRunner'
import type { FilterChrome, ReportSectionShared } from './sectionTypes'

type Preview = {
  rows?: {
    case_id?: string
    case_number: string
    client_name?: string | null
    matter_description: string
    status_label: string
    fee_earner_name: string
    source_name?: string | null
    created_at: string
  }[]
} | null

export function useCasesOpenedReport(active: boolean) {
  const [openedFrom, setOpenedFrom] = useState('')
  const [openedTo, setOpenedTo] = useState('')
  const [openedQuote, setOpenedQuote] = useState(true)
  const [openedActive, setOpenedActive] = useState(true)
  const [preview, setPreview] = useState<Preview>(null)
  useEffect(() => {
    if (!active) setPreview(null)
  }, [active])
  const body = useMemo(
    () => ({
      date_from: openedFrom.trim(),
      date_to: openedTo.trim(),
      include_quote: openedQuote,
      include_active: openedActive,
    }),
    [openedFrom, openedTo, openedQuote, openedActive],
  )
  const dateSummary = useMemo(() => {
    const a = openedFrom.trim() || '…'
    const b = openedTo.trim() || '…'
    return `${a} → ${b}`
  }, [openedFrom, openedTo])
  const statusSummary = useMemo(() => {
    const bits: string[] = []
    if (openedQuote) bits.push('Quote')
    if (openedActive) bits.push('Active')
    if (!bits.length) return 'None'
    return bits.join(' + ')
  }, [openedQuote, openedActive])
  return {
    openedFrom,
    setOpenedFrom,
    openedTo,
    setOpenedTo,
    openedQuote,
    setOpenedQuote,
    openedActive,
    setOpenedActive,
    preview,
    setPreview,
    body,
    dateSummary,
    statusSummary,
  }
}

type State = ReturnType<typeof useCasesOpenedReport>

export function CasesOpenedReportFilters({ state, chrome }: { state: State; chrome: FilterChrome }) {
  return (
    <>
      <FilterDropdown
        id="openedDates"
        label="Opened date range"
        summary={state.dateSummary}
        openId={chrome.openFilterId}
        setOpenId={chrome.setOpenFilterId}
      >
        <div className="reportsDdDateFields">
          <label className="field">
            <span>From</span>
            <input type="date" value={state.openedFrom} onChange={(e) => state.setOpenedFrom(e.target.value)} />
          </label>
          <label className="field">
            <span>To</span>
            <input type="date" value={state.openedTo} onChange={(e) => state.setOpenedTo(e.target.value)} />
          </label>
        </div>
      </FilterDropdown>
      <FilterDropdown
        id="openedStatus"
        label="New file status"
        summary={state.statusSummary}
        openId={chrome.openFilterId}
        setOpenId={chrome.setOpenFilterId}
      >
        <div className={scrollPanelClassName('reportsDdCheckList', 2)}>
          <label className="reportsCheckbox">
            <input type="checkbox" checked={state.openedQuote} onChange={(e) => state.setOpenedQuote(e.target.checked)} />
            <span>Quote</span>
          </label>
          <label className="reportsCheckbox">
            <input type="checkbox" checked={state.openedActive} onChange={(e) => state.setOpenedActive(e.target.checked)} />
            <span>Active</span>
          </label>
        </div>
      </FilterDropdown>
    </>
  )
}

export function CasesOpenedReportBody({ shared, state }: { shared: ReportSectionShared; state: State }) {
  const body = { ...shared.feeEarnerPayload, ...state.body }
  return (
    <section className="reportsSection">
      <div className="row" style={{ gap: 8, marginTop: 10 }}>
        <button
          type="button"
          className="btn primary"
          disabled={shared.busy}
          onClick={() => {
            if (!state.openedFrom.trim() || !state.openedTo.trim()) {
              shared.setErr('Choose opened date range in the dropdown (from / to).')
              return
            }
            void runReportJson(shared, '/reports/cases-opened', body, state.setPreview)
          }}
        >
          Run report
        </button>
        <button
          type="button"
          className="btn"
          disabled={shared.busy}
          onClick={() => {
            if (!state.openedFrom.trim() || !state.openedTo.trim()) {
              shared.setErr('Choose opened date range in the dropdown (from / to).')
              return
            }
            void runReportXlsx(shared, '/reports/cases-opened', body, 'canary-report-cases-opened.xlsx')
          }}
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
                <th>Matter</th>
                <th>Status</th>
                <th>Fee earner</th>
                <th>Source</th>
                <th>Opened</th>
              </tr>
            </thead>
            <tbody>
              {state.preview.rows.map((r) => (
                <tr key={`${r.case_number}-${r.created_at}`}>
                  <td>{r.case_number}</td>
                  <td>{r.client_name ?? ''}</td>
                  <td>{r.matter_description}</td>
                  <td>{r.status_label}</td>
                  <td>{r.fee_earner_name}</td>
                  <td>{r.source_name ?? ''}</td>
                  <td>{r.created_at?.slice(0, 16)?.replace('T', ' ') ?? ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  )
}
