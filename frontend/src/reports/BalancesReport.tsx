import { useEffect, useState } from 'react'
import type { ReportSectionShared } from './sectionTypes'
import { runReportJson, runReportXlsx } from './reportRunner'
import { formatMoneyPence } from './utils'

function BalancesReportColgroup() {
  return (
    <colgroup>
      <col className="reportsColRef" />
      <col className="reportsColClient" />
      <col className="reportsColMatter" />
      <col className="reportsColFeeEarner" />
      <col className="reportsColMoney" />
      <col className="reportsColMoney" />
    </colgroup>
  )
}

type Preview = {
  rows?: {
    case_id: string
    case_number: string
    client_name?: string | null
    matter_description: string
    fee_earner_name: string
    client_balance_pence: number
    office_balance_pence: number
  }[]
  totals?: { client_balance_pence: number; office_balance_pence: number }
} | null

export function useBalancesReport(active: boolean) {
  const [preview, setPreview] = useState<Preview>(null)
  useEffect(() => {
    if (!active) setPreview(null)
  }, [active])
  return { preview, setPreview }
}

export function BalancesReportBody({
  shared,
  preview,
  setPreview,
}: {
  shared: ReportSectionShared
  preview: Preview
  setPreview: (v: Preview) => void
}) {
  const body = shared.feeEarnerPayload
  return (
    <section className={`reportsSection${preview?.rows ? ' reportsSection--fill' : ''}`}>
      <p className="muted reportsSectionStatic">Excludes matters with status Closed or Archived. Balances use approved ledger entries only.</p>
      <div className="row reportsSectionStatic" style={{ gap: 8, marginTop: 10 }}>
        <button
          type="button"
          className="btn primary"
          disabled={shared.busy}
          onClick={() => void runReportJson(shared, '/reports/client-office-balances', body, setPreview)}
        >
          Run report
        </button>
        <button
          type="button"
          className="btn"
          disabled={shared.busy}
          onClick={() => void runReportXlsx(shared, '/reports/client-office-balances', body, 'canary-report-client-office-balances.xlsx')}
        >
          Export Excel
        </button>
      </div>
      {preview?.rows ? (
        <div className="reportsPreviewFrame">
          <div className="reportsPreviewScroll">
            <table className="reportsTable reportsTable--balances">
              <BalancesReportColgroup />
              <thead>
                <tr>
                  <th>Reference</th>
                  <th>Client</th>
                  <th>Matter</th>
                  <th>Fee earner</th>
                  <th>Client balance</th>
                  <th>Office balance</th>
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((r) => (
                  <tr key={r.case_id}>
                    <td>{r.case_number}</td>
                    <td>{r.client_name ?? ''}</td>
                    <td>{r.matter_description}</td>
                    <td>{r.fee_earner_name}</td>
                    <td>{formatMoneyPence(r.client_balance_pence)}</td>
                    <td>{formatMoneyPence(r.office_balance_pence)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {preview.totals ? (
            <div className="reportsPreviewTotalsRibbon" aria-label="Report totals">
              <table className="reportsTable reportsTable--balances">
                <BalancesReportColgroup />
                <tbody>
                  <tr className="reportsTableTotalRow">
                    <td colSpan={4}>
                      <strong>Total</strong>
                    </td>
                    <td>
                      <strong>{formatMoneyPence(preview.totals.client_balance_pence)}</strong>
                    </td>
                    <td>
                      <strong>{formatMoneyPence(preview.totals.office_balance_pence)}</strong>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
