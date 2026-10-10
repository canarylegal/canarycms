import { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../api'
import type { ApiError } from '../api'
import type { HmlrOrderOut, HmlrSummaryOut } from '../types/hmlr'
import { CaseDocPanelChrome, CaseDocPanelScroll } from './caseDetailChrome'

function penceGb(pence: number): string {
  return `£${(pence / 100).toFixed(2)}`
}

function isReady(state: string): boolean {
  const s = (state || '').trim().toLowerCase()
  return s === 'ready' || s === 'complete' || s === 'completed'
}

type Props = {
  caseId: string
  token: string
  busy: boolean
  setBusy: (v: boolean) => void
  setActionErr: (v: string | null) => void
  backToDocuments: () => void
  onRefresh?: () => void
  onOpenFile?: (fileId: string) => void
}

export function CaseDetailHmlrPanel({
  caseId,
  token,
  busy,
  setBusy,
  setActionErr,
  backToDocuments,
  onRefresh,
  onOpenFile,
}: Props) {
  const [summary, setSummary] = useState<HmlrSummaryOut | null>(null)
  const [titleNumber, setTitleNumber] = useState('')
  const [wantRegister, setWantRegister] = useState(true)
  const [wantPlan, setWantPlan] = useState(true)

  const load = useCallback(async () => {
    const s = await apiFetch<HmlrSummaryOut>(`/cases/${caseId}/land-registry`, { token })
    setSummary(s)
    setTitleNumber((prev) => prev.trim() || s.suggested_title_numbers?.[0] || '')
    return s
  }, [caseId, token])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const s = await apiFetch<HmlrSummaryOut>(`/cases/${caseId}/land-registry`, { token })
        if (cancelled) return
        setSummary(s)
        setTitleNumber((prev) => prev || s.suggested_title_numbers?.[0] || '')
      } catch (e) {
        if (!cancelled) setActionErr((e as ApiError).message ?? 'Failed to load Land Registry')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [caseId, token, setActionErr])

  const place = async () => {
    if (!titleNumber.trim()) {
      setActionErr('Enter a title number')
      return
    }
    if (!wantRegister && !wantPlan) {
      setActionErr('Select register and/or title plan')
      return
    }
    setBusy(true)
    setActionErr(null)
    try {
      await apiFetch<HmlrOrderOut>(`/cases/${caseId}/land-registry/orders`, {
        token,
        method: 'POST',
        json: {
          title_number: titleNumber.trim(),
          want_register: wantRegister,
          want_title_plan: wantPlan,
        },
      })
      await load()
      onRefresh?.()
    } catch (e) {
      setActionErr((e as ApiError).message ?? 'Could not place Land Registry order')
    } finally {
      setBusy(false)
    }
  }

  const syncOrder = async (orderId: string) => {
    setBusy(true)
    setActionErr(null)
    try {
      await apiFetch<HmlrOrderOut>(`/cases/${caseId}/land-registry/orders/${orderId}/sync`, {
        token,
        method: 'POST',
      })
      await load()
      onRefresh?.()
    } catch (e) {
      setActionErr((e as ApiError).message ?? 'Could not sync order')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="caseDocPanelInset caseDocPanelHost stack">
      <CaseDocPanelChrome
        title="Land Registry"
        onClose={backToDocuments}
        closeLabel="Close"
        closeDisabled={busy}
        actions={
          <button
            type="button"
            className="btn primary"
            disabled={busy || !summary?.configured}
            onClick={() => void place()}
          >
            Order official copy
          </button>
        }
      />
      <CaseDocPanelScroll>
        <div className="card stack" style={{ gap: 12 }}>
          {!summary ? (
            <div className="muted">Loading…</div>
          ) : !summary.enabled ? (
            <div className="muted">
              Land Registry is not enabled. An admin can turn it on under Admin → Integrations → Land Registry.
            </div>
          ) : !summary.configured ? (
            <div className="muted">Land Registry is not fully configured yet.</div>
          ) : (
            <>
              {summary.mock_mode ? (
                <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                  Sandbox mock: orders return sample PDFs into the <strong>Land Registry</strong> folder (no Gateway
                  charge). Real stub calls start after the HMLR test SSL certificate is installed.
                </p>
              ) : summary.sandbox ? (
                <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                  Connected to HMLR customer test / stub (no live charges).
                </p>
              ) : (
                <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                  Live Business Gateway — official copy fees apply.
                </p>
              )}

              <div className="stack" style={{ gap: 8 }}>
                <strong>New official copy (title known)</strong>
                {summary.suggested_title_numbers.length > 0 ? (
                  <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                    {summary.suggested_title_numbers.map((t) => (
                      <button
                        key={t}
                        type="button"
                        className="btn"
                        disabled={busy}
                        style={{ fontSize: 12, padding: '4px 8px' }}
                        onClick={() => setTitleNumber(t)}
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                ) : null}
                <label className="stack" style={{ gap: 4 }}>
                  <span>Title number</span>
                  <input
                    className="input"
                    value={titleNumber}
                    disabled={busy}
                    onChange={(e) => setTitleNumber(e.target.value.toUpperCase())}
                    placeholder="e.g. AB123456"
                    autoComplete="off"
                  />
                </label>
                <label className="row" style={{ gap: 8, alignItems: 'center' }}>
                  <input
                    type="checkbox"
                    checked={wantRegister}
                    disabled={busy}
                    onChange={(e) => setWantRegister(e.target.checked)}
                  />
                  <span>Official copy of register</span>
                </label>
                <label className="row" style={{ gap: 8, alignItems: 'center' }}>
                  <input
                    type="checkbox"
                    checked={wantPlan}
                    disabled={busy}
                    onChange={(e) => setWantPlan(e.target.checked)}
                  />
                  <span>Official copy of title plan</span>
                </label>
              </div>

              <div className="stack" style={{ gap: 10 }}>
                <strong>Orders</strong>
                {summary.orders.length === 0 ? (
                  <div className="muted">No Land Registry orders yet.</div>
                ) : (
                  summary.orders.map((o) => (
                    <div
                      key={o.id}
                      style={{ borderTop: '1px solid var(--border)', paddingTop: 10 }}
                      className="stack"
                    >
                      <div className="row" style={{ justifyContent: 'space-between', gap: 8 }}>
                        <strong>{o.title_number}</strong>
                        <span>{o.fee_pence > 0 ? penceGb(o.fee_pence) : '—'}</span>
                      </div>
                      <div className="muted" style={{ fontSize: 13 }}>
                        {o.state}
                        {o.sandbox ? ' · sandbox' : ''}
                        {o.placed_at ? ` · ${new Date(o.placed_at).toLocaleDateString('en-GB')}` : ''}
                      </div>
                      {o.error_message ? <div className="err">{o.error_message}</div> : null}
                      <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                        {o.register_file_id && isReady(o.state) && onOpenFile ? (
                          <button
                            type="button"
                            className="btn"
                            disabled={busy}
                            onClick={() => onOpenFile(o.register_file_id!)}
                          >
                            Open register
                          </button>
                        ) : null}
                        {o.plan_file_id && isReady(o.state) && onOpenFile ? (
                          <button
                            type="button"
                            className="btn"
                            disabled={busy}
                            onClick={() => onOpenFile(o.plan_file_id!)}
                          >
                            Open title plan
                          </button>
                        ) : null}
                        {!isReady(o.state) ? (
                          <button
                            type="button"
                            className="btn"
                            disabled={busy}
                            onClick={() => void syncOrder(o.id)}
                          >
                            Sync
                          </button>
                        ) : null}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </>
          )}
        </div>
      </CaseDocPanelScroll>
    </div>
  )
}
