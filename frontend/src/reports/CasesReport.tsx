import { useEffect, useMemo, useState } from 'react'
import type { CaseWorkflowStatus } from '../types'
import { scrollPanelClassName } from '../dropdownSizing'
import { FilterDropdown } from './FilterDropdown'
import { runReportJson, runReportXlsx } from './reportRunner'
import type { FilterChrome, ReportSectionShared } from './sectionTypes'
import { CASE_STATUS_OPTIONS } from './types'

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

export function useCasesReport(active: boolean) {
  const [caseStatusSel, setCaseStatusSel] = useState<Set<CaseWorkflowStatus>>(new Set())
  const [preview, setPreview] = useState<Preview>(null)
  useEffect(() => {
    if (!active) setPreview(null)
  }, [active])
  const body = useMemo(() => {
    const o: Record<string, unknown> = {}
    if (caseStatusSel.size > 0) o.statuses = Array.from(caseStatusSel)
    return o
  }, [caseStatusSel])
  const statusSummary = useMemo(() => {
    if (caseStatusSel.size === 0) return 'All statuses'
    const labels = CASE_STATUS_OPTIONS.filter((o) => caseStatusSel.has(o.value)).map((o) => o.label)
    return labels.length <= 2 ? labels.join(', ') : `${caseStatusSel.size} statuses`
  }, [caseStatusSel])
  function toggleCaseStatus(s: CaseWorkflowStatus) {
    setCaseStatusSel((prev) => {
      const next = new Set(prev)
      if (next.has(s)) next.delete(s)
      else next.add(s)
      return next
    })
  }
  return { caseStatusSel, setCaseStatusSel, preview, setPreview, body, statusSummary, toggleCaseStatus }
}

type State = ReturnType<typeof useCasesReport>

export function CasesReportFilters({ state, chrome }: { state: State; chrome: FilterChrome }) {
  return (
    <FilterDropdown
      id="caseStatus"
      label="Matter status"
      summary={state.statusSummary}
      openId={chrome.openFilterId}
      setOpenId={chrome.setOpenFilterId}
      footer={
        <button type="button" className="btn btn--small" onClick={() => state.setCaseStatusSel(new Set())}>
          Clear filters (all statuses)
        </button>
      }
    >
      <p className="muted" style={{ margin: '0 0 8px', fontSize: 12 }}>
        Leave none ticked to include every status.
      </p>
      <div className={scrollPanelClassName('reportsDdCheckList', CASE_STATUS_OPTIONS.length)}>
        {CASE_STATUS_OPTIONS.map(({ value, label }) => (
          <label key={value} className="reportsCheckbox">
            <input type="checkbox" checked={state.caseStatusSel.has(value)} onChange={() => state.toggleCaseStatus(value)} />
            <span>{label}</span>
          </label>
        ))}
      </div>
    </FilterDropdown>
  )
}

export function CasesReportBody({ shared, state }: { shared: ReportSectionShared; state: State }) {
  const body = { ...shared.feeEarnerPayload, ...state.body }
  return (
    <section className="reportsSection">
      <div className="row" style={{ gap: 8, marginTop: 10 }}>
        <button
          type="button"
          className="btn primary"
          disabled={shared.busy}
          onClick={() => void runReportJson(shared, '/reports/cases', body, state.setPreview)}
        >
          Run report
        </button>
        <button
          type="button"
          className="btn"
          disabled={shared.busy}
          onClick={() => void runReportXlsx(shared, '/reports/cases', body, 'canary-report-cases.xlsx')}
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
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {state.preview.rows.map((r) => (
                <tr key={r.case_id ?? r.case_number}>
                  <td>{r.case_number}</td>
                  <td>{r.client_name ?? ''}</td>
                  <td>{r.matter_description}</td>
                  <td>{r.status_label}</td>
                  <td>{r.fee_earner_name}</td>
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
