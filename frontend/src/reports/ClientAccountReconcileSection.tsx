import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch, apiUrl, applyAuthHeaders, type ApiError } from '../api'
import type { ClientAccountReconciliationOut, ReconciliationPreviewOut } from '../types'
import {
  defaultPeriodEndDate,
  formatMoneyPence,
  parsePoundsToPence,
  penceToPoundsInput,
} from './utils'

export function ClientAccountReconcileSection({
  token,
  busy,
  setBusy,
  setErr,
  active,
}: {
  token: string
  busy: boolean
  setBusy: (v: boolean) => void
  setErr: (v: string | null) => void
  active: boolean
}) {
  const [recPeriodEnd, setRecPeriodEnd] = useState(defaultPeriodEndDate)
  const [recBankPounds, setRecBankPounds] = useState('')
  const [recNotes, setRecNotes] = useState('')
  const [recPreview, setRecPreview] = useState<ReconciliationPreviewOut | null>(null)
  const [recRows, setRecRows] = useState<ClientAccountReconciliationOut[]>([])
  const [recSelectedId, setRecSelectedId] = useState<string | null>(null)
  const [recCanApprove, setRecCanApprove] = useState(false)
  const [recSavedMsg, setRecSavedMsg] = useState<string | null>(null)

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
  }, [token, setErr])

  useEffect(() => {
    if (!active) return
    void loadReconciliationData()
  }, [active, loadReconciliationData])

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

  return (
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
  )
}
