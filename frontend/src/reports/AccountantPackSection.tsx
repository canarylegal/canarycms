import { useEffect, useMemo, useState } from 'react'
import { apiFetch, apiUrl, applyAuthHeaders, type ApiError } from '../api'
import type { AccountantPackPreviewOut } from '../types'
import { FilterDropdown } from './FilterDropdown'
import type { FilterChrome, ReportSectionShared } from './sectionTypes'
import { activityRangeForPeriodEnd, defaultPeriodEndDate } from './utils'

export function useAccountantPackSection(active: boolean) {
  const [packPeriodEnd, setPackPeriodEnd] = useState(defaultPeriodEndDate)
  const [packActivityFrom, setPackActivityFrom] = useState(() => activityRangeForPeriodEnd(defaultPeriodEndDate()).from)
  const [packActivityTo, setPackActivityTo] = useState(() => activityRangeForPeriodEnd(defaultPeriodEndDate()).to)
  const [packIncludeBalances, setPackIncludeBalances] = useState(true)
  const [packIncludeBilling, setPackIncludeBilling] = useState(true)
  const [packIncludeLedger, setPackIncludeLedger] = useState(true)
  const [packIncludeAgedDebt, setPackIncludeAgedDebt] = useState(true)
  const [packIncludeExceptions, setPackIncludeExceptions] = useState(false)
  const [packIncludeReconcileDoc, setPackIncludeReconcileDoc] = useState(true)
  const [packPreview, setPackPreview] = useState<AccountantPackPreviewOut | null>(null)

  useEffect(() => {
    if (!active) setPackPreview(null)
  }, [active])

  const packBodyExtra = useMemo(() => {
    const o: Record<string, unknown> = {
      period_end_date: packPeriodEnd.trim(),
      include_balances: packIncludeBalances,
      include_billing: packIncludeBilling,
      include_ledger_activity: packIncludeLedger,
      include_aged_debt: packIncludeAgedDebt,
      include_exceptions: packIncludeExceptions,
      include_reconcile_doc: packIncludeReconcileDoc,
    }
    if (packActivityFrom.trim()) o.date_from = packActivityFrom.trim()
    if (packActivityTo.trim()) o.date_to = packActivityTo.trim()
    return o
  }, [
    packPeriodEnd,
    packActivityFrom,
    packActivityTo,
    packIncludeBalances,
    packIncludeBilling,
    packIncludeLedger,
    packIncludeAgedDebt,
    packIncludeExceptions,
    packIncludeReconcileDoc,
  ])

  const packPeriodSummary = useMemo(() => packPeriodEnd.trim() || 'Not set', [packPeriodEnd])
  const packActivitySummary = useMemo(() => {
    if (!packActivityFrom.trim() && !packActivityTo.trim()) return 'Same as period end month'
    const a = packActivityFrom.trim() || '…'
    const b = packActivityTo.trim() || '…'
    return `${a} → ${b}`
  }, [packActivityFrom, packActivityTo])

  function onPackPeriodEndChange(value: string) {
    setPackPeriodEnd(value)
    const range = activityRangeForPeriodEnd(value)
    setPackActivityFrom(range.from)
    setPackActivityTo(range.to)
    setPackPreview(null)
  }

  return {
    packPeriodEnd,
    packActivityFrom,
    setPackActivityFrom,
    packActivityTo,
    setPackActivityTo,
    packIncludeBalances,
    setPackIncludeBalances,
    packIncludeBilling,
    setPackIncludeBilling,
    packIncludeLedger,
    setPackIncludeLedger,
    packIncludeAgedDebt,
    setPackIncludeAgedDebt,
    packIncludeExceptions,
    setPackIncludeExceptions,
    packIncludeReconcileDoc,
    setPackIncludeReconcileDoc,
    packPreview,
    setPackPreview,
    packBodyExtra,
    packPeriodSummary,
    packActivitySummary,
    onPackPeriodEndChange,
  }
}

type State = ReturnType<typeof useAccountantPackSection>

export function AccountantPackFilters({ state, chrome }: { state: State; chrome: FilterChrome }) {
  return (
    <>
      <FilterDropdown
        id="packPeriodEnd"
        label="Period end date"
        summary={state.packPeriodSummary}
        openId={chrome.openFilterId}
        setOpenId={chrome.setOpenFilterId}
      >
        <div className="reportsDdDateFields">
          <label className="field">
            <span>Period end</span>
            <input type="date" value={state.packPeriodEnd} onChange={(e) => state.onPackPeriodEndChange(e.target.value)} />
          </label>
          <p className="muted" style={{ margin: '4px 0 0', fontSize: 12 }}>
            Balances and aged debt are as at this date.
          </p>
        </div>
      </FilterDropdown>
      <FilterDropdown
        id="packActivityDates"
        label="Activity date range"
        summary={state.packActivitySummary}
        openId={chrome.openFilterId}
        setOpenId={chrome.setOpenFilterId}
      >
        <div className="reportsDdDateFields">
          <label className="field">
            <span>From</span>
            <input
              type="date"
              value={state.packActivityFrom}
              onChange={(e) => {
                state.setPackActivityFrom(e.target.value)
                state.setPackPreview(null)
              }}
            />
          </label>
          <label className="field">
            <span>To</span>
            <input
              type="date"
              value={state.packActivityTo}
              onChange={(e) => {
                state.setPackActivityTo(e.target.value)
                state.setPackPreview(null)
              }}
            />
          </label>
          <p className="muted" style={{ margin: '4px 0 0', fontSize: 12 }}>
            Billing and ledger activity within this range (defaults to period month).
          </p>
        </div>
      </FilterDropdown>
    </>
  )
}

export function AccountantPackBody({ shared, state }: { shared: ReportSectionShared; state: State }) {
  const packBody = { ...shared.feeEarnerPayload, ...state.packBodyExtra }

  async function loadPackPreview() {
    if (!shared.requireFeeEarners()) return
    if (!state.packPeriodEnd.trim()) {
      shared.setErr('Choose a period end date.')
      return
    }
    shared.setBusy(true)
    shared.setErr(null)
    try {
      const data = await apiFetch<AccountantPackPreviewOut>('/reports/accountant-pack/preview', {
        token: shared.token,
        method: 'POST',
        json: packBody,
      })
      state.setPackPreview(data)
    } catch (e) {
      state.setPackPreview(null)
      shared.setErr((e as ApiError)?.message ?? 'Preview failed')
    } finally {
      shared.setBusy(false)
    }
  }

  async function downloadAccountantPack() {
    if (!shared.requireFeeEarners()) return
    if (!state.packPeriodEnd.trim()) {
      shared.setErr('Choose a period end date.')
      return
    }
    if (
      !state.packIncludeBalances &&
      !state.packIncludeBilling &&
      !state.packIncludeLedger &&
      !state.packIncludeAgedDebt &&
      !state.packIncludeExceptions &&
      !state.packIncludeReconcileDoc
    ) {
      shared.setErr('Select at least one section to include.')
      return
    }
    shared.setBusy(true)
    shared.setErr(null)
    try {
      const headers = new Headers()
      applyAuthHeaders(headers, shared.token.trim())
      headers.set('Content-Type', 'application/json')
      const res = await fetch(apiUrl('/reports/accountant-pack'), {
        method: 'POST',
        headers,
        body: JSON.stringify(packBody),
      })
      if (!res.ok) {
        const raw = await res.json().catch(() => ({}))
        const msg =
          typeof (raw as { detail?: unknown }).detail === 'string'
            ? (raw as { detail: string }).detail
            : `Download failed (${res.status})`
        throw new Error(msg)
      }
      const blob = await res.blob()
      const period = state.packPeriodEnd.trim().slice(0, 7)
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `canary-accountant-pack-${period}.zip`
      a.click()
      URL.revokeObjectURL(a.href)
    } catch (e) {
      shared.setErr((e as Error)?.message ?? 'Download failed')
    } finally {
      shared.setBusy(false)
    }
  }

  return (
    <section className="reportsSection">
      <p className="muted" style={{ marginTop: 0 }}>
        Download a ZIP containing a multi-sheet Excel workbook plus the approved client account reconcile report
        (Word) for the period end date. Ledger activity is exported on separate client and office worksheets.
        Run month-end reconcile first if you need the Word document included.
      </p>
      <div className="card" style={{ padding: 16, marginTop: 12 }}>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Include in pack</div>
        <div className="reportsDdCheckList" style={{ marginBottom: 16 }}>
          <label className="reportsCheckbox">
            <input
              type="checkbox"
              checked={state.packIncludeBalances}
              onChange={(e) => {
                state.setPackIncludeBalances(e.target.checked)
                state.setPackPreview(null)
              }}
            />
            <span>Client &amp; office balances</span>
          </label>
          <label className="reportsCheckbox">
            <input
              type="checkbox"
              checked={state.packIncludeBilling}
              onChange={(e) => {
                state.setPackIncludeBilling(e.target.checked)
                state.setPackPreview(null)
              }}
            />
            <span>Billing</span>
          </label>
          <label className="reportsCheckbox">
            <input
              type="checkbox"
              checked={state.packIncludeLedger}
              onChange={(e) => {
                state.setPackIncludeLedger(e.target.checked)
                state.setPackPreview(null)
              }}
            />
            <span>Client &amp; office ledger activity</span>
          </label>
          <label className="reportsCheckbox">
            <input
              type="checkbox"
              checked={state.packIncludeAgedDebt}
              onChange={(e) => {
                state.setPackIncludeAgedDebt(e.target.checked)
                state.setPackPreview(null)
              }}
            />
            <span>Aged debt</span>
          </label>
          <label className="reportsCheckbox">
            <input
              type="checkbox"
              checked={state.packIncludeExceptions}
              onChange={(e) => {
                state.setPackIncludeExceptions(e.target.checked)
                state.setPackPreview(null)
              }}
            />
            <span>Exceptions</span>
          </label>
          <label className="reportsCheckbox">
            <input
              type="checkbox"
              checked={state.packIncludeReconcileDoc}
              onChange={(e) => {
                state.setPackIncludeReconcileDoc(e.target.checked)
                state.setPackPreview(null)
              }}
            />
            <span>Client account reconcile report (Word)</span>
          </label>
        </div>
        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
          <button type="button" className="btn" disabled={shared.busy} onClick={() => void loadPackPreview()}>
            Refresh preview
          </button>
          <button type="button" className="btn primary" disabled={shared.busy} onClick={() => void downloadAccountantPack()}>
            Download export pack
          </button>
        </div>
      </div>
      {state.packPreview ? (
        <div className="reportsPreviewScroll" style={{ marginTop: 16 }}>
          <h3 style={{ margin: '0 0 8px', fontSize: 15 }}>Pack preview</h3>
          <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
            Activity: {state.packPreview.activity_date_from} → {state.packPreview.activity_date_to} · Fee earners:{' '}
            {state.packPreview.fee_earner_count}
          </p>
          <table className="reportsTable">
            <thead>
              <tr>
                <th>Section</th>
                <th>Rows</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody>
              {state.packPreview.sections.map((s) => (
                <tr key={s.key}>
                  <td>{s.label}</td>
                  <td>{s.row_count ?? (s.key === 'reconcile_doc' ? '—' : '0')}</td>
                  <td className="muted">{s.note ?? ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted" style={{ marginTop: 16 }}>
          Choose filters above, then click Refresh preview to see row counts before downloading.
        </p>
      )}
    </section>
  )
}
