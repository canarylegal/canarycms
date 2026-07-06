import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { apiFetch, apiUrl, applyAuthHeaders } from './api'
import { dropdownMenuClassName, scrollPanelClassName } from './dropdownSizing'
import { useDismissOnOutsidePointer } from './useDismissOnOutsidePointer'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import type { ApiError } from './api'
import {
  userCanAccessAdminConsole,
  type CalendarEventTemplatePickOut,
  type CaseWorkflowStatus,
  type ClientAccountReconciliationOut,
  type AccountantPackPreviewOut,
  type ReconciliationPreviewOut,
  type UserPublic,
} from './types'

type ReportTab =
  | 'client_office_balances'
  | 'billing'
  | 'time_recorded'
  | 'wip'
  | 'aged_debt'
  | 'exceptions'
  | 'client_account_reconcile'
  | 'accountant_pack'
  | 'cases'
  | 'cases_opened'
  | 'events'
  | 'ledger_activity'

type FeeEarnerPick = { id: string; display_name: string; email: string }

const REPORT_OPTIONS: { value: ReportTab; label: string }[] = [
  { value: 'client_office_balances', label: 'Client & office balances' },
  { value: 'billing', label: 'Billing' },
  { value: 'time_recorded', label: 'Time recorded' },
  { value: 'wip', label: 'WIP (unbilled time)' },
  { value: 'aged_debt', label: 'Aged debt' },
  { value: 'exceptions', label: 'Exceptions' },
  { value: 'client_account_reconcile', label: 'Client account reconcile' },
  { value: 'accountant_pack', label: 'Accountant export pack' },
  { value: 'ledger_activity', label: 'Ledger activity' },
  { value: 'cases', label: 'Cases' },
  { value: 'cases_opened', label: 'Cases opened' },
  { value: 'events', label: 'Events' },
]

const AGED_DEBT_BUCKETS = ['0-30', '31-60', '61-90', '90+'] as const

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

function defaultPeriodEndDate(): string {
  const d = new Date()
  d.setDate(0)
  return d.toISOString().slice(0, 10)
}

function parsePoundsToPence(input: string): number | null {
  const pounds = parseFloat(input.replace(/,/g, '').trim())
  if (!Number.isFinite(pounds)) return null
  return Math.round(pounds * 100)
}

function penceToPoundsInput(pence: number): string {
  return (pence / 100).toFixed(2)
}

function activityRangeForPeriodEnd(periodEnd: string): { from: string; to: string } {
  if (!periodEnd.trim()) return { from: '', to: '' }
  const d = new Date(`${periodEnd.trim()}T12:00:00`)
  if (Number.isNaN(d.getTime())) return { from: '', to: '' }
  const from = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
  return { from, to: periodEnd.trim() }
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
  fitContentItemCount,
}: {
  id: string
  label: string
  summary: string
  disabled?: boolean
  openId: string | null
  setOpenId: (v: string | null) => void
  children: ReactNode
  footer?: ReactNode
  /** When the panel body is a simple list, pass its length for smart no-scroll sizing. */
  fitContentItemCount?: number
}) {
  const open = openId === id
  const wrapRef = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const [panelPos, setPanelPos] = useState<{ top: number; left: number; width: number } | null>(null)
  const close = useCallback(() => setOpenId(null), [setOpenId])

  const containsTarget = useCallback(
    (target: Node) => Boolean(wrapRef.current?.contains(target) || panelRef.current?.contains(target)),
    [],
  )

  useDismissOnOutsidePointer(open, containsTarget, close)

  const updatePanelPos = useCallback(() => {
    const el = wrapRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    setPanelPos({
      top: rect.bottom + 4,
      left: rect.left,
      width: Math.max(rect.width, 260),
    })
  }, [])

  useLayoutEffect(() => {
    if (!open) {
      setPanelPos(null)
      return
    }
    updatePanelPos()
    window.addEventListener('resize', updatePanelPos)
    window.addEventListener('scroll', updatePanelPos, true)
    return () => {
      window.removeEventListener('resize', updatePanelPos)
      window.removeEventListener('scroll', updatePanelPos, true)
    }
  }, [open, updatePanelPos])

  const panel =
    open && panelPos ? (
      <div
        ref={panelRef}
        className="reportsDdPanel reportsDdPanel--portal"
        role="dialog"
        aria-label={label}
        style={{
          position: 'fixed',
          top: panelPos.top,
          left: panelPos.left,
          width: panelPos.width,
        }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div
          className={dropdownMenuClassName(
            'reportsDdPanelBody',
            fitContentItemCount ?? Number.POSITIVE_INFINITY,
          )}
        >
          {children}
        </div>
        {footer ? <div className="reportsDdPanelFooter">{footer}</div> : null}
      </div>
    ) : null

  return (
    <div className="reportsDd" ref={wrapRef}>
      <button
        type="button"
        className="reportsDdTrigger"
        aria-expanded={open}
        aria-haspopup="dialog"
        disabled={disabled}
        onMouseDown={(e) => {
          if (disabled) return
          e.preventDefault()
          e.stopPropagation()
          setOpenId(open ? null : id)
        }}
      >
        <span className="reportsDdTriggerLabel">{label}</span>
        <span className="reportsDdTriggerSummary">{summary}</span>
      </button>
      {panel ? createPortal(panel, document.body) : null}
    </div>
  )
}

export function ReportsPage({
  token,
  me,
  initialTab,
  onInitialTabConsumed,
}: {
  token: string
  me: UserPublic | null
  initialTab?: ReportTab
  onInitialTabConsumed?: () => void
}) {
  const [tab, setTab] = useState<ReportTab>(initialTab ?? 'client_office_balances')
  useEffect(() => {
    if (!initialTab) return
    setTab(initialTab)
    onInitialTabConsumed?.()
  }, [initialTab, onInitialTabConsumed])

  const [openFilterId, setOpenFilterId] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const [feeEarners, setFeeEarners] = useState<FeeEarnerPick[]>([])
  const [feeEarnerSelected, setFeeEarnerSelected] = useState<Set<string>>(new Set())

  const isAdmin = userCanAccessAdminConsole(me)
  const feeEarnerLocked = !isAdmin

  const [billingFrom, setBillingFrom] = useState('')
  const [billingTo, setBillingTo] = useState('')
  const [timeRecordedFrom, setTimeRecordedFrom] = useState('')
  const [timeRecordedTo, setTimeRecordedTo] = useState('')
  const [wipAsOf, setWipAsOf] = useState('')

  const [caseStatusSel, setCaseStatusSel] = useState<Set<CaseWorkflowStatus>>(new Set())

  const [openedFrom, setOpenedFrom] = useState('')
  const [openedTo, setOpenedTo] = useState('')
  const [openedQuote, setOpenedQuote] = useState(true)
  const [openedActive, setOpenedActive] = useState(true)

  const [evFrom, setEvFrom] = useState('')
  const [evTo, setEvTo] = useState('')
  const [evTemplates, setEvTemplates] = useState<CalendarEventTemplatePickOut[]>([])
  const [evTemplateSel, setEvTemplateSel] = useState<Set<string>>(new Set())

  const [ledgerFrom, setLedgerFrom] = useState('')
  const [ledgerTo, setLedgerTo] = useState('')
  const [ledgerApprovedOnly, setLedgerApprovedOnly] = useState(false)

  const [agedDebtAsOf, setAgedDebtAsOf] = useState('')

  const [excFrom, setExcFrom] = useState('')
  const [excTo, setExcTo] = useState('')
  const [excLargeMinPounds, setExcLargeMinPounds] = useState('5000')

  const [recPeriodEnd, setRecPeriodEnd] = useState(defaultPeriodEndDate)
  const [recBankPounds, setRecBankPounds] = useState('')
  const [recNotes, setRecNotes] = useState('')
  const [recPreview, setRecPreview] = useState<ReconciliationPreviewOut | null>(null)
  const [recRows, setRecRows] = useState<ClientAccountReconciliationOut[]>([])
  const [recSelectedId, setRecSelectedId] = useState<string | null>(null)
  const [recCanApprove, setRecCanApprove] = useState(false)
  const [recSavedMsg, setRecSavedMsg] = useState<string | null>(null)

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

  const loadReconciliationData = useCallback(async () => {
    setErr(null)
    setRecSavedMsg(null)
    try {
      const [preview, rows, perms] = await Promise.all([
        apiFetch<ReconciliationPreviewOut>('/reports/reconciliations/preview-totals', { token }),
        apiFetch<ClientAccountReconciliationOut[]>('/reports/reconciliations', { token }),
        apiFetch<{ can_approve_reconciliation: boolean }>('/reports/reconciliations/permissions', { token }),
      ])
      setRecPreview(preview)
      setRecRows(rows)
      setRecCanApprove(Boolean(perms.can_approve_reconciliation))
    } catch (e) {
      setRecPreview(null)
      setRecRows([])
      setErr((e as ApiError)?.message ?? 'Could not load reconciliation data')
    }
  }, [token])

  useEffect(() => {
    if (tab !== 'client_account_reconcile') return
    void loadReconciliationData()
  }, [tab, loadReconciliationData])

  useEffect(() => {
    if (tab !== 'accountant_pack') return
    setPackPreview(null)
  }, [tab])

  const recSelected = useMemo(
    () => (recSelectedId ? recRows.find((r) => r.id === recSelectedId) ?? null : null),
    [recRows, recSelectedId],
  )

  const recDraftDifference = useMemo(() => {
    const bank = parsePoundsToPence(recBankPounds)
    if (bank === null || !recPreview) return null
    return bank - recPreview.ledger_client_total_pence
  }, [recBankPounds, recPreview])

  function selectReconciliation(row: ClientAccountReconciliationOut) {
    setRecSelectedId(row.id)
    setRecPeriodEnd(row.period_end_date)
    setRecBankPounds(penceToPoundsInput(row.bank_statement_balance_pence))
    setRecNotes(row.notes ?? '')
    setRecSavedMsg(null)
  }

  function clearReconciliationSelection() {
    setRecSelectedId(null)
    setRecPeriodEnd(defaultPeriodEndDate())
    setRecBankPounds('')
    setRecNotes('')
    setRecSavedMsg(null)
  }

  async function saveReconciliationDraft() {
    const bankPence = parsePoundsToPence(recBankPounds)
    if (!recPeriodEnd.trim()) {
      setErr('Choose a period end date.')
      return
    }
    if (bankPence === null) {
      setErr('Enter the bank statement closing balance.')
      return
    }
    setBusy(true)
    setErr(null)
    setRecSavedMsg(null)
    try {
      let row: ClientAccountReconciliationOut
      if (recSelected?.status === 'draft') {
        row = await apiFetch<ClientAccountReconciliationOut>(`/reports/reconciliations/${recSelected.id}`, {
          token,
          method: 'PATCH',
          json: {
            bank_statement_balance_pence: bankPence,
            notes: recNotes.trim() || null,
            refresh_ledger_totals: true,
          },
        })
      } else if (recSelected?.status === 'approved') {
        setErr('This reconciliation is approved and cannot be changed.')
        return
      } else {
        row = await apiFetch<ClientAccountReconciliationOut>('/reports/reconciliations', {
          token,
          method: 'POST',
          json: {
            period_end_date: recPeriodEnd.trim(),
            bank_statement_balance_pence: bankPence,
            notes: recNotes.trim() || null,
          },
        })
      }
      setRecSelectedId(row.id)
      setRecSavedMsg('Draft saved.')
      await loadReconciliationData()
      const refreshed = await apiFetch<ClientAccountReconciliationOut[]>('/reports/reconciliations', { token })
      setRecRows(refreshed)
      const updated = refreshed.find((r) => r.id === row.id)
      if (updated) selectReconciliation(updated)
    } catch (e) {
      setErr((e as ApiError)?.message ?? 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  async function approveReconciliation() {
    if (!recSelected || recSelected.status !== 'draft') {
      setErr('Save a draft reconciliation first.')
      return
    }
    const bankPence = parsePoundsToPence(recBankPounds)
    if (bankPence === null) {
      setErr('Enter the bank statement closing balance.')
      return
    }
    const diff = bankPence - (recPreview?.ledger_client_total_pence ?? recSelected.ledger_client_total_pence)
    if (diff !== 0 && !recNotes.trim()) {
      setErr('Enter notes explaining the difference before approving.')
      return
    }
    setBusy(true)
    setErr(null)
    setRecSavedMsg(null)
    try {
      await apiFetch<ClientAccountReconciliationOut>(`/reports/reconciliations/${recSelected.id}`, {
        token,
        method: 'PATCH',
        json: {
          bank_statement_balance_pence: bankPence,
          notes: recNotes.trim() || null,
          refresh_ledger_totals: true,
        },
      })
      const row = await apiFetch<ClientAccountReconciliationOut>(`/reports/reconciliations/${recSelected.id}/approve`, {
        token,
        method: 'POST',
      })
      setRecSavedMsg('Reconciliation approved.')
      await loadReconciliationData()
      selectReconciliation(row)
    } catch (e) {
      setErr((e as ApiError)?.message ?? 'Approve failed')
    } finally {
      setBusy(false)
    }
  }

  async function downloadReconciliationReport(recId: string) {
    setBusy(true)
    setErr(null)
    try {
      const headers = new Headers()
      applyAuthHeaders(headers, token.trim())
      const res = await fetch(apiUrl(`/reports/reconciliations/${recId}/report.docx`), { headers })
      if (!res.ok) {
        const raw = await res.json().catch(() => ({}))
        const msg =
          typeof (raw as { detail?: unknown }).detail === 'string'
            ? (raw as { detail: string }).detail
            : `Download failed (${res.status})`
        throw new Error(msg)
      }
      const blob = await res.blob()
      const row = recRows.find((r) => r.id === recId)
      const period = row?.period_end_date?.slice(0, 7) ?? 'report'
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `Client account reconcile report — ${period}.docx`
      a.click()
      URL.revokeObjectURL(a.href)
    } catch (e) {
      setErr((e as Error)?.message ?? 'Download failed')
    } finally {
      setBusy(false)
    }
  }

  function requireFeeEarners(): boolean {
    if (feeEarnerSelected.size === 0) {
      setErr('Select at least one fee earner.')
      return false
    }
    return true
  }

  async function runJson(path: string, body: object) {
    if (tab !== 'client_account_reconcile' && !requireFeeEarners()) return
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
    if (tab !== 'client_account_reconcile' && !requireFeeEarners()) return
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

  const timeRecordedBody = useMemo(() => {
    const o: Record<string, unknown> = { ...feeEarnerPayload }
    if (timeRecordedFrom.trim()) o.date_from = timeRecordedFrom.trim()
    if (timeRecordedTo.trim()) o.date_to = timeRecordedTo.trim()
    return o
  }, [feeEarnerPayload, timeRecordedFrom, timeRecordedTo])

  const wipBody = useMemo(() => {
    const o: Record<string, unknown> = { ...feeEarnerPayload }
    if (wipAsOf.trim()) o.as_of = wipAsOf.trim()
    return o
  }, [feeEarnerPayload, wipAsOf])

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

  const ledgerActivityBody = useMemo(() => {
    const o: Record<string, unknown> = { ...feeEarnerPayload, approved_only: ledgerApprovedOnly }
    if (ledgerFrom.trim()) o.date_from = ledgerFrom.trim()
    if (ledgerTo.trim()) o.date_to = ledgerTo.trim()
    return o
  }, [feeEarnerPayload, ledgerFrom, ledgerTo, ledgerApprovedOnly])

  const agedDebtBody = useMemo(() => {
    const o: Record<string, unknown> = { ...feeEarnerPayload }
    if (agedDebtAsOf.trim()) o.as_of = agedDebtAsOf.trim()
    return o
  }, [feeEarnerPayload, agedDebtAsOf])

  const exceptionsBody = useMemo(() => {
    const o: Record<string, unknown> = { ...feeEarnerPayload }
    if (excFrom.trim()) o.date_from = excFrom.trim()
    if (excTo.trim()) o.date_to = excTo.trim()
    const pounds = parseFloat(excLargeMinPounds.replace(/,/g, ''))
    if (Number.isFinite(pounds) && pounds > 0) {
      o.large_posting_min_pence = Math.round(pounds * 100)
    }
    return o
  }, [feeEarnerPayload, excFrom, excTo, excLargeMinPounds])

  const packBody = useMemo(() => {
    const o: Record<string, unknown> = {
      ...feeEarnerPayload,
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
    feeEarnerPayload,
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

  async function loadPackPreview() {
    if (!requireFeeEarners()) return
    if (!packPeriodEnd.trim()) {
      setErr('Choose a period end date.')
      return
    }
    setBusy(true)
    setErr(null)
    try {
      const data = await apiFetch<AccountantPackPreviewOut>('/reports/accountant-pack/preview', {
        token,
        method: 'POST',
        json: packBody,
      })
      setPackPreview(data)
    } catch (e) {
      setPackPreview(null)
      setErr((e as ApiError)?.message ?? 'Preview failed')
    } finally {
      setBusy(false)
    }
  }

  async function downloadAccountantPack() {
    if (!requireFeeEarners()) return
    if (!packPeriodEnd.trim()) {
      setErr('Choose a period end date.')
      return
    }
    if (
      !packIncludeBalances &&
      !packIncludeBilling &&
      !packIncludeLedger &&
      !packIncludeAgedDebt &&
      !packIncludeExceptions &&
      !packIncludeReconcileDoc
    ) {
      setErr('Select at least one section to include.')
      return
    }
    setBusy(true)
    setErr(null)
    try {
      const headers = new Headers()
      applyAuthHeaders(headers, token.trim())
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
      const period = packPeriodEnd.trim().slice(0, 7)
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `canary-accountant-pack-${period}.zip`
      a.click()
      URL.revokeObjectURL(a.href)
    } catch (e) {
      setErr((e as Error)?.message ?? 'Download failed')
    } finally {
      setBusy(false)
    }
  }

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

  const timeRecordedDateSummary = useMemo(() => {
    if (!timeRecordedFrom.trim() && !timeRecordedTo.trim()) return 'All dates'
    const a = timeRecordedFrom.trim() || '…'
    const b = timeRecordedTo.trim() || '…'
    return `${a} → ${b}`
  }, [timeRecordedFrom, timeRecordedTo])

  const wipAsOfSummary = useMemo(() => (wipAsOf.trim() ? wipAsOf.trim() : 'Today'), [wipAsOf])

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

  const ledgerDateSummary = useMemo(() => {
    if (!ledgerFrom.trim() && !ledgerTo.trim()) return 'All dates'
    const a = ledgerFrom.trim() || '…'
    const b = ledgerTo.trim() || '…'
    return `${a} → ${b}`
  }, [ledgerFrom, ledgerTo])

  const ledgerApprovedSummary = useMemo(() => (ledgerApprovedOnly ? 'Approved only' : 'All postings'), [ledgerApprovedOnly])

  const agedDebtAsOfSummary = useMemo(() => (agedDebtAsOf.trim() ? agedDebtAsOf.trim() : 'Today'), [agedDebtAsOf])

  const excDateSummary = useMemo(() => {
    if (!excFrom.trim() && !excTo.trim()) return 'All dates'
    const a = excFrom.trim() || '…'
    const b = excTo.trim() || '…'
    return `${a} → ${b}`
  }, [excFrom, excTo])

  const excLargeSummary = useMemo(() => {
    const pounds = parseFloat(excLargeMinPounds.replace(/,/g, ''))
    return Number.isFinite(pounds) && pounds > 0 ? `≥ £${pounds.toLocaleString()}` : '≥ £5,000'
  }, [excLargeMinPounds])

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

  const previewWip = previewJson as {
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

  const previewTimeRecorded = previewJson as {
    by_fee_earner?: {
      user_id: string
      display_name: string
      duration_hours: number
      billable_hours: number
      nil_rate_hours: number
      value_pence: number
      entry_count: number
      unbilled_minutes: number
      billed_minutes: number
      written_off_minutes: number
    }[]
    entries?: {
      entry_id: string
      case_number: string
      client_name?: string | null
      fee_earner_name: string
      work_date: string
      duration_minutes: number
      description: string
      non_billable: boolean
      status: string
      value_pence: number | null
    }[]
    totals?: {
      duration_minutes: number
      billable_minutes: number
      nil_rate_minutes: number
      value_pence: number
      entry_count: number
      unbilled_minutes: number
      billed_minutes: number
      written_off_minutes: number
    }
  } | null

  function formatHoursFromMinutes(m: number): string {
    return (m / 60).toFixed(1)
  }

  function timeStatusLabel(status: string): string {
    if (status === 'written_off') return 'Written off'
    if (status === 'billed') return 'Billed'
    return 'Unbilled'
  }

  const previewCases = previewJson as {
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

  const previewLedgerActivity = previewJson as {
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

  function formatLedgerLegs(client?: string | null, office?: string | null): string {
    const parts: string[] = []
    if (client) parts.push(`client ${client}`)
    if (office) parts.push(`office ${office}`)
    return parts.join(' / ') || '—'
  }

  const previewAgedDebt = previewJson as {
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

  const previewExceptions = previewJson as {
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

  function ExceptionSection({
    title,
    empty,
    children,
  }: {
    title: string
    empty: boolean
    children: ReactNode
  }) {
    return (
      <div style={{ marginTop: 20 }}>
        <h3 style={{ margin: '0 0 8px', fontSize: 15 }}>{title}</h3>
        {empty ? <p className="muted" style={{ margin: 0 }}>None.</p> : children}
      </div>
    )
  }

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
          <div className="reportsReportSelect">
            <SingleSelectDropdown
              label="Report"
              options={REPORT_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
              value={tab}
              onChange={(v) => {
                setTab(v as ReportTab)
                setPreviewJson(null)
                setOpenFilterId(null)
              }}
              disabled={busy}
            />
          </div>

          <div className="reportsFilterRow">
            {tab !== 'client_account_reconcile' ? (
            <FilterDropdown
              id="fe"
              label="Fee earners"
              summary={feSummary}
              openId={openFilterId}
              setOpenId={setOpenFilterId}
              fitContentItemCount={feeEarners.length}
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
              <div className={scrollPanelClassName('reportsDdCheckList', feeEarners.length)}>
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
            ) : null}

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

            {tab === 'time_recorded' ? (
              <FilterDropdown
                id="timeRecordedDates"
                label="Work date range"
                summary={timeRecordedDateSummary}
                openId={openFilterId}
                setOpenId={setOpenFilterId}
              >
                <div className="reportsDdDateFields">
                  <label className="field">
                    <span>From</span>
                    <input type="date" value={timeRecordedFrom} onChange={(e) => setTimeRecordedFrom(e.target.value)} />
                  </label>
                  <label className="field">
                    <span>To</span>
                    <input type="date" value={timeRecordedTo} onChange={(e) => setTimeRecordedTo(e.target.value)} />
                  </label>
                  <p className="muted" style={{ margin: '4px 0 0', fontSize: 12 }}>
                    Filter by work date on each time entry. Leave both empty for all time.
                  </p>
                </div>
              </FilterDropdown>
            ) : null}

            {tab === 'wip' ? (
              <FilterDropdown
                id="wipAsOf"
                label="Age as of"
                summary={wipAsOfSummary}
                openId={openFilterId}
                setOpenId={setOpenFilterId}
              >
                <div className="reportsDdDateFields">
                  <label className="field">
                    <span>As of date</span>
                    <input type="date" value={wipAsOf} onChange={(e) => setWipAsOf(e.target.value)} />
                  </label>
                  <p className="muted" style={{ margin: '4px 0 0', fontSize: 12 }}>
                    Leave empty to use today. Age buckets: 0–30, 31–90, and 90+ days from work date.
                  </p>
                </div>
              </FilterDropdown>
            ) : null}

            {tab === 'aged_debt' ? (
              <FilterDropdown
                id="agedDebtAsOf"
                label="Age as of"
                summary={agedDebtAsOfSummary}
                openId={openFilterId}
                setOpenId={setOpenFilterId}
              >
                <div className="reportsDdDateFields">
                  <label className="field">
                    <span>As of date</span>
                    <input type="date" value={agedDebtAsOf} onChange={(e) => setAgedDebtAsOf(e.target.value)} />
                  </label>
                  <p className="muted" style={{ margin: '4px 0 0', fontSize: 12 }}>
                    Leave empty to use today. Age buckets are measured from invoice approval date.
                  </p>
                </div>
              </FilterDropdown>
            ) : null}

            {tab === 'exceptions' ? (
              <>
                <FilterDropdown
                  id="excDates"
                  label="Large posting dates"
                  summary={excDateSummary}
                  openId={openFilterId}
                  setOpenId={setOpenFilterId}
                >
                  <div className="reportsDdDateFields">
                    <label className="field">
                      <span>From</span>
                      <input type="date" value={excFrom} onChange={(e) => setExcFrom(e.target.value)} />
                    </label>
                    <label className="field">
                      <span>To</span>
                      <input type="date" value={excTo} onChange={(e) => setExcTo(e.target.value)} />
                    </label>
                    <p className="muted" style={{ margin: '4px 0 0', fontSize: 12 }}>
                      Applies to the large postings section only. Leave both empty for all time.
                    </p>
                  </div>
                </FilterDropdown>
                <FilterDropdown
                  id="excLarge"
                  label="Large posting minimum"
                  summary={excLargeSummary}
                  openId={openFilterId}
                  setOpenId={setOpenFilterId}
                >
                  <label className="field">
                    <span>Minimum amount (£)</span>
                    <input
                      type="number"
                      min={1}
                      step={100}
                      value={excLargeMinPounds}
                      onChange={(e) => setExcLargeMinPounds(e.target.value)}
                    />
                  </label>
                </FilterDropdown>
              </>
            ) : null}

            {tab === 'ledger_activity' ? (
              <>
                <FilterDropdown
                  id="ledgerDates"
                  label="Posted date range"
                  summary={ledgerDateSummary}
                  openId={openFilterId}
                  setOpenId={setOpenFilterId}
                >
                  <div className="reportsDdDateFields">
                    <label className="field">
                      <span>From</span>
                      <input type="date" value={ledgerFrom} onChange={(e) => setLedgerFrom(e.target.value)} />
                    </label>
                    <label className="field">
                      <span>To</span>
                      <input type="date" value={ledgerTo} onChange={(e) => setLedgerTo(e.target.value)} />
                    </label>
                    <p className="muted" style={{ margin: '4px 0 0', fontSize: 12 }}>
                      Leave both empty for all time.
                    </p>
                  </div>
                </FilterDropdown>
                <FilterDropdown
                  id="ledgerApproved"
                  label="Approval status"
                  summary={ledgerApprovedSummary}
                  openId={openFilterId}
                  setOpenId={setOpenFilterId}
                >
                  <div className={scrollPanelClassName('reportsDdCheckList', 1)}>
                    <label className="reportsCheckbox">
                      <input
                        type="checkbox"
                        checked={ledgerApprovedOnly}
                        onChange={(e) => setLedgerApprovedOnly(e.target.checked)}
                      />
                      <span>Approved postings only</span>
                    </label>
                  </div>
                </FilterDropdown>
              </>
            ) : null}

            {tab === 'accountant_pack' ? (
              <>
                <FilterDropdown
                  id="packPeriodEnd"
                  label="Period end date"
                  summary={packPeriodSummary}
                  openId={openFilterId}
                  setOpenId={setOpenFilterId}
                >
                  <div className="reportsDdDateFields">
                    <label className="field">
                      <span>Period end</span>
                      <input
                        type="date"
                        value={packPeriodEnd}
                        onChange={(e) => onPackPeriodEndChange(e.target.value)}
                      />
                    </label>
                    <p className="muted" style={{ margin: '4px 0 0', fontSize: 12 }}>
                      Balances and aged debt are as at this date.
                    </p>
                  </div>
                </FilterDropdown>
                <FilterDropdown
                  id="packActivityDates"
                  label="Activity date range"
                  summary={packActivitySummary}
                  openId={openFilterId}
                  setOpenId={setOpenFilterId}
                >
                  <div className="reportsDdDateFields">
                    <label className="field">
                      <span>From</span>
                      <input
                        type="date"
                        value={packActivityFrom}
                        onChange={(e) => {
                          setPackActivityFrom(e.target.value)
                          setPackPreview(null)
                        }}
                      />
                    </label>
                    <label className="field">
                      <span>To</span>
                      <input
                        type="date"
                        value={packActivityTo}
                        onChange={(e) => {
                          setPackActivityTo(e.target.value)
                          setPackPreview(null)
                        }}
                      />
                    </label>
                    <p className="muted" style={{ margin: '4px 0 0', fontSize: 12 }}>
                      Billing and ledger activity within this range (defaults to period month).
                    </p>
                  </div>
                </FilterDropdown>
              </>
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
                <div className={scrollPanelClassName('reportsDdCheckList', CASE_STATUS_OPTIONS.length)}>
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
                  <div className={scrollPanelClassName('reportsDdCheckList', 2)}>
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
                  <div className={scrollPanelClassName('reportsDdCheckList reportsDdCheckList--tall', evTemplates.length)}>
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

        {tab === 'time_recorded' ? (
          <section className="reportsSection">
            <p className="muted" style={{ marginTop: 0 }}>
              Time logged on matters by work date — all statuses (unbilled, billed, written off) and nil-rate entries
              included. Value is at each fee earner&apos;s charge rate for billable entries only.
            </p>
            <div className="row" style={{ gap: 8, marginTop: 10 }}>
              <button
                type="button"
                className="btn primary"
                disabled={busy}
                onClick={() => void runJson('/reports/time-recorded', timeRecordedBody)}
              >
                Run report
              </button>
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => void runXlsx('/reports/time-recorded', timeRecordedBody, 'canary-report-time-recorded.xlsx')}
              >
                Export Excel
              </button>
            </div>
            {previewTimeRecorded?.by_fee_earner ? (
              <div className="stack" style={{ gap: 16, marginTop: 12 }}>
                <div className="reportsPreviewScroll">
                  <table className="reportsTable">
                    <thead>
                      <tr>
                        <th>Fee earner</th>
                        <th>Total hrs</th>
                        <th>Billable hrs</th>
                        <th>Nil-rate hrs</th>
                        <th>Value</th>
                        <th>Entries</th>
                        <th>Unbilled hrs</th>
                        <th>Billed hrs</th>
                        <th>Written-off hrs</th>
                      </tr>
                    </thead>
                    <tbody>
                      {previewTimeRecorded.by_fee_earner.map((r) => (
                        <tr key={r.user_id}>
                          <td>{r.display_name}</td>
                          <td>{r.duration_hours}</td>
                          <td>{r.billable_hours}</td>
                          <td>{r.nil_rate_hours}</td>
                          <td>{formatMoneyPence(r.value_pence)}</td>
                          <td>{r.entry_count}</td>
                          <td>{formatHoursFromMinutes(r.unbilled_minutes)}</td>
                          <td>{formatHoursFromMinutes(r.billed_minutes)}</td>
                          <td>{formatHoursFromMinutes(r.written_off_minutes)}</td>
                        </tr>
                      ))}
                      {previewTimeRecorded.totals ? (
                        <tr className="reportsTableTotalRow">
                          <td>
                            <strong>Total</strong>
                          </td>
                          <td>
                            <strong>{formatHoursFromMinutes(previewTimeRecorded.totals.duration_minutes)}</strong>
                          </td>
                          <td>
                            <strong>{formatHoursFromMinutes(previewTimeRecorded.totals.billable_minutes)}</strong>
                          </td>
                          <td>
                            <strong>{formatHoursFromMinutes(previewTimeRecorded.totals.nil_rate_minutes)}</strong>
                          </td>
                          <td>
                            <strong>{formatMoneyPence(previewTimeRecorded.totals.value_pence)}</strong>
                          </td>
                          <td>
                            <strong>{previewTimeRecorded.totals.entry_count}</strong>
                          </td>
                          <td>
                            <strong>{formatHoursFromMinutes(previewTimeRecorded.totals.unbilled_minutes)}</strong>
                          </td>
                          <td>
                            <strong>{formatHoursFromMinutes(previewTimeRecorded.totals.billed_minutes)}</strong>
                          </td>
                          <td>
                            <strong>{formatHoursFromMinutes(previewTimeRecorded.totals.written_off_minutes)}</strong>
                          </td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
                {previewTimeRecorded.entries?.length ? (
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
                          <th>Nil rate</th>
                          <th>Status</th>
                          <th>Value</th>
                        </tr>
                      </thead>
                      <tbody>
                        {previewTimeRecorded.entries.map((r) => (
                          <tr key={r.entry_id}>
                            <td>{r.case_number}</td>
                            <td>{r.client_name ?? ''}</td>
                            <td>{r.fee_earner_name}</td>
                            <td>{r.work_date}</td>
                            <td>{formatHoursFromMinutes(r.duration_minutes)}</td>
                            <td>{r.description}</td>
                            <td>{r.non_billable ? 'Yes' : 'No'}</td>
                            <td>{timeStatusLabel(r.status)}</td>
                            <td>{r.non_billable ? '—' : r.value_pence != null ? formatMoneyPence(r.value_pence) : '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null}
              </div>
            ) : null}
          </section>
        ) : null}

        {tab === 'wip' ? (
          <section className="reportsSection">
            <p className="muted" style={{ marginTop: 0 }}>
              Unbilled time entries across matters, valued at each fee earner&apos;s charge rate. Written-off and billed
              time is excluded.
            </p>
            <div className="row" style={{ gap: 8, marginTop: 10 }}>
              <button type="button" className="btn primary" disabled={busy} onClick={() => void runJson('/reports/wip', wipBody)}>
                Run report
              </button>
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => void runXlsx('/reports/wip', wipBody, 'canary-report-wip.xlsx')}
              >
                Export Excel
              </button>
            </div>
            {previewWip?.by_fee_earner ? (
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
                      {previewWip.by_fee_earner.map((r) => (
                        <tr key={r.user_id}>
                          <td>{r.display_name}</td>
                          <td>{r.duration_hours}</td>
                          <td>{formatMoneyPence(r.value_pence)}</td>
                          <td>{r.entry_count}</td>
                        </tr>
                      ))}
                      {previewWip.totals ? (
                        <tr className="reportsTableTotalRow">
                          <td>
                            <strong>Total</strong>
                          </td>
                          <td>
                            <strong>{(previewWip.totals.duration_minutes / 60).toFixed(1)}</strong>
                          </td>
                          <td>
                            <strong>{formatMoneyPence(previewWip.totals.value_pence)}</strong>
                          </td>
                          <td>
                            <strong>{previewWip.totals.entry_count}</strong>
                          </td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
                {previewWip.entries?.length ? (
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
                        {previewWip.entries.map((r) => (
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
        ) : null}

        {tab === 'aged_debt' ? (
          <section className="reportsSection">
            <p className="muted" style={{ marginTop: 0 }}>
              Approved invoices on matters whose office balance is still debit (client owes). There is no separate
              paid flag — matter office balance is the debt indicator.
            </p>
            <div className="row" style={{ gap: 8, marginTop: 10 }}>
              <button type="button" className="btn primary" disabled={busy} onClick={() => void runJson('/reports/aged-debt', agedDebtBody)}>
                Run report
              </button>
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => void runXlsx('/reports/aged-debt', agedDebtBody, 'canary-report-aged-debt.xlsx')}
              >
                Export Excel
              </button>
            </div>
            {previewAgedDebt?.rows ? (
              <div className="reportsPreviewScroll">
                {previewAgedDebt.bucket_totals_pence ? (
                  <div className="row" style={{ gap: 16, marginTop: 14, marginBottom: 8, flexWrap: 'wrap' }}>
                    {AGED_DEBT_BUCKETS.map((b) => (
                      <span key={b} className="muted" style={{ fontSize: 13 }}>
                        <strong>{b} days:</strong> {formatMoneyPence(previewAgedDebt.bucket_totals_pence?.[b] ?? 0)}
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
                    {previewAgedDebt.rows.map((r) => (
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
        ) : null}

        {tab === 'exceptions' ? (
          <section className="reportsSection">
            <p className="muted" style={{ marginTop: 0 }}>
              Month-end exception checks: pending approvals, closed matters with client money, negative client balances,
              and large postings.
            </p>
            <div className="row" style={{ gap: 8, marginTop: 10 }}>
              <button type="button" className="btn primary" disabled={busy} onClick={() => void runJson('/reports/exceptions', exceptionsBody)}>
                Run report
              </button>
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => void runXlsx('/reports/exceptions', exceptionsBody, 'canary-report-exceptions.xlsx')}
              >
                Export Excel
              </button>
            </div>
            {previewExceptions ? (
              <div className="reportsPreviewScroll">
                <ExceptionSection title="Pending ledger approvals" empty={!(previewExceptions.pending_ledger_approvals?.length)}>
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
                      {previewExceptions.pending_ledger_approvals?.map((r) => (
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

                <ExceptionSection title="Pending invoices" empty={!(previewExceptions.pending_invoices?.length)}>
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
                      {previewExceptions.pending_invoices?.map((r) => (
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
                  empty={!(previewExceptions.client_balance_closed_archived?.length)}
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
                      {previewExceptions.client_balance_closed_archived?.map((r) => (
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

                <ExceptionSection title="Negative client balance" empty={!(previewExceptions.negative_client_balance?.length)}>
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
                      {previewExceptions.negative_client_balance?.map((r) => (
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

                <ExceptionSection title="Large postings" empty={!(previewExceptions.large_postings?.length)}>
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
                      {previewExceptions.large_postings?.map((r) => (
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
        ) : null}

        {tab === 'ledger_activity' ? (
          <section className="reportsSection">
            <p className="muted" style={{ marginTop: 0 }}>
              All ledger postings for matters in scope, newest first. Pending postings appear until approved.
            </p>
            <div className="row" style={{ gap: 8, marginTop: 10 }}>
              <button
                type="button"
                className="btn primary"
                disabled={busy}
                onClick={() => void runJson('/reports/ledger-activity', ledgerActivityBody)}
              >
                Run report
              </button>
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() =>
                  void runXlsx('/reports/ledger-activity', ledgerActivityBody, 'canary-report-ledger-activity.xlsx')
                }
              >
                Export Excel
              </button>
            </div>
            {previewLedgerActivity?.rows ? (
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
                    {previewLedgerActivity.rows.map((r) => (
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
                      <th>Source</th>
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
                        <td>{r.source_name ?? ''}</td>
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

        {tab === 'accountant_pack' ? (
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
                    checked={packIncludeBalances}
                    onChange={(e) => {
                      setPackIncludeBalances(e.target.checked)
                      setPackPreview(null)
                    }}
                  />
                  <span>Client &amp; office balances</span>
                </label>
                <label className="reportsCheckbox">
                  <input
                    type="checkbox"
                    checked={packIncludeBilling}
                    onChange={(e) => {
                      setPackIncludeBilling(e.target.checked)
                      setPackPreview(null)
                    }}
                  />
                  <span>Billing</span>
                </label>
                <label className="reportsCheckbox">
                  <input
                    type="checkbox"
                    checked={packIncludeLedger}
                    onChange={(e) => {
                      setPackIncludeLedger(e.target.checked)
                      setPackPreview(null)
                    }}
                  />
                  <span>Client &amp; office ledger activity</span>
                </label>
                <label className="reportsCheckbox">
                  <input
                    type="checkbox"
                    checked={packIncludeAgedDebt}
                    onChange={(e) => {
                      setPackIncludeAgedDebt(e.target.checked)
                      setPackPreview(null)
                    }}
                  />
                  <span>Aged debt</span>
                </label>
                <label className="reportsCheckbox">
                  <input
                    type="checkbox"
                    checked={packIncludeExceptions}
                    onChange={(e) => {
                      setPackIncludeExceptions(e.target.checked)
                      setPackPreview(null)
                    }}
                  />
                  <span>Exceptions</span>
                </label>
                <label className="reportsCheckbox">
                  <input
                    type="checkbox"
                    checked={packIncludeReconcileDoc}
                    onChange={(e) => {
                      setPackIncludeReconcileDoc(e.target.checked)
                      setPackPreview(null)
                    }}
                  />
                  <span>Client account reconcile report (Word)</span>
                </label>
              </div>
              <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                <button type="button" className="btn" disabled={busy} onClick={() => void loadPackPreview()}>
                  Refresh preview
                </button>
                <button type="button" className="btn primary" disabled={busy} onClick={() => void downloadAccountantPack()}>
                  Download export pack
                </button>
              </div>
            </div>
            {packPreview ? (
              <div className="reportsPreviewScroll" style={{ marginTop: 16 }}>
                <h3 style={{ margin: '0 0 8px', fontSize: 15 }}>Pack preview</h3>
                <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
                  Activity: {packPreview.activity_date_from} → {packPreview.activity_date_to} · Fee earners:{' '}
                  {packPreview.fee_earner_count}
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
                    {packPreview.sections.map((s) => (
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
        ) : null}

        {tab === 'client_account_reconcile' ? (
          <section className="reportsSection">
            <p className="muted" style={{ marginTop: 0 }}>
              Month-end client account reconciliation: compare the firm-wide ledger client total against your bank
              statement closing balance, approve the snapshot, then generate the client account reconcile report.
            </p>
            {recSavedMsg ? <div className="muted" style={{ marginBottom: 8 }}>{recSavedMsg}</div> : null}
            <div className="card" style={{ padding: 16, marginTop: 12 }}>
              <div className="stack" style={{ gap: 12, maxWidth: 520 }}>
                <label className="field">
                  <span>Period end date</span>
                  <input
                    type="date"
                    value={recPeriodEnd}
                    onChange={(e) => {
                      setRecPeriodEnd(e.target.value)
                      setRecSelectedId(null)
                    }}
                    disabled={busy || recSelected?.status === 'approved'}
                  />
                </label>
                {recPreview ? (
                  <div className="muted" style={{ fontSize: 13 }}>
                    <div>
                      Ledger client total (all matters):{' '}
                      <strong>{formatMoneyPence(recPreview.ledger_client_total_pence)}</strong>
                    </div>
                    <div>
                      Office ledger total (reference):{' '}
                      <strong>{formatMoneyPence(recPreview.ledger_office_total_pence)}</strong>
                    </div>
                  </div>
                ) : (
                  <div className="muted">Loading ledger totals…</div>
                )}
                <label className="field">
                  <span>Bank statement closing balance (£)</span>
                  <input
                    value={recBankPounds}
                    onChange={(e) => setRecBankPounds(e.target.value)}
                    disabled={busy || recSelected?.status === 'approved'}
                    inputMode="decimal"
                    placeholder="0.00"
                  />
                </label>
                {recDraftDifference !== null ? (
                  <div style={{ fontSize: 14 }}>
                    Difference (bank minus ledger):{' '}
                    <strong className={recDraftDifference === 0 ? undefined : 'error'}>
                      {formatMoneyPence(recDraftDifference)}
                    </strong>
                    {recDraftDifference !== 0 ? (
                      <span className="muted"> — explain in notes before approving</span>
                    ) : null}
                  </div>
                ) : null}
                <label className="field">
                  <span>Notes</span>
                  <textarea
                    value={recNotes}
                    onChange={(e) => setRecNotes(e.target.value)}
                    disabled={busy || recSelected?.status === 'approved'}
                    rows={3}
                    placeholder="Optional; required if difference is not zero"
                  />
                </label>
                <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                  {recSelected?.status !== 'approved' ? (
                    <>
                      <button type="button" className="btn primary" disabled={busy} onClick={() => void saveReconciliationDraft()}>
                        Save draft
                      </button>
                      {recCanApprove && recSelected?.status === 'draft' ? (
                        <button type="button" className="btn" disabled={busy} onClick={() => void approveReconciliation()}>
                          Approve
                        </button>
                      ) : null}
                      <button type="button" className="btn" disabled={busy} onClick={clearReconciliationSelection}>
                        New period
                      </button>
                    </>
                  ) : null}
                  {recSelected ? (
                    <button
                      type="button"
                      className="btn"
                      disabled={busy}
                      onClick={() => void downloadReconciliationReport(recSelected.id)}
                    >
                      Download client account reconcile report
                    </button>
                  ) : null}
                  <button type="button" className="btn" disabled={busy} onClick={() => void loadReconciliationData()}>
                    Refresh totals
                  </button>
                </div>
                {recSelected?.status === 'approved' ? (
                  <div className="muted" style={{ fontSize: 13 }}>
                    Approved by {recSelected.approved_by_name ?? '—'} on{' '}
                    {recSelected.approved_at?.slice(0, 10) ?? '—'}. This snapshot is locked.
                  </div>
                ) : null}
              </div>
            </div>
            {recRows.length ? (
              <div className="reportsPreviewScroll" style={{ marginTop: 20 }}>
                <h3 style={{ margin: '0 0 8px', fontSize: 15 }}>Previous reconciliations</h3>
                <table className="reportsTable">
                  <thead>
                    <tr>
                      <th>Period end</th>
                      <th>Ledger client</th>
                      <th>Bank balance</th>
                      <th>Difference</th>
                      <th>Status</th>
                      <th>Prepared</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {recRows.map((r) => (
                      <tr key={r.id}>
                        <td>{r.period_end_date}</td>
                        <td>{formatMoneyPence(r.ledger_client_total_pence)}</td>
                        <td>{formatMoneyPence(r.bank_statement_balance_pence)}</td>
                        <td>{formatMoneyPence(r.difference_pence)}</td>
                        <td>{r.status === 'approved' ? 'Approved' : 'Draft'}</td>
                        <td>{r.prepared_by_name ?? ''}</td>
                        <td>
                          <button type="button" className="btn btn--small" disabled={busy} onClick={() => selectReconciliation(r)}>
                            Open
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="muted" style={{ marginTop: 16 }}>No reconciliations yet.</p>
            )}
          </section>
        ) : null}
        </div>
      </div>
    </div>
  )
}
