import { useEffect, useState } from 'react'
import { apiFetch } from './api'
import type { ApiError } from './api'

export type EditPendingLedgerModalProps = {
  caseId: string
  token: string
  pairId: string
  amountPence: number
  description: string
  reference: string
  isAnticipated: boolean
  anticipatedForDate: string
  open: boolean
  onClose: () => void
  onSaved: () => void
}

export function EditPendingLedgerModal({
  caseId,
  token,
  pairId,
  amountPence,
  description,
  reference,
  isAnticipated,
  anticipatedForDate,
  open,
  onClose,
  onSaved,
}: EditPendingLedgerModalProps) {
  const [amountStr, setAmountStr] = useState('')
  const [desc, setDesc] = useState('')
  const [ref, setRef] = useState('')
  const [expectedDate, setExpectedDate] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setAmountStr((amountPence / 100).toFixed(2))
    setDesc(description)
    setRef(reference)
    setExpectedDate(anticipatedForDate)
    setErr(null)
  }, [open, amountPence, description, reference, anticipatedForDate])

  if (!open) return null

  async function save() {
    setBusy(true)
    setErr(null)
    const penceVal = Math.round(parseFloat(amountStr) * 100)
    if (!amountStr || Number.isNaN(penceVal) || penceVal <= 0) {
      setErr('Enter a valid amount greater than zero.')
      setBusy(false)
      return
    }
    if (!desc.trim()) {
      setErr('Description is required.')
      setBusy(false)
      return
    }
    if (isAnticipated && !expectedDate) {
      setErr('Select the anticipated payment date.')
      setBusy(false)
      return
    }
    try {
      await apiFetch(`/cases/${caseId}/ledger/pairs/${pairId}`, {
        token,
        method: 'PATCH',
        json: {
          amount_pence: penceVal,
          description: desc.trim(),
          reference: ref.trim() || null,
          ...(isAnticipated ? { anticipated_for_date: expectedDate } : {}),
        },
      })
      onSaved()
      onClose()
    } catch (e) {
      setErr((e as ApiError).message ?? 'Could not save changes')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modalOverlay" role="dialog" aria-modal="true" onClick={() => !busy && onClose()}>
      <div className="modal card" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 440 }}>
        <div className="paneHead">
          <h2 style={{ margin: 0, fontSize: 18 }}>Edit pending posting</h2>
          <button type="button" className="btn" disabled={busy} onClick={onClose}>
            Close
          </button>
        </div>
        <div className="stack" style={{ marginTop: 12, gap: 12 }}>
          {err ? <div className="error">{err}</div> : null}
          <label className="field">
            <span>Amount (£)</span>
            <input className="input" value={amountStr} onChange={(e) => setAmountStr(e.target.value)} disabled={busy} />
          </label>
          <label className="field">
            <span>Description</span>
            <input className="input" value={desc} onChange={(e) => setDesc(e.target.value)} disabled={busy} />
          </label>
          <label className="field">
            <span>Reference</span>
            <input className="input" value={ref} onChange={(e) => setRef(e.target.value)} disabled={busy} />
          </label>
          {isAnticipated ? (
            <label className="field">
              <span>Anticipated date</span>
              <input
                className="input"
                type="date"
                value={expectedDate}
                onChange={(e) => setExpectedDate(e.target.value)}
                disabled={busy}
              />
            </label>
          ) : null}
          <div className="row" style={{ justifyContent: 'flex-end', gap: 8 }}>
            <button type="button" className="btn" disabled={busy} onClick={onClose}>
              Cancel
            </button>
            <button type="button" className="btn primary" disabled={busy} onClick={() => void save()}>
              {busy ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
