import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { apiFetch, apiUrl, applyAuthHeaders } from './api'
import type { ApiError } from './api'
import type { CalendarEventTemplatePickOut, CaseWorkflowStatus, UserPublic } from './types'

type ReportTab =
  | 'client_office_balances'
  | 'billing'
  | 'cases'
  | 'cases_opened'
  | 'events'

type FeeEarnerPick = { id: string; display_name: string; email: string }

const REPORT_OPTIONS: { value: ReportTab; label: string }[] = [
  { value: 'client_office_balances', label: 'Client & office balances' },
  { value: 'billing', label: 'Billing' },
  { value: 'cases', label: 'Cases' },
  { value: 'cases_opened', label: 'Cases opened' },
  { value: 'events', label: 'Events' },
]

const CASE_STATUS_OPTIONS: { value: CaseWorkflowStatus; label: string }[] = [
  { value: 'open', label: 'Active' },
  { value: 'quote', label: 'Quote' },
  { value: 'post_completion', label: 'Post-completion' },
  { value: 'closed', label: 'Closed' },
  { value: 'archived', label: 'Archived' },
]

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

function formatMoneyPence(p: number): string {
  const neg = p < 0
  const a = Math.abs(p)
  const s = (a / 100).toFixed(2)
  return `${neg ? '-' : ''}£${s}`
}

async function downloadReportXlsx(path: string, body: unknown, token: string, downloadFilename: string) {
  const headers = new Headers()
  applyAuthHeaders(headers, token.trim())
  headers.set('Content-Type', 'application/json')
  const res = await fetch(apiUrl(`${path}?format=xlsx`), { method: 'POST', headers, body: JSON.stringify(body) })
  if (!res.ok) {
    const raw = await res.json().catch(() => ({}))
    const msg = typeof (raw as { detail?: unknown }).detail === 'string' ? (raw as { detail: string }).detail : `Export failed (${res.status})`
    throw new Error(msg)
  }
  const blob = await res.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = downloadFilename
  a.click()
  URL.revokeObjectURL(a.href)
}

function feeEarnerSummary(selected: Set<string>, feeEarners: FeeEarnerPick[], lockedSingle: boolean): string {
  if (lockedSingle && feeEarners.length === 1) {
    const u = feeEarners[0]
    return u ? `${u.display_name}` : '—'
  }
  const n = selected.size
  if (n === 0) return 'None selected'
  if (n === feeEarners.length && feeEarners.length > 0) return `All (${n})`
  if (n === 1) {
    const id = Array.from(selected)[0]
    const u = feeEarners.find((x) => x.id === id)
    return u ? u.display_name : '1 selected'
  }
  return `${n} selected`
}

function FilterDropdown({
  id,
  label,
  summary,
  disabled,
  openId,
  setOpenId,
  children,
  footer,
}: {
  id: string
  label: string
  summary: string
  disabled?: boolean
  openId: string | null
  setOpenId: (v: string | null) => void
  children: ReactNode
  footer?: ReactNode
}) {
  const open = openId === id
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function onDoc(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpenId(null)
      }
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open, setOpenId])

  return (
    <div className="reportsDd" ref={wrapRef}>
      <button
        type="button"
        className="reportsDdTrigger"
        aria-expanded={open}
        aria-haspopup="dialog"
        disabled={disabled}
        onClick={() => setOpenId(open ? null : id)}
      >
        <span className="reportsDdTriggerLabel">{label}</span>
        <span className="reportsDdTriggerSummary">{summary}</span>
      </button>
      {open ? (
        <div className="reportsDdPanel" role="dialog" aria-label={label}>
          <div className="reportsDdPanelBody">{children}</div>
          {footer ? <div className="reportsDdPanelFooter">{footer}</div> : null}
        </div>
      ) : null}
    </div>
  )
}

export function ReportsPage({ token, me }: { token: string; me: UserPublic | null }) {
  const [tab, setTab] = useState<ReportTab>('client_office_balances')
  const [openFilterId, setOpenFilterId] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const [feeEarners, setFeeEarners] = useState<FeeEarnerPick[]>([])
  const [feeEarnerSelected, setFeeEarnerSelected] = useState<Set<string>>(new Set())

  const isAdmin = Boolean(me?.admin_console_access || me?.role === 'admin')
  const feeEarnerLocked = !isAdmin

  const [billingFrom, setBillingFrom] = useState('')
  const [billingTo, setBillingTo] = useState('')

  const [caseStatusSel, setCaseStatusSel] = useState<Set<CaseWorkflowStatus>>(new Set())

  const [openedFrom, setOpenedFrom] = useState('')
  const [openedTo, setOpenedTo] = useState('')
  const [openedQuote, setOpenedQuote] = useState(true)
  const [openedActive, setOpenedActive] = useState(true)

  const [evFrom, setEvFrom] = useState('')
  const [evTo, setEvTo] = useState('')
  const [evTemplates, setEvTemplates] = useState<CalendarEventTemplatePickOut[]>([])
  const [evTemplateSel, setEvTemplateSel] = useState<Set<string>>(new Set())

  const [previewJson, setPreviewJson] = useState<unknown>(null)

  const feeEarnerPayload = useMemo(() => {
    const ids = Array.from(feeEarnerSelected)
    return { fee_earner_user_ids: ids }
  }, [feeEarnerSelected])

  const loadFeeEarners = useCallback(async () => {
    setErr(null)
    try {
      const rows = await apiFetch<FeeEarnerPick[]>('/reports/fee-earners', { token })
      setFeeEarners(rows)
      if (!isAdmin && me?.id) {
        setFeeEarnerSelected(new Set([me.id]))
      } else if (isAdmin && rows.length) {
        setFeeEarnerSelected(new Set(rows.map((r) => r.id)))
      }
    } catch (e) {
      setFeeEarners([])
      setErr((e as ApiError)?.message ?? 'Could not load fee earners')
    }
  }, [token, isAdmin, me?.id])

  const loadEventTemplates = useCallback(async () => {
    try {
      const rows = await apiFetch<CalendarEventTemplatePickOut[]>('/users/me/calendar/event-line-templates', { token })
      setEvTemplates(rows)
    } catch {
      setEvTemplates([])
    }
  }, [token])

  useEffect(() => {
    void loadFeeEarners()
  }, [loadFeeEarners])

  useEffect(() => {
    void loadEventTemplates()
  }, [loadEventTemplates])

  function requireFeeEarners(): boolean {
    if (feeEarnerSelected.size === 0) {
      setErr('Select at least one fee earner.')
      return false
    }
    return true
  }

  async function runJson(path: string, body: object) {
    if (!requireFeeEarners()) return
    setBusy(true)
    setErr(null)
    setPreviewJson(null)
    setOpenFilterId(null)
    try {
      const data = await apiFetch<unknown>(`${path}?format=json`, { token, method: 'POST', json: body })
      setPreviewJson(data)
    } catch (e) {
      setErr((e as ApiError)?.message ?? 'Report failed')
    } finally {
      setBusy(false)
    }
  }

  async function runXlsx(path: string, body: object, filename: string) {
    if (!requireFeeEarners()) return
    setBusy(true)
    setErr(null)
    setOpenFilterId(null)
    try {
      await downloadReportXlsx(path, body, token, filename)
    } catch (e) {
      setErr((e as Error)?.message ?? 'Export failed')
    } finally {
      setBusy(false)
    }
  }

  const balancesBody = feeEarnerPayload

  const billingBody = useMemo(() => {
    const o: Record<string, unknown> = { ...feeEarnerPayload }
    if (billingFrom.trim()) o.date_from = billingFrom.trim()
    if (billingTo.trim()) o.date_to = billingTo.trim()
    return o
  }, [feeEarnerPayload, billingFrom, billingTo])

  const casesBody = useMemo(() => {
    const o: Record<string, unknown> = { ...feeEarnerPayload }
    if (caseStatusSel.size > 0) o.statuses = Array.from(caseStatusSel)
    return o
  }, [feeEarnerPayload, caseStatusSel])

  const openedBody = useMemo(() => {
    return {
      ...feeEarnerPayload,
      date_from: openedFrom.trim(),
      date_to: openedTo.trim(),
      include_quote: openedQuote,
      include_active: openedActive,
    }
  }, [feeEarnerPayload, openedFrom, openedTo, openedQuote, openedActive])

  const eventsBody = useMemo(() => {
    const o: Record<string, unknown> = { ...feeEarnerPayload }
    if (evFrom.trim()) o.date_from = evFrom.trim()
    if (evTo.trim()) o.date_to = evTo.trim()
    if (evTemplateSel.size > 0) o.template_ids = Array.from(evTemplateSel)
    return o
  }, [feeEarnerPayload, evFrom, evTo, evTemplateSel])

  function toggleCaseStatus(s: CaseWorkflowStatus) {
    setCaseStatusSel((prev) => {
      const next = new Set(prev)
      if (next.has(s)) next.delete(s)
      else next.add(s)
      return next
    })
  }

  function toggleEvTemplate(id: string) {
    setEvTemplateSel((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const feSummary = useMemo(
    () => feeEarnerSummary(feeEarnerSelected, feeEarners, feeEarnerLocked),
    [feeEarnerSelected, feeEarners, feeEarnerLocked],
  )

  const billingDateSummary = useMemo(() => {
    if (!billingFrom.trim() && !billingTo.trim()) return 'All dates'
    const a = billingFrom.trim() || '…'
    const b = billingTo.trim() || '…'
    return `${a} → ${b}`
  }, [billingFrom, billingTo])

  const caseStatusSummary = useMemo(() => {
    if (caseStatusSel.size === 0) return 'All statuses'
    const labels = CASE_STATUS_OPTIONS.filter((o) => caseStatusSel.has(o.value)).map((o) => o.label)
    return labels.length <= 2 ? labels.join(', ') : `${caseStatusSel.size} statuses`
  }, [caseStatusSel])

  const openedDateSummary = useMemo(() => {
    const a = openedFrom.trim() || '…'
    const b = openedTo.trim() || '…'
    return `${a} → ${b}`
  }, [openedFrom, openedTo])

  const openedStatusSummary = useMemo(() => {
    const bits: string[] = []
    if (openedQuote) bits.push('Quote')
    if (openedActive) bits.push('Active')
    if (!bits.length) return 'None'
    return bits.join(' + ')
  }, [openedQuote, openedActive])

  const evDateSummary = useMemo(() => {
    if (!evFrom.trim() && !evTo.trim()) return 'All dates'
    const a = evFrom.trim() || '…'
    const b = evTo.trim() || '…'
    return `${a} → ${b}`
  }, [evFrom, evTo])

  const evTemplateSummary = useMemo(() => {
    if (evTemplateSel.size === 0) return 'All templates'
    if (evTemplateSel.size === 1) {
      const id = Array.from(evTemplateSel)[0]
      const t = evTemplates.find((x) => x.id === id)
      return t?.name ?? '1 template'
    }
    return `${evTemplateSel.size} templates`
  }, [evTemplateSel, evTemplates])

  const allFeeIds = useMemo(() => feeEarners.map((u) => u.id), [feeEarners])

  const previewBalances = previewJson as {
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

  const previewBilling = previewJson as {
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

  const previewCases = previewJson as {
    rows?: {
      case_id?: string
      case_number: string
      client_name?: string | null
      matter_description: string
      status_label: string
      fee_earner_name: string
      created_at: string
    }[]
  } | null

  const previewEvents = previewJson as {
    rows?: {
      event_id?: string
      event_name: string
      event_date?: string | null
      event_category: string
      case_number: string
      matter_description: string
      fee_earner_name: string
    }[]
  } | null

  return (
    <div className="mainMenuShell mainMenuShell--mainMenu">
      <div className="card casesTableCard reportsPageShell">
        <div className="reportsPageHeader">
        <h1 className="reportsPageTitle">Reports</h1>
        <p className="muted reportsPageLead" style={{ marginBottom: 16 }}>
          Run firm reports by fee earner. Exports use the same Excel format as merge-code downloads.
          {!isAdmin ? ' You can only include matters where you are the fee earner.' : null}
        </p>

        {err ? <div className="error">{err}</div> : null}

        <div className="reportsToolbar">
          <label className="field reportsReportSelect">
            <span>Report</span>
            <select
              value={tab}
              onChange={(e) => {
                setTab(e.target.value as ReportTab)
                setPreviewJson(null)
                setOpenFilterId(null)
              }}
              aria-label="Choose report type"
            >
              {REPORT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>

          <div className="reportsFilterRow">
            <FilterDropdown
              id="fe"
              label="Fee earners"
              summary={feSummary}
              openId={openFilterId}
              setOpenId={setOpenFilterId}
              footer={
                isAdmin ? (
                  <div className="row" style={{ gap: 8 }}>
                    <button type="button" className="btn btn--small" onClick={() => setFeeEarnerSelected(new Set(allFeeIds))}>
                      All
                    </button>
                    <button type="button" className="btn btn--small" onClick={() => setFeeEarnerSelected(new Set())}>
                      Clear
                    </button>
                  </div>
                ) : undefined
              }
            >
              <div className="reportsDdCheckList">
                {feeEarners.map((u) => (
                  <label key={u.id} className="reportsCheckbox">
                    <input
                      type="checkbox"
                      checked={feeEarnerSelected.has(u.id)}
                      onChange={() => {
                        if (feeEarnerLocked) return
                        setFeeEarnerSelected((prev) => {
                          const next = new Set(prev)
                          if (next.has(u.id)) next.delete(u.id)
                          else next.add(u.id)
                          return next
                        })
                      }}
                      disabled={feeEarnerLocked}
                    />
                    <span>
                      {u.display_name}
                      <span className="muted" style={{ fontSize: 12 }}>
                        {' '}
                        ({u.email})
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            </FilterDropdown>

            {tab === 'billing' ? (
              <FilterDropdown
                id="billingDates"
                label="Invoice date range"
                summary={billingDateSummary}
                openId={openFilterId}
                setOpenId={setOpenFilterId}
              >
                <div className="reportsDdDateFields">
                  <label className="field">
                    <span>From</span>
                    <input type="date" value={billingFrom} onChange={(e) => setBillingFrom(e.target.value)} />
                  </label>
                  <label className="field">
                    <span>To</span>
                    <input type="date" value={billingTo} onChange={(e) => setBillingTo(e.target.value)} />
                  </label>
                  <p className="muted" style={{ margin: '4px 0 0', fontSize: 12 }}>
                    Leave both empty for all time.
                  </p>
                </div>
              </FilterDropdown>
            ) : null}

            {tab === 'cases' ? (
              <FilterDropdown
                id="caseStatus"
                label="Matter status"
                summary={caseStatusSummary}
                openId={openFilterId}
                setOpenId={setOpenFilterId}
                footer={
                  <button type="button" className="btn btn--small" onClick={() => setCaseStatusSel(new Set())}>
                    Clear filters (all statuses)
                  </button>
                }
              >
                <p className="muted" style={{ margin: '0 0 8px', fontSize: 12 }}>
                  Leave none ticked to include every status.
                </p>
                <div className="reportsDdCheckList">
                  {CASE_STATUS_OPTIONS.map(({ value, label }) => (
                    <label key={value} className="reportsCheckbox">
                      <input type="checkbox" checked={caseStatusSel.has(value)} onChange={() => toggleCaseStatus(value)} />
                      <span>{label}</span>
                    </label>
                  ))}
                </div>
              </FilterDropdown>
            ) : null}

            {tab === 'cases_opened' ? (
              <>
                <FilterDropdown
                  id="openedDates"
                  label="Opened date range"
                  summary={openedDateSummary}
                  openId={openFilterId}
                  setOpenId={setOpenFilterId}
                >
                  <div className="reportsDdDateFields">
                    <label className="field">
                      <span>From</span>
                      <input type="date" value={openedFrom} onChange={(e) => setOpenedFrom(e.target.value)} />
                    </label>
                    <label className="field">
                      <span>To</span>
                      <input type="date" value={openedTo} onChange={(e) => setOpenedTo(e.target.value)} />
                    </label>
                  </div>
                </FilterDropdown>
                <FilterDropdown
                  id="openedStatus"
                  label="New file status"
                  summary={openedStatusSummary}
                  openId={openFilterId}
                  setOpenId={setOpenFilterId}
                >
                  <div className="reportsDdCheckList">
                    <label className="reportsCheckbox">
                      <input type="checkbox" checked={openedQuote} onChange={(e) => setOpenedQuote(e.target.checked)} />
                      <span>Quote</span>
                    </label>
                    <label className="reportsCheckbox">
                      <input type="checkbox" checked={openedActive} onChange={(e) => setOpenedActive(e.target.checked)} />
                      <span>Active</span>
                    </label>
                  </div>
                </FilterDropdown>
              </>
            ) : null}

            {tab === 'events' ? (
              <>
                <FilterDropdown
                  id="evDates"
                  label="Event date range"
                  summary={evDateSummary}
                  openId={openFilterId}
                  setOpenId={setOpenFilterId}
                >
                  <div className="reportsDdDateFields">
                    <label className="field">
                      <span>From</span>
                      <input type="date" value={evFrom} onChange={(e) => setEvFrom(e.target.value)} />
                    </label>
                    <label className="field">
                      <span>To</span>
                      <input type="date" value={evTo} onChange={(e) => setEvTo(e.target.value)} />
                    </label>
                    <p className="muted" style={{ margin: '4px 0 0', fontSize: 12 }}>
                      Leave both empty to ignore event date.
                    </p>
                  </div>
                </FilterDropdown>
                <FilterDropdown
                  id="evTpl"
                  label="Calendar template"
                  summary={evTemplateSummary}
                  openId={openFilterId}
                  setOpenId={setOpenFilterId}
                  footer={
                    <button type="button" className="btn btn--small" onClick={() => setEvTemplateSel(new Set())}>
                      Clear (all templates)
                    </button>
                  }
                >
                  <p className="muted" style={{ margin: '0 0 8px', fontSize: 12 }}>
                    Admin → Sub-menus → Events. Leave none ticked for all templates.
                  </p>
                  <div className="reportsDdCheckList reportsDdCheckList--tall">
                    {evTemplates.map((t) => (
                      <label key={t.id} className="reportsCheckbox">
                        <input type="checkbox" checked={evTemplateSel.has(t.id)} onChange={() => toggleEvTemplate(t.id)} />
                        <span>
                          {t.name}
                          <span className="muted" style={{ fontSize: 12 }}>
                            {' '}
                            — {t.matter_sub_type_name}
                          </span>
                        </span>
                      </label>
                    ))}
                  </div>
                </FilterDropdown>
              </>
            ) : null}
          </div>
        </div>
        </div>

        <div className="reportsPageBody">

        {tab === 'client_office_balances' ? (
          <section className={`reportsSection${previewBalances?.rows ? ' reportsSection--fill' : ''}`}>
            <p className="muted reportsSectionStatic">Excludes matters with status Closed or Archived. Balances use approved ledger entries only.</p>
            <div className="row reportsSectionStatic" style={{ gap: 8, marginTop: 10 }}>
              <button type="button" className="btn primary" disabled={busy} onClick={() => void runJson('/reports/client-office-balances', balancesBody)}>
                Run report
              </button>
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => void runXlsx('/reports/client-office-balances', balancesBody, 'canary-report-client-office-balances.xlsx')}
              >
                Export Excel
              </button>
            </div>
            {previewBalances?.rows ? (
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
                      {previewBalances.rows.map((r) => (
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
                {previewBalances.totals ? (
                  <div className="reportsPreviewTotalsRibbon" aria-label="Report totals">
                    <table className="reportsTable reportsTable--balances">
                      <BalancesReportColgroup />
                      <tbody>
                        <tr className="reportsTableTotalRow">
                          <td colSpan={4}>
                            <strong>Total</strong>
                          </td>
                          <td>
                            <strong>{formatMoneyPence(previewBalances.totals.client_balance_pence)}</strong>
                          </td>
                          <td>
                            <strong>{formatMoneyPence(previewBalances.totals.office_balance_pence)}</strong>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                ) : null}
              </div>
            ) : null}
          </section>
        ) : null}

        {tab === 'billing' ? (
          <section className="reportsSection">
            <p className="muted" style={{ marginTop: 0 }}>
              Invoices with status pending approval or approved (voided excluded).
            </p>
            <div className="row" style={{ gap: 8, marginTop: 10 }}>
              <button type="button" className="btn primary" disabled={busy} onClick={() => void runJson('/reports/billing', billingBody)}>
                Run report
              </button>
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => void runXlsx('/reports/billing', billingBody, 'canary-report-billing.xlsx')}
              >
                Export Excel
              </button>
            </div>
            {previewBilling?.rows ? (
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
                    {previewBilling.rows.map((r) => (
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
                    {previewBilling.totals ? (
                      <tr className="reportsTableTotalRow">
                        <td colSpan={6}>
                          <strong>Total</strong>
                        </td>
                        <td>
                          <strong>{formatMoneyPence(previewBilling.totals.fees_ex_vat_pence)}</strong>
                        </td>
                        <td>
                          <strong>{formatMoneyPence(previewBilling.totals.vat_pence)}</strong>
                        </td>
                        <td>
                          <strong>{formatMoneyPence(previewBilling.totals.disbursements_ex_vat_pence)}</strong>
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            ) : null}
          </section>
        ) : null}

        {tab === 'cases' ? (
          <section className="reportsSection">
            <div className="row" style={{ gap: 8, marginTop: 10 }}>
              <button type="button" className="btn primary" disabled={busy} onClick={() => void runJson('/reports/cases', casesBody)}>
                Run report
              </button>
              <button type="button" className="btn" disabled={busy} onClick={() => void runXlsx('/reports/cases', casesBody, 'canary-report-cases.xlsx')}>
                Export Excel
              </button>
            </div>
            {previewCases?.rows ? (
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
                    {previewCases.rows.map((r) => (
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
        ) : null}

        {tab === 'cases_opened' ? (
          <section className="reportsSection">
            <div className="row" style={{ gap: 8, marginTop: 10 }}>
              <button
                type="button"
                className="btn primary"
                disabled={busy}
                onClick={() => {
                  if (!openedFrom.trim() || !openedTo.trim()) {
                    setErr('Choose opened date range in the dropdown (from / to).')
                    return
                  }
                  void runJson('/reports/cases-opened', openedBody)
                }}
              >
                Run report
              </button>
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => {
                  if (!openedFrom.trim() || !openedTo.trim()) {
                    setErr('Choose opened date range in the dropdown (from / to).')
                    return
                  }
                  void runXlsx('/reports/cases-opened', openedBody, 'canary-report-cases-opened.xlsx')
                }}
              >
                Export Excel
              </button>
            </div>
            {previewCases?.rows ? (
              <div className="reportsPreviewScroll">
                <table className="reportsTable">
                  <thead>
                    <tr>
                      <th>Reference</th>
                      <th>Client</th>
                      <th>Matter</th>
                      <th>Status</th>
                      <th>Fee earner</th>
                      <th>Opened</th>
                    </tr>
                  </thead>
                  <tbody>
                    {previewCases.rows.map((r) => (
                      <tr key={`${r.case_number}-${r.created_at}`}>
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
        ) : null}

        {tab === 'events' ? (
          <section className="reportsSection">
            <div className="row" style={{ gap: 8, marginTop: 10 }}>
              <button type="button" className="btn primary" disabled={busy} onClick={() => void runJson('/reports/events', eventsBody)}>
                Run report
              </button>
              <button type="button" className="btn" disabled={busy} onClick={() => void runXlsx('/reports/events', eventsBody, 'canary-report-events.xlsx')}>
                Export Excel
              </button>
            </div>
            {previewEvents?.rows ? (
              <div className="reportsPreviewScroll">
                <table className="reportsTable">
                  <thead>
                    <tr>
                      <th>Event</th>
                      <th>Date</th>
                      <th>Template</th>
                      <th>Reference</th>
                      <th>Matter</th>
                      <th>Fee earner</th>
                    </tr>
                  </thead>
                  <tbody>
                    {previewEvents.rows.map((r) => (
                      <tr key={r.event_id ?? `${r.case_number}-${r.event_name}-${r.event_date ?? ''}`}>
                        <td>{r.event_name}</td>
                        <td>{r.event_date ?? ''}</td>
                        <td>{r.event_category ?? ''}</td>
                        <td>{r.case_number}</td>
                        <td>{r.matter_description}</td>
                        <td>{r.fee_earner_name}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </section>
        ) : null}
        </div>
      </div>
    </div>
  )
}
