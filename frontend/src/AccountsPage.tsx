import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from './api'
import { fetchCaseSearch } from './apiSearch'
import { downloadInvoiceDocument, invoiceDownloadFilename } from './invoiceDownload'
import type { ApiError } from './api'
import { ConfirmModal } from './ConfirmModal'
import { EditPendingLedgerModal } from './EditPendingLedgerModal'
import type {
  CaseOut,
  ClientAccountReconciliationOut,
  LedgerPermissionsOut,
  ReconciliationPreviewOut,
  UserPublic,
} from './types'
import {
  canApprovePendingLedgerRow,
  matchesPendingLedgerFilters,
  type PendingLedgerAccountFilter,
  type PendingLedgerDirectionFilter,
} from './ledgerApproval'

type AccountsTab = 'queue' | 'exceptions' | 'activity' | 'reconcile'

type FeeEarnerPick = { id: string; display_name: string; email: string }

type ExceptionLedgerRow = {
  pair_id: string
  case_id?: string
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
  is_anticipated?: boolean
  anticipated_for_date?: string | null
  reference?: string | null
}

type ExceptionBalRow = {
  case_id?: string
  case_number: string
  client_name?: string | null
  matter_description: string
  status_label: string
  fee_earner_name: string
  client_balance_pence: number
  office_balance_pence: number
}

type PendingInvoiceRow = {
  invoice_id: string
  case_id: string
  case_number: string
  client_name?: string | null
  matter_description: string
  fee_earner_name: string
  invoice_number: string
  created_at: string
  total_pence: number
}

type RecentApprovedInvoiceRow = {
  invoice_id: string
  case_id: string
  case_number: string
  client_name?: string | null
  matter_description: string
  fee_earner_name: string
  invoice_number: string
  approved_at: string | null
  total_pence: number
  document_file_id?: string | null
}

type ExceptionsPayload = {
  pending_ledger_approvals?: ExceptionLedgerRow[]
  pending_invoices?: PendingInvoiceRow[]
  client_balance_closed_archived?: ExceptionBalRow[]
  negative_client_balance?: ExceptionBalRow[]
}

type LedgerActivityRow = {
  pair_id: string
  case_id: string
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
}

const TAB_OPTIONS: { value: AccountsTab; label: string }[] = [
  { value: 'queue', label: 'Work queue' },
  { value: 'exceptions', label: 'Exceptions' },
  { value: 'activity', label: 'Ledger activity' },
  { value: 'reconcile', label: 'Client account' },
]

function formatMoneyPence(p: number): string {
  const neg = p < 0
  const a = Math.abs(p)
  const s = (a / 100).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return `${neg ? '-' : ''}£${s}`
}

function ledgerTotalToneClass(pence: number): string {
  if (pence > 0) return 'accountsLedgerTotal--positive'
  if (pence < 0) return 'accountsLedgerTotal--negative'
  return ''
}

function formatPostedAt(iso: string): string {
  return iso.slice(0, 16).replace('T', ' ')
}

function formatExpectedDate(isoDate: string | null | undefined): string {
  if (!isoDate) return '—'
  const [y, m, d] = isoDate.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

function ledgerLegSummary(row: Pick<ExceptionLedgerRow, 'client_direction' | 'office_direction'>): string {
  const parts: string[] = []
  if (row.client_direction) parts.push(`Client ${row.client_direction}`)
  if (row.office_direction) parts.push(`Office ${row.office_direction}`)
  return parts.join(' · ') || '—'
}

function openLedgerWindow(caseId: string) {
  const url = `${window.location.origin}${window.location.pathname}?ledger=${encodeURIComponent(caseId)}`
  window.open(url, `canary-ledger-${caseId}`, 'noopener,noreferrer')
}

function defaultActivityFrom(): string {
  const d = new Date()
  d.setDate(d.getDate() - 30)
  return d.toISOString().slice(0, 10)
}

function defaultActivityTo(): string {
  return new Date().toISOString().slice(0, 10)
}

type Props = {
  token: string
  me: UserPublic | null
  onOpenCase: (caseId: string) => void
  onOpenReportsReconcile: () => void
}

export function AccountsPage({ token, me, onOpenCase, onOpenReportsReconcile }: Props) {
  const [tab, setTab] = useState<AccountsTab>('queue')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [feeEarnerIds, setFeeEarnerIds] = useState<string[]>([])
  const [ledgerPerm, setLedgerPerm] = useState<LedgerPermissionsOut | null>(null)
  const [exceptions, setExceptions] = useState<ExceptionsPayload | null>(null)
  const [recentApprovedInvoices, setRecentApprovedInvoices] = useState<RecentApprovedInvoiceRow[]>([])
  const [activityRows, setActivityRows] = useState<LedgerActivityRow[]>([])
  const [recPreview, setRecPreview] = useState<ReconciliationPreviewOut | null>(null)
  const [recRows, setRecRows] = useState<ClientAccountReconciliationOut[]>([])
  const [caseSearch, setCaseSearch] = useState('')
  const [caseResults, setCaseResults] = useState<CaseOut[]>([])
  const [caseSearchBusy, setCaseSearchBusy] = useState(false)
  const [actionKey, setActionKey] = useState<string | null>(null)
  const [pendingLedgerAccountFilter, setPendingLedgerAccountFilter] =
    useState<PendingLedgerAccountFilter>('all')
  const [pendingLedgerDirectionFilter, setPendingLedgerDirectionFilter] =
    useState<PendingLedgerDirectionFilter>('all')
  const [editLedger, setEditLedger] = useState<{
    caseId: string
    pairId: string
    amountPence: number
    description: string
    reference: string
    isAnticipated: boolean
    anticipatedForDate: string
  } | null>(null)
  const [rejectLedger, setRejectLedger] = useState<{ caseId: string; pairId: string } | null>(null)

  const loadFeeEarners = useCallback(async () => {
    const rows = await apiFetch<FeeEarnerPick[]>('/reports/fee-earners', { token })
    setFeeEarnerIds(rows.map((r) => r.id))
    return rows
  }, [token])

  const loadLedgerPermissions = useCallback(async () => {
    const perms = await apiFetch<LedgerPermissionsOut>('/users/me/ledger-permissions', { token })
    setLedgerPerm(perms)
    return perms
  }, [token])

  const refreshAll = useCallback(async () => {
    setBusy(true)
    setErr(null)
    try {
      const rows = await loadFeeEarners()
      const ids = rows.map((r) => r.id)
      await loadLedgerPermissions()
      if (!ids.length) {
        setExceptions(null)
        setRecentApprovedInvoices([])
        setActivityRows([])
      } else {
        const payload = { fee_earner_user_ids: ids }
        const [exc, recent, act, rec] = await Promise.all([
          apiFetch<ExceptionsPayload>('/reports/exceptions', { method: 'POST', token, json: payload }),
          apiFetch<{ rows: RecentApprovedInvoiceRow[] }>('/reports/recent-approved-invoices', {
            method: 'POST',
            token,
            json: payload,
          }),
          apiFetch<{ rows: LedgerActivityRow[] }>('/reports/ledger-activity', {
            method: 'POST',
            token,
            json: {
              ...payload,
              date_from: defaultActivityFrom(),
              date_to: defaultActivityTo(),
              approved_only: false,
            },
          }),
          Promise.all([
            apiFetch<ReconciliationPreviewOut>('/reports/reconciliations/preview-totals', { token }),
            apiFetch<ClientAccountReconciliationOut[]>('/reports/reconciliations', { token }),
          ]),
        ])
        setExceptions(exc)
        setRecentApprovedInvoices(recent.rows ?? [])
        setActivityRows(act.rows ?? [])
        setRecPreview(rec[0])
        setRecRows(rec[1])
      }
    } catch (e) {
      setErr((e as ApiError)?.message ?? 'Could not load accounts data')
    } finally {
      setBusy(false)
    }
  }, [token, loadFeeEarners, loadLedgerPermissions])

  const reloadQueue = useCallback(async () => {
    if (!feeEarnerIds.length) return
    const payload = { fee_earner_user_ids: feeEarnerIds }
    const [exc, recent] = await Promise.all([
      apiFetch<ExceptionsPayload>('/reports/exceptions', { method: 'POST', token, json: payload }),
      apiFetch<{ rows: RecentApprovedInvoiceRow[] }>('/reports/recent-approved-invoices', {
        method: 'POST',
        token,
        json: payload,
      }),
    ])
    setExceptions(exc)
    setRecentApprovedInvoices(recent.rows ?? [])
  }, [token, feeEarnerIds])

  const reloadActivity = useCallback(async () => {
    if (!feeEarnerIds.length) return
    const payload = { fee_earner_user_ids: feeEarnerIds }
    const act = await apiFetch<{ rows: LedgerActivityRow[] }>('/reports/ledger-activity', {
      method: 'POST',
      token,
      json: {
        ...payload,
        date_from: defaultActivityFrom(),
        date_to: defaultActivityTo(),
        approved_only: false,
      },
    })
    setActivityRows(act.rows ?? [])
  }, [token, feeEarnerIds])

  useEffect(() => {
    void refreshAll()
  }, [refreshAll])

  useEffect(() => {
    const q = caseSearch.trim()
    if (q.length < 2) {
      setCaseResults([])
      return
    }
    const t = window.setTimeout(() => {
      setCaseSearchBusy(true)
      void fetchCaseSearch(token, { q, limit: 12 })
        .then(setCaseResults)
        .catch(() => setCaseResults([]))
        .finally(() => setCaseSearchBusy(false))
    }, 250)
    return () => window.clearTimeout(t)
  }, [caseSearch, token])

  const pendingLedger = exceptions?.pending_ledger_approvals ?? []
  const filteredPendingLedger = useMemo(
    () =>
      pendingLedger.filter((r) =>
        matchesPendingLedgerFilters(r, pendingLedgerAccountFilter, pendingLedgerDirectionFilter),
      ),
    [pendingLedger, pendingLedgerAccountFilter, pendingLedgerDirectionFilter],
  )
  const pendingInvoices = exceptions?.pending_invoices ?? []
  const exceptionCount = useMemo(() => {
    if (!exceptions) return 0
    return (
      (exceptions.negative_client_balance?.length ?? 0) +
      (exceptions.client_balance_closed_archived?.length ?? 0)
    )
  }, [exceptions])

  const latestReconcile = recRows[0] ?? null

  const canApproveInvoices = ledgerPerm?.can_approve_invoices ?? false

  function canApprovePendingRow(row: ExceptionLedgerRow): boolean {
    return canApprovePendingLedgerRow(row, ledgerPerm)
  }

  async function approveLedgerPosting(caseId: string, pairId: string) {
    const key = `ledger:${caseId}:${pairId}`
    setActionKey(key)
    setErr(null)
    try {
      await apiFetch(`/cases/${caseId}/ledger/approve/${pairId}`, { method: 'POST', token })
      await reloadQueue()
      await reloadActivity()
    } catch (e) {
      setErr((e as ApiError)?.message ?? 'Could not approve posting')
    } finally {
      setActionKey(null)
    }
  }

  async function rejectLedgerPosting(caseId: string, pairId: string) {
    const key = `ledger:${caseId}:${pairId}`
    setActionKey(key)
    setErr(null)
    try {
      await apiFetch(`/cases/${caseId}/ledger/pairs/${pairId}`, { method: 'DELETE', token })
      setRejectLedger(null)
      await reloadQueue()
      await reloadActivity()
    } catch (e) {
      setErr((e as ApiError)?.message ?? 'Could not reject posting')
    } finally {
      setActionKey(null)
    }
  }

  function openEditLedger(row: ExceptionLedgerRow) {
    const caseId = row.case_id ?? ''
    if (!caseId) return
    setEditLedger({
      caseId,
      pairId: row.pair_id,
      amountPence: row.amount_pence,
      description: row.description,
      reference: row.reference ?? '',
      isAnticipated: Boolean(row.is_anticipated),
      anticipatedForDate: row.anticipated_for_date ?? '',
    })
  }

  async function approveInvoice(caseId: string, invoiceId: string) {
    const key = `invoice:${caseId}:${invoiceId}`
    setActionKey(key)
    setErr(null)
    try {
      await apiFetch(`/cases/${caseId}/invoices/${invoiceId}/approve`, { method: 'POST', token })
      await reloadQueue()
    } catch (e) {
      setErr((e as ApiError)?.message ?? 'Could not approve invoice')
    } finally {
      setActionKey(null)
    }
  }

  return (
    <div className="mainMenuShell mainMenuShell--mainMenu">
      <div className="card casesTableCard reportsPageShell accountsPageShell">
        <div className="reportsPageHeader">
          <h1 className="reportsPageTitle">Accounts</h1>
          <p className="muted reportsPageLead" style={{ marginBottom: 16 }}>
            Firm-wide client and office account desk for cashiers. Review approvals, exceptions, and recent ledger
            activity across all fee earners.
            {me?.display_name ? ` Signed in as ${me.display_name}.` : null}
          </p>

          {err ? <div className="error">{err}</div> : null}

          <div className="accountsSummaryGrid">
            <div className="accountsSummaryCard">
              <div className="accountsSummaryLabel">Pending ledger approvals</div>
              <div className="accountsSummaryValue">{pendingLedger.length}</div>
            </div>
            <div className="accountsSummaryCard">
              <div className="accountsSummaryLabel">Pending invoices</div>
              <div className="accountsSummaryValue">{pendingInvoices.length}</div>
            </div>
            <div className="accountsSummaryCard">
              <div className="accountsSummaryLabel">Other exceptions</div>
              <div className="accountsSummaryValue">{exceptionCount}</div>
            </div>
            <div className="accountsSummaryCard">
              <div className="accountsSummaryLabel">Client ledger total</div>
              <div
                className={[
                  'accountsSummaryValue',
                  'accountsSummaryValue--money',
                  recPreview ? ledgerTotalToneClass(recPreview.ledger_client_total_pence) : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
              >
                {recPreview ? formatMoneyPence(recPreview.ledger_client_total_pence) : '—'}
              </div>
            </div>
            <div className="accountsSummaryCard">
              <div className="accountsSummaryLabel">Office ledger total</div>
              <div
                className={[
                  'accountsSummaryValue',
                  'accountsSummaryValue--money',
                  recPreview ? ledgerTotalToneClass(recPreview.ledger_office_total_pence) : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
              >
                {recPreview ? formatMoneyPence(recPreview.ledger_office_total_pence) : '—'}
              </div>
            </div>
          </div>

          <div className="accountsMatterLookup">
            <label className="accountsMatterLookupLabel">
              <span className="muted">Find matter</span>
              <input
                type="search"
                value={caseSearch}
                onChange={(e) => setCaseSearch(e.target.value)}
                placeholder="Reference, client, or description…"
                autoComplete="off"
              />
            </label>
            {caseSearchBusy ? <span className="muted accountsMatterLookupHint">Searching…</span> : null}
            {caseResults.length > 0 ? (
              <ul className="accountsMatterResults">
                {caseResults.map((c) => (
                  <li key={c.id}>
                    <button type="button" className="accountsMatterResultBtn" onClick={() => onOpenCase(c.id)}>
                      <strong>{c.case_number}</strong>
                      <span>
                        {[c.client_name, c.matter_description].filter(Boolean).join(' — ')}
                      </span>
                    </button>
                    <button type="button" className="btn btn--small" onClick={() => openLedgerWindow(c.id)}>
                      Open ledger
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>

          <div className="accountsToolbar">
            <div className="accountsTabSelect">
              {TAB_OPTIONS.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  className={`accountsTabBtn${tab === o.value ? ' accountsTabBtn--active' : ''}`}
                  onClick={() => setTab(o.value)}
                >
                  {o.label}
                  {o.value === 'queue' && pendingLedger.length + pendingInvoices.length > 0
                    ? ` (${pendingLedger.length + pendingInvoices.length})`
                    : null}
                  {o.value === 'exceptions' && exceptionCount > 0 ? ` (${exceptionCount})` : null}
                </button>
              ))}
            </div>
            <button type="button" className="btn" disabled={busy} onClick={() => void refreshAll()}>
              Refresh
            </button>
          </div>
        </div>

        <div className="reportsPageBody accountsPageBody">
          {tab === 'queue' ? (
            <section className="reportsSection">
              <h2 className="accountsSectionTitle">Pending ledger approvals</h2>
              <p className="muted" style={{ marginTop: 0 }}>
                Includes anticipated payments awaiting confirmation and other unapproved ledger postings (such as draft
                invoices).
              </p>
              <div className="accountsPendingFilters">
                <label className="accountsPendingFilter">
                  <span className="muted">Account</span>
                  <select
                    value={pendingLedgerAccountFilter}
                    onChange={(e) => setPendingLedgerAccountFilter(e.target.value as PendingLedgerAccountFilter)}
                  >
                    <option value="all">All</option>
                    <option value="client">Client</option>
                    <option value="office">Office</option>
                  </select>
                </label>
                <label className="accountsPendingFilter">
                  <span className="muted">Direction</span>
                  <select
                    value={pendingLedgerDirectionFilter}
                    onChange={(e) =>
                      setPendingLedgerDirectionFilter(e.target.value as PendingLedgerDirectionFilter)
                    }
                  >
                    <option value="all">All</option>
                    <option value="credit">Credits</option>
                    <option value="debit">Debits</option>
                  </select>
                </label>
              </div>
              {filteredPendingLedger.length === 0 ? (
                <p className="muted">No ledger postings awaiting approval for the selected filters.</p>
              ) : (
                <table className="reportsTable">
                  <thead>
                    <tr>
                      <th>Posted</th>
                      <th>Expected</th>
                      <th>Reference</th>
                      <th>Client</th>
                      <th>Matter</th>
                      <th>Description</th>
                      <th>Amount</th>
                      <th>Legs</th>
                      <th>Type</th>
                      <th>Posted by</th>
                      <th aria-label="Actions" />
                    </tr>
                  </thead>
                  <tbody>
                    {filteredPendingLedger.map((r) => {
                      const caseId = r.case_id ?? ''
                      const actionBusy = actionKey === `ledger:${caseId}:${r.pair_id}`
                      return (
                        <tr key={r.pair_id} className={r.is_anticipated ? 'ledgerRow--anticipated' : undefined}>
                          <td>{formatPostedAt(r.posted_at)}</td>
                          <td>{r.is_anticipated ? formatExpectedDate(r.anticipated_for_date) : '—'}</td>
                          <td>{r.case_number}</td>
                          <td>{r.client_name ?? ''}</td>
                          <td>{r.matter_description}</td>
                          <td>{r.description}</td>
                          <td>{formatMoneyPence(r.amount_pence)}</td>
                          <td>{ledgerLegSummary(r)}</td>
                          <td>{r.is_anticipated ? 'Anticipated' : 'Pending'}</td>
                          <td>{r.posted_by_name}</td>
                          <td>
                            <div className="accountsRowActions">
                              {caseId ? (
                                <>
                                  <button type="button" className="btn btn--small" onClick={() => openLedgerWindow(caseId)}>
                                    Ledger
                                  </button>
                                  {canApprovePendingRow(r) ? (
                                    <>
                                      <button
                                        type="button"
                                        className="btn btn--small"
                                        disabled={actionBusy}
                                        onClick={() => openEditLedger(r)}
                                      >
                                        Edit
                                      </button>
                                      <button
                                        type="button"
                                        className="btn btn--small primary"
                                        disabled={actionBusy}
                                        onClick={() => void approveLedgerPosting(caseId, r.pair_id)}
                                      >
                                        Approve
                                      </button>
                                      <button
                                        type="button"
                                        className="btn btn--small"
                                        disabled={actionBusy}
                                        onClick={() => setRejectLedger({ caseId, pairId: r.pair_id })}
                                      >
                                        Reject
                                      </button>
                                    </>
                                  ) : null}
                                </>
                              ) : null}
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              )}

              <h2 className="accountsSectionTitle">Pending invoices</h2>
              {pendingInvoices.length === 0 ? (
                <p className="muted">No invoices awaiting approval.</p>
              ) : (
                <table className="reportsTable">
                  <thead>
                    <tr>
                      <th>Created</th>
                      <th>Reference</th>
                      <th>Client</th>
                      <th>Invoice</th>
                      <th>Total</th>
                      <th>Fee earner</th>
                      <th aria-label="Actions" />
                    </tr>
                  </thead>
                  <tbody>
                    {pendingInvoices.map((r) => {
                      const actionBusy = actionKey === `invoice:${r.case_id}:${r.invoice_id}`
                      return (
                        <tr key={r.invoice_id}>
                          <td>{formatPostedAt(r.created_at)}</td>
                          <td>{r.case_number}</td>
                          <td>{r.client_name ?? ''}</td>
                          <td>{r.invoice_number}</td>
                          <td>{formatMoneyPence(r.total_pence)}</td>
                          <td>{r.fee_earner_name}</td>
                          <td>
                            <div className="accountsRowActions">
                              <button type="button" className="btn btn--small" onClick={() => openLedgerWindow(r.case_id)}>
                                Ledger
                              </button>
                              {canApproveInvoices ? (
                                <button
                                  type="button"
                                  className="btn btn--small primary"
                                  disabled={actionBusy}
                                  onClick={() => void approveInvoice(r.case_id, r.invoice_id)}
                                >
                                  Approve
                                </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
              )}

              <h2 className="accountsSectionTitle">Recent approved invoices</h2>
              <p className="muted" style={{ marginTop: 0 }}>
                Approved invoice documents are saved on each matter under Accounts/Invoices/.
              </p>
              {recentApprovedInvoices.length === 0 ? (
                <p className="muted">No approved invoices yet.</p>
              ) : (
                <table className="reportsTable">
                  <thead>
                    <tr>
                      <th>Approved</th>
                      <th>Reference</th>
                      <th>Client</th>
                      <th>Invoice</th>
                      <th>Total</th>
                      <th aria-label="Actions" />
                    </tr>
                  </thead>
                  <tbody>
                    {recentApprovedInvoices.map((r) => (
                      <tr key={r.invoice_id}>
                        <td>{r.approved_at ? formatPostedAt(r.approved_at) : '—'}</td>
                        <td>{r.case_number}</td>
                        <td>{r.client_name ?? ''}</td>
                        <td>{r.invoice_number}</td>
                        <td>{formatMoneyPence(r.total_pence)}</td>
                        <td>
                          <div className="accountsRowActions">
                            <button
                              type="button"
                              className="btn btn--small"
                              onClick={() =>
                                void downloadInvoiceDocument(
                                  r.case_id,
                                  r.invoice_id,
                                  token,
                                  invoiceDownloadFilename(r.invoice_number),
                                ).catch((e) => setErr((e as Error).message ?? 'Could not download invoice'))
                              }
                            >
                              Download
                            </button>
                            <button type="button" className="btn btn--small" onClick={() => openLedgerWindow(r.case_id)}>
                              Ledger
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          ) : null}

          {tab === 'exceptions' ? (
            <section className="reportsSection">
              <ExceptionBlock
                title="Negative client balance"
                empty={!(exceptions?.negative_client_balance?.length)}
                rows={exceptions?.negative_client_balance ?? []}
                onOpenCase={onOpenCase}
              />
              <ExceptionBlock
                title="Client balance on closed or archived matters"
                empty={!(exceptions?.client_balance_closed_archived?.length)}
                rows={exceptions?.client_balance_closed_archived ?? []}
                onOpenCase={onOpenCase}
              />
            </section>
          ) : null}

          {tab === 'activity' ? (
            <section className="reportsSection">
              <p className="muted" style={{ marginTop: 0 }}>
                Ledger postings from the last 30 days, newest first (all fee earners).
              </p>
              {activityRows.length === 0 ? (
                <p className="muted">No ledger activity in the last 30 days.</p>
              ) : (
                <table className="reportsTable">
                  <thead>
                    <tr>
                      <th>Posted</th>
                      <th>Reference</th>
                      <th>Client</th>
                      <th>Description</th>
                      <th>Amount</th>
                      <th>Status</th>
                      <th>Posted by</th>
                      <th aria-label="Actions" />
                    </tr>
                  </thead>
                  <tbody>
                    {activityRows.map((r) => (
                      <tr key={`${r.pair_id}-${r.posted_at}`}>
                        <td>{formatPostedAt(r.posted_at)}</td>
                        <td>{r.case_number}</td>
                        <td>{r.client_name ?? ''}</td>
                        <td>{r.description}</td>
                        <td>{formatMoneyPence(r.amount_pence)}</td>
                        <td>{r.is_approved ? 'Approved' : 'Pending'}</td>
                        <td>{r.posted_by_name}</td>
                        <td>
                          <button type="button" className="btn btn--small" onClick={() => openLedgerWindow(r.case_id)}>
                            Ledger
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          ) : null}

          {tab === 'reconcile' ? (
            <section className="reportsSection">
              <p className="muted" style={{ marginTop: 0 }}>
                Current firm-wide ledger totals and recent client account reconciliations. Use Reports for the full
                month-end reconcile workflow (bank balance entry, approval, and DOCX export).
              </p>
              {recPreview ? (
                <div className="accountsReconcileTotals">
                  <div>
                    <span className="muted">Client ledger total</span>
                    <strong className={ledgerTotalToneClass(recPreview.ledger_client_total_pence) || undefined}>
                      {formatMoneyPence(recPreview.ledger_client_total_pence)}
                    </strong>
                  </div>
                  <div>
                    <span className="muted">Office ledger total</span>
                    <strong className={ledgerTotalToneClass(recPreview.ledger_office_total_pence) || undefined}>
                      {formatMoneyPence(recPreview.ledger_office_total_pence)}
                    </strong>
                  </div>
                </div>
              ) : null}
              {latestReconcile ? (
                <p style={{ marginTop: 12 }}>
                  Latest reconciliation: <strong>{latestReconcile.period_end_date}</strong> —{' '}
                  {latestReconcile.status === 'approved' ? 'Approved' : 'Draft'} — difference{' '}
                  {formatMoneyPence(latestReconcile.difference_pence)}
                </p>
              ) : (
                <p className="muted" style={{ marginTop: 12 }}>
                  No reconciliations recorded yet.
                </p>
              )}
              <div className="row" style={{ gap: 8, marginTop: 16 }}>
                <button type="button" className="btn primary" onClick={onOpenReportsReconcile}>
                  Open reconcile in Reports
                </button>
              </div>
              {recRows.length > 0 ? (
                <>
                  <h3 className="accountsSectionTitle">Recent reconciliations</h3>
                  <table className="reportsTable">
                    <thead>
                      <tr>
                        <th>Period end</th>
                        <th>Status</th>
                        <th>Client ledger</th>
                        <th>Bank statement</th>
                        <th>Difference</th>
                        <th>Prepared by</th>
                      </tr>
                    </thead>
                    <tbody>
                      {recRows.slice(0, 12).map((r) => (
                        <tr key={r.id}>
                          <td>{r.period_end_date}</td>
                          <td>{r.status === 'approved' ? 'Approved' : 'Draft'}</td>
                          <td>{formatMoneyPence(r.ledger_client_total_pence)}</td>
                          <td>{formatMoneyPence(r.bank_statement_balance_pence)}</td>
                          <td>{formatMoneyPence(r.difference_pence)}</td>
                          <td>{r.prepared_by_name ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              ) : null}
            </section>
          ) : null}
        </div>
      </div>

      <ConfirmModal
        open={rejectLedger !== null}
        title="Reject posting?"
        message="Remove this draft posting from the ledger? It will not affect account balances."
        confirmLabel="Reject"
        cancelLabel="Cancel"
        danger
        busy={actionKey !== null}
        onConfirm={() =>
          rejectLedger && void rejectLedgerPosting(rejectLedger.caseId, rejectLedger.pairId)
        }
        onCancel={() => setRejectLedger(null)}
      />

      {editLedger ? (
        <EditPendingLedgerModal
          caseId={editLedger.caseId}
          token={token}
          pairId={editLedger.pairId}
          amountPence={editLedger.amountPence}
          description={editLedger.description}
          reference={editLedger.reference}
          isAnticipated={editLedger.isAnticipated}
          anticipatedForDate={editLedger.anticipatedForDate}
          open
          onClose={() => setEditLedger(null)}
          onSaved={() => {
            void reloadQueue()
            void reloadActivity()
          }}
        />
      ) : null}
    </div>
  )
}

function ExceptionBlock({
  title,
  empty,
  rows,
  onOpenCase,
}: {
  title: string
  empty: boolean
  rows: ExceptionBalRow[]
  onOpenCase: (caseId: string) => void
}) {
  return (
    <div className="accountsExceptionBlock">
      <h2 className="accountsSectionTitle">{title}</h2>
      {empty ? (
        <p className="muted">None.</p>
      ) : (
        <table className="reportsTable">
          <thead>
            <tr>
              <th>Reference</th>
              <th>Client</th>
              <th>Status</th>
              <th>Client balance</th>
              <th>Office balance</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${title}-${r.case_number}`}>
                <td>{r.case_number}</td>
                <td>{r.client_name ?? ''}</td>
                <td>{r.status_label}</td>
                <td>{formatMoneyPence(r.client_balance_pence)}</td>
                <td>{formatMoneyPence(r.office_balance_pence)}</td>
                <td>
                  {r.case_id ? (
                    <div className="accountsRowActions">
                      <button type="button" className="btn btn--small" onClick={() => onOpenCase(r.case_id!)}>
                        Matter
                      </button>
                      <button type="button" className="btn btn--small" onClick={() => openLedgerWindow(r.case_id!)}>
                        Ledger
                      </button>
                    </div>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
