import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../api'
import type { ApiError } from '../api'
import type {
  CaseraAvailablePackOut,
  CaseraAvailableProductOut,
  CaseraConveyancingDetails,
  CaseraCreateOrderOut,
  CaseraOrderOut,
  CaseraPrefillOut,
  CaseraRiskBadgeOut,
  CaseraSearchesSummaryOut,
} from '../types/casera'
import { CaseDocPanelChrome, CaseDocPanelScroll } from './caseDetailChrome'

function isCompleteState(state: string): boolean {
  const s = (state || '').trim().toLowerCase()
  return s === 'completed' || s === 'complete' || s === 'returned'
}

function penceGb(pence: number): string {
  return `£${(pence / 100).toFixed(2)}`
}

const ORDER_CATEGORIES: {
  id: string
  label: string
  blurb: string
  /** When true, category is shown but cannot be ordered yet. */
  stub?: boolean
}[] = [
  { id: 'Conveyancing', label: 'Conveyancing', blurb: 'Local authority, water, environmental and packs' },
  { id: 'Aml', label: 'AML / KYC', blurb: 'Individual and business checks', stub: true },
  { id: 'DocRetrieval', label: 'Document retrieval', blurb: 'Title register and plan', stub: true },
  { id: 'CompanySearch', label: 'Company search', blurb: 'Company search reports', stub: true },
  { id: 'LenderCheck', label: 'Lender check', blurb: 'Lender checks', stub: true },
]

type WizardStep = 'list' | 'category' | 'confirm' | 'pick'

type Props = {
  caseId: string
  token: string
  busy: boolean
  setBusy: (v: boolean) => void
  setActionErr: (v: string | null) => void
  backToDocuments: () => void
  onPlaced: () => void
  onRefresh?: () => void
  onOpenSearchFile?: (fileId: string) => void
}

export function CaseDetailSearchesPanel({
  caseId,
  token,
  busy,
  setBusy,
  setActionErr,
  backToDocuments,
  onPlaced,
  onRefresh,
  onOpenSearchFile,
}: Props) {
  const [summary, setSummary] = useState<CaseraSearchesSummaryOut | null>(null)
  const [step, setStep] = useState<WizardStep>('list')
  const [category, setCategory] = useState('Conveyancing')
  const [details, setDetails] = useState<CaseraConveyancingDetails | null>(null)
  const [fromProperty, setFromProperty] = useState(false)
  const [draftOrderId, setDraftOrderId] = useState<string | null>(null)
  const [availableProducts, setAvailableProducts] = useState<CaseraAvailableProductOut[]>([])
  const [availablePacks, setAvailablePacks] = useState<CaseraAvailablePackOut[]>([])
  const [selectedProducts, setSelectedProducts] = useState<Set<string>>(() => new Set())
  const [selectedPacks, setSelectedPacks] = useState<Set<string>>(() => new Set())
  const [productFilter, setProductFilter] = useState('')
  const [riskBadges, setRiskBadges] = useState<CaseraRiskBadgeOut[]>([])
  const [titleNumbersText, setTitleNumbersText] = useState('')
  const [orderReference, setOrderReference] = useState('')
  const [referenceLocked, setReferenceLocked] = useState(false)

  const applyReferenceFrom = (suggested?: string | null, linked?: string | null) => {
    const existing = (linked || '').trim()
    if (existing) {
      setOrderReference(existing)
      setReferenceLocked(true)
      return
    }
    setOrderReference((suggested || '').trim())
    setReferenceLocked(false)
  }

  const loadSummary = useCallback(async () => {
    const s = await apiFetch<CaseraSearchesSummaryOut>(`/cases/${caseId}/searches`, { token })
    setSummary(s)
    return s
  }, [caseId, token])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const s = await apiFetch<CaseraSearchesSummaryOut>(`/cases/${caseId}/searches`, { token })
        if (!cancelled) setSummary(s)
      } catch (e) {
        if (!cancelled) setActionErr((e as ApiError).message ?? 'Failed to load searches')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [caseId, token, setActionErr])

  const resetDraft = () => {
    setDraftOrderId(null)
    setAvailableProducts([])
    setAvailablePacks([])
    setSelectedProducts(new Set())
    setSelectedPacks(new Set())
    setProductFilter('')
    setRiskBadges([])
  }

  const applyDraftFromOrder = (out: CaseraCreateOrderOut) => {
    setDraftOrderId(out.order.id)
    setAvailableProducts(out.products)
    setAvailablePacks(out.packs)
    setSelectedProducts(new Set(out.order.selected_product_ids || []))
    setSelectedPacks(new Set(out.order.selected_pack_ids || []))
    setProductFilter('')
    setRiskBadges(out.risk_badges || [])
  }

  const coveredByPacks = useMemo(() => {
    const ids = new Set<string>()
    for (const pack of availablePacks) {
      if (!selectedPacks.has(pack.id)) continue
      for (const pid of pack.product_ids || []) ids.add(pid)
    }
    return ids
  }, [availablePacks, selectedPacks])

  const recommendedProductIds = useMemo(() => {
    const ids = new Set<string>()
    for (const b of riskBadges) {
      for (const pid of b.product_ids || []) ids.add(pid)
    }
    return ids
  }, [riskBadges])

  const persistDraftSelection = async () => {
    if (!draftOrderId) return
    const products = [...selectedProducts].filter((id) => !coveredByPacks.has(id))
    await apiFetch(`/cases/${caseId}/searches/orders/${draftOrderId}/selection`, {
      token,
      method: 'PUT',
      json: {
        products,
        packs: [...selectedPacks],
      },
    })
  }

  const openWizard = () => {
    setActionErr(null)
    setCategory('Conveyancing')
    resetDraft()
    applyReferenceFrom(summary?.suggested_reference, summary?.casera_reference)
    setStep('category')
  }

  const loadPrefill = async () => {
    const pre = await apiFetch<CaseraPrefillOut>(`/cases/${caseId}/searches/prefill`, { token })
    setDetails(pre.conveyancing)
    setFromProperty(pre.from_property)
    setTitleNumbersText((pre.conveyancing.title_numbers || []).join(', '))
    // Keep the reference chosen on the category step unless Casera already linked this matter.
    const existing = (pre.casera_reference || '').trim()
    if (existing) {
      setOrderReference(existing)
      setReferenceLocked(true)
    }
  }

  const createOrder = async (opts: {
    category: string
    conveyancing?: CaseraConveyancingDetails
  }) => {
    const ref = orderReference.trim()
    if (!referenceLocked && !ref) {
      throw Object.assign(new Error('Enter an order reference'), { message: 'Enter an order reference' })
    }
    const out = await apiFetch<CaseraCreateOrderOut>(`/cases/${caseId}/searches/orders`, {
      token,
      method: 'POST',
      json: {
        category: opts.category,
        conveyancing_type: opts.conveyancing?.type || 'Residential',
        conveyancing: opts.conveyancing ?? null,
        reference: referenceLocked ? null : ref,
      },
    })
    applyDraftFromOrder(out)
    setStep('pick')
    await loadSummary()
  }

  const continueFromCategory = async () => {
    const chosen = ORDER_CATEGORIES.find((c) => c.id === category)
    if (chosen?.stub) {
      setActionErr(`${chosen.label} ordering is not available yet — use Conveyancing for now.`)
      return
    }
    if (!referenceLocked && !orderReference.trim()) {
      setActionErr('Enter an order reference')
      return
    }
    setBusy(true)
    setActionErr(null)
    try {
      if (category === 'Conveyancing') {
        await loadPrefill()
        setStep('confirm')
      } else {
        await createOrder({ category })
      }
    } catch (e) {
      setActionErr((e as ApiError).message ?? 'Could not continue')
    } finally {
      setBusy(false)
    }
  }

  const submitDetails = async () => {
    if (!details) return
    if (!referenceLocked && !orderReference.trim()) {
      setActionErr('Enter an order reference')
      return
    }
    setBusy(true)
    setActionErr(null)
    try {
      const conveyancing: CaseraConveyancingDetails = {
        ...details,
        title_numbers: titleNumbersText
          .split(/[,;\n]+/)
          .map((t) => t.trim())
          .filter(Boolean),
      }
      await createOrder({ category: 'Conveyancing', conveyancing })
    } catch (e) {
      setActionErr((e as ApiError).message ?? 'Could not create search order')
    } finally {
      setBusy(false)
    }
  }

  const referenceField = (
    <label className="stack" style={{ gap: 4 }}>
      <span>Order reference</span>
      <input
        className="input"
        value={orderReference}
        disabled={busy || referenceLocked}
        maxLength={200}
        autoComplete="off"
        onChange={(e) => setOrderReference(e.target.value)}
        placeholder="Matter reference sent to Casera"
      />
      <span className="muted" style={{ fontSize: 12 }}>
        {referenceLocked
          ? 'Already set on the Casera case for this matter.'
          : 'Defaults to the matter number. Edit before the first order is created.'}
      </span>
    </label>
  )

  const isDraft = (state: string, placedAt?: string | null) =>
    !placedAt && (state || '').trim().toLowerCase() === 'draft'

  const resumeDraft = async (orderId: string, orderCategory: string) => {
    setBusy(true)
    setActionErr(null)
    try {
      const out = await apiFetch<CaseraCreateOrderOut>(
        `/cases/${caseId}/searches/orders/${orderId}/resume`,
        { token },
      )
      setCategory(orderCategory)
      applyDraftFromOrder(out)
      setStep('pick')
    } catch (e) {
      setActionErr((e as ApiError).message ?? 'Could not resume draft order')
    } finally {
      setBusy(false)
    }
  }

  const syncOrder = async (orderId: string) => {
    setBusy(true)
    setActionErr(null)
    try {
      await apiFetch<CaseraOrderOut>(`/cases/${caseId}/searches/orders/${orderId}/sync`, {
        token,
        method: 'POST',
      })
      await loadSummary()
      onRefresh?.()
    } catch (e) {
      setActionErr((e as ApiError).message ?? 'Could not sync with Casera')
    } finally {
      setBusy(false)
    }
  }

  const discardDraft = async (orderId: string) => {
    setBusy(true)
    setActionErr(null)
    try {
      await apiFetch(`/cases/${caseId}/searches/orders/${orderId}`, {
        token,
        method: 'DELETE',
      })
      await loadSummary()
    } catch (e) {
      setActionErr((e as ApiError).message ?? 'Could not discard draft')
    } finally {
      setBusy(false)
    }
  }

  const placeSelected = async () => {
    if (!draftOrderId) return
    if (selectedProducts.size === 0 && selectedPacks.size === 0) {
      setActionErr('Select at least one product or pack')
      return
    }
    setBusy(true)
    setActionErr(null)
    try {
      const products = [...selectedProducts].filter((id) => !coveredByPacks.has(id))
      await apiFetch(`/cases/${caseId}/searches/orders/${draftOrderId}/products`, {
        token,
        method: 'PUT',
        json: {
          products,
          packs: [...selectedPacks],
        },
      })
      await apiFetch(`/cases/${caseId}/searches/orders/${draftOrderId}/place`, {
        token,
        method: 'POST',
      })
      setStep('list')
      resetDraft()
      await loadSummary()
      onPlaced()
    } catch (e) {
      setActionErr((e as ApiError).message ?? 'Could not place order')
    } finally {
      setBusy(false)
    }
  }

  const goBack = () => {
    if (step === 'pick') {
      void (async () => {
        setBusy(true)
        setActionErr(null)
        try {
          await persistDraftSelection()
          setStep('list')
          resetDraft()
          await loadSummary()
        } catch (e) {
          setActionErr((e as ApiError).message ?? 'Could not save selection')
        } finally {
          setBusy(false)
        }
      })()
      return
    }
    if (step === 'confirm') {
      setStep('category')
      return
    }
    if (step === 'category') {
      setStep('list')
      return
    }
    backToDocuments()
  }

  const filterQ = productFilter.trim().toLowerCase()

  const filteredPacks = useMemo(() => {
    if (!filterQ) return availablePacks
    return availablePacks.filter((pack) => {
      const hay = [
        pack.name,
        ...(pack.product_names || []),
        ...(pack.product_ids || []),
      ]
        .join(' ')
        .toLowerCase()
      return hay.includes(filterQ)
    })
  }, [availablePacks, filterQ])

  const filteredProducts = useMemo(() => {
    if (!filterQ) return availableProducts
    return availableProducts.filter((p) => {
      const hay = [p.name, p.group, p.subcategory, p.description].filter(Boolean).join(' ').toLowerCase()
      return hay.includes(filterQ)
    })
  }, [availableProducts, filterQ])

  const togglePack = (packId: string, checked: boolean) => {
    const pack = availablePacks.find((p) => p.id === packId)
    setSelectedPacks((prev) => {
      const next = new Set(prev)
      if (checked) next.add(packId)
      else next.delete(packId)
      return next
    })
    if (checked && pack) {
      setSelectedProducts((prev) => {
        const next = new Set(prev)
        for (const pid of pack.product_ids || []) next.delete(pid)
        return next
      })
    }
  }

  const toggleProduct = (productId: string, checked: boolean) => {
    if (coveredByPacks.has(productId)) return
    setSelectedProducts((prev) => {
      const next = new Set(prev)
      if (checked) next.add(productId)
      else next.delete(productId)
      return next
    })
  }

  const selectionTotal = useMemo(() => {
    let total = 0
    for (const p of availableProducts) {
      if (selectedProducts.has(p.id) && !coveredByPacks.has(p.id) && p.price_pence != null) {
        total += p.price_pence
      }
    }
    for (const pack of availablePacks) {
      if (selectedPacks.has(pack.id) && pack.price_pence != null) total += pack.price_pence
    }
    return total
  }, [availableProducts, availablePacks, selectedProducts, selectedPacks, coveredByPacks])

  const title =
    step === 'list'
      ? 'Searches'
      : step === 'category'
        ? 'Order type'
        : step === 'confirm'
          ? 'Confirm property details'
          : 'Select searches'

  return (
    <div className="caseDocPanelInset caseDocPanelHost stack">
      <CaseDocPanelChrome
        title={title}
        onClose={goBack}
        closeLabel={step === 'list' ? 'Close' : 'Back'}
        closeDisabled={busy}
        actions={
          step === 'list' ? (
            <button
              type="button"
              className="btn primary"
              disabled={busy || !summary?.configured}
              onClick={openWizard}
            >
              Place new order
            </button>
          ) : step === 'category' ? (
            <button
              type="button"
              className="btn primary"
              disabled={busy || Boolean(ORDER_CATEGORIES.find((c) => c.id === category)?.stub)}
              onClick={() => void continueFromCategory()}
            >
              Continue
            </button>
          ) : step === 'confirm' ? (
            <button type="button" className="btn primary" disabled={busy} onClick={() => void submitDetails()}>
              Continue
            </button>
          ) : (
            <button type="button" className="btn primary" disabled={busy} onClick={() => void placeSelected()}>
              Place order{selectionTotal > 0 ? ` · ${penceGb(selectionTotal)}` : ''}
            </button>
          )
        }
      />
      <CaseDocPanelScroll>
        <div className="card stack" style={{ gap: 12 }}>
          {step === 'list' ? (
            <>
              {!summary ? (
                <div className="muted">Loading…</div>
              ) : (summary.provider || 'none') === 'none' ? (
                <div className="muted">
                  No search provider configured. An admin can choose one under Admin → Integrations → Searches.
                </div>
              ) : !summary.configured ? (
                <div className="muted">
                  {(summary.provider || 'casera') === 'casera'
                    ? 'Casera is selected but not fully configured. An admin can finish setup under Admin → Integrations → Searches.'
                    : 'The selected search provider is not fully configured. An admin can finish setup under Admin → Integrations → Searches.'}
                </div>
              ) : (
                <>
                  <div>
                    <div className="muted" style={{ fontSize: 13 }}>
                      Current orders total
                    </div>
                    <div style={{ fontSize: 22, fontWeight: 600 }}>{penceGb(summary.total_pence)}</div>
                  </div>
                  {summary.orders.length === 0 ? (
                    <div className="muted">No search orders yet.</div>
                  ) : (
                    <div className="stack" style={{ gap: 10 }}>
                      {summary.orders.map((o) => {
                        const draft = isDraft(o.state, o.placed_at)
                        return (
                          <div
                            key={o.id}
                            style={{
                              borderTop: '1px solid var(--border)',
                              paddingTop: 10,
                            }}
                          >
                            <div className="row" style={{ justifyContent: 'space-between', gap: 8 }}>
                              <strong>{o.category}</strong>
                              <span>{penceGb(o.total_pence)}</span>
                            </div>
                            <div className="muted" style={{ fontSize: 13 }}>
                              {o.state}
                              {o.placed_at
                                ? ` · placed ${new Date(o.placed_at).toLocaleDateString('en-GB')}`
                                : ''}
                            </div>
                            {o.products.length > 0 ? (
                              <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
                                {o.products.map((p) => {
                                  const fileIds =
                                    p.file_ids && p.file_ids.length > 0
                                      ? p.file_ids
                                      : p.file_id
                                        ? [p.file_id]
                                        : []
                                  const canOpen =
                                    fileIds.length > 0 &&
                                    isCompleteState(p.state) &&
                                    typeof onOpenSearchFile === 'function'
                                  return (
                                    <li key={p.id}>
                                      {canOpen ? (
                                        <span>
                                          <button
                                            type="button"
                                            className="linkish"
                                            style={{
                                              background: 'none',
                                              border: 'none',
                                              padding: 0,
                                              color: 'inherit',
                                              textDecoration: 'underline',
                                              cursor: 'pointer',
                                              font: 'inherit',
                                            }}
                                            disabled={busy}
                                            onClick={() => onOpenSearchFile?.(fileIds[0]!)}
                                          >
                                            {p.name}
                                          </button>
                                          {fileIds.length > 1
                                            ? fileIds.slice(1).map((fid, i) => (
                                                <button
                                                  key={fid}
                                                  type="button"
                                                  className="linkish"
                                                  style={{
                                                    background: 'none',
                                                    border: 'none',
                                                    padding: 0,
                                                    marginLeft: 6,
                                                    color: 'inherit',
                                                    textDecoration: 'underline',
                                                    cursor: 'pointer',
                                                    font: 'inherit',
                                                    fontSize: 12,
                                                  }}
                                                  disabled={busy}
                                                  onClick={() => onOpenSearchFile?.(fid)}
                                                >
                                                  file {i + 2}
                                                </button>
                                              ))
                                            : null}
                                        </span>
                                      ) : (
                                        p.name
                                      )}{' '}
                                      — {p.state}
                                      {p.due_at && !isCompleteState(p.state)
                                        ? ` · ETA ${new Date(p.due_at).toLocaleDateString('en-GB')}`
                                        : ''}
                                    </li>
                                  )
                                })}
                              </ul>
                            ) : null}
                            {draft ? (
                              <div className="row" style={{ gap: 8, marginTop: 8 }}>
                                <button
                                  type="button"
                                  className="btn primary"
                                  disabled={busy}
                                  onClick={() => void resumeDraft(o.id, o.category)}
                                >
                                  Continue
                                </button>
                                <button
                                  type="button"
                                  className="btn"
                                  disabled={busy}
                                  onClick={() => void discardDraft(o.id)}
                                >
                                  Discard
                                </button>
                              </div>
                            ) : (
                              <div className="row" style={{ gap: 8, marginTop: 8 }}>
                                <button
                                  type="button"
                                  className="btn"
                                  disabled={busy}
                                  onClick={() => void syncOrder(o.id)}
                                >
                                  Sync with Casera
                                </button>
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  )}
                </>
              )}
            </>
          ) : null}

          {step === 'category' ? (
            <div className="stack" style={{ gap: 8 }}>
              <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                Choose the type of Casera order. Available products depend on the category.
              </p>
              {referenceField}
              {ORDER_CATEGORIES.map((c) => (
                <label
                  key={c.id}
                  className="row"
                  style={{
                    gap: 10,
                    alignItems: 'flex-start',
                    padding: '10px 12px',
                    border: '1px solid var(--border)',
                    borderRadius: 6,
                    cursor: c.stub ? 'not-allowed' : 'pointer',
                    opacity: c.stub ? 0.65 : 1,
                    background: category === c.id ? 'rgba(0,0,0,0.03)' : undefined,
                  }}
                >
                  <input
                    type="radio"
                    name="casera-category"
                    checked={category === c.id}
                    disabled={busy || Boolean(c.stub)}
                    onChange={() => setCategory(c.id)}
                    style={{ marginTop: 3 }}
                  />
                  <span>
                    <strong>
                      {c.label}
                      {c.stub ? ' (coming soon)' : ''}
                    </strong>
                    <div className="muted" style={{ fontSize: 13 }}>
                      {c.stub ? 'UI stub — ordering flow not wired yet.' : c.blurb}
                    </div>
                  </span>
                </label>
              ))}
            </div>
          ) : null}

          {step === 'confirm' && details ? (
            <div className="stack" style={{ gap: 10 }}>
              {fromProperty ? (
                <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                  Prefill from Property details — confirm or edit before continuing.
                </p>
              ) : (
                <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                  No Property details found — enter the address and title numbers below.
                </p>
              )}
              {referenceField}
              <label className="stack" style={{ gap: 4 }}>
                <span>Type</span>
                <select
                  className="input"
                  value={details.type}
                  disabled={busy}
                  onChange={(e) => setDetails({ ...details, type: e.target.value })}
                >
                  <option value="Residential">Residential</option>
                  <option value="Commercial">Commercial</option>
                </select>
              </label>
              <label className="row" style={{ gap: 8, alignItems: 'center' }}>
                <input
                  type="checkbox"
                  checked={details.new_build}
                  disabled={busy}
                  onChange={(e) => setDetails({ ...details, new_build: e.target.checked })}
                />
                <span>New build</span>
              </label>
              <label className="stack" style={{ gap: 4 }}>
                <span>Title numbers (comma-separated)</span>
                <input
                  className="input"
                  value={titleNumbersText}
                  disabled={busy}
                  onChange={(e) => setTitleNumbersText(e.target.value)}
                />
              </label>
              <label className="stack" style={{ gap: 4 }}>
                <span>Building / house</span>
                <input
                  className="input"
                  value={details.building_identifier ?? ''}
                  disabled={busy}
                  onChange={(e) => setDetails({ ...details, building_identifier: e.target.value })}
                />
              </label>
              <label className="stack" style={{ gap: 4 }}>
                <span>Street</span>
                <input
                  className="input"
                  value={details.street ?? ''}
                  disabled={busy}
                  onChange={(e) => setDetails({ ...details, street: e.target.value })}
                />
              </label>
              <label className="stack" style={{ gap: 4 }}>
                <span>Town / city</span>
                <input
                  className="input"
                  value={details.town_city ?? ''}
                  disabled={busy}
                  onChange={(e) => setDetails({ ...details, town_city: e.target.value })}
                />
              </label>
              <label className="stack" style={{ gap: 4 }}>
                <span>Postcode</span>
                <input
                  className="input"
                  value={details.postcode ?? ''}
                  disabled={busy}
                  onChange={(e) => setDetails({ ...details, postcode: e.target.value })}
                />
              </label>
            </div>
          ) : null}

          {step === 'pick' ? (
            <div className="stack" style={{ gap: 12 }}>
              <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                Category: {ORDER_CATEGORIES.find((c) => c.id === category)?.label ?? category}
              </p>
              {riskBadges.length > 0 ? (
                <div className="stack" style={{ gap: 6 }}>
                  <strong>Property risks</strong>
                  <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                    Casera flagged the following for this property — consider the matching products below.
                  </p>
                  <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                    {riskBadges.map((b) => (
                      <span
                        key={b.key}
                        title={b.detail || undefined}
                        style={{
                          display: 'inline-block',
                          padding: '3px 8px',
                          border: '1px solid var(--border)',
                          borderRadius: 4,
                          fontSize: 12,
                          background: 'rgba(180, 90, 40, 0.08)',
                        }}
                      >
                        {b.label}
                        {b.level ? ` · ${b.level}` : ''}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}
              <label className="stack" style={{ gap: 4 }}>
                <span className="muted" style={{ fontSize: 13 }}>
                  Filter
                </span>
                <input
                  className="input"
                  value={productFilter}
                  disabled={busy}
                  placeholder="Search packs and products"
                  onChange={(e) => setProductFilter(e.target.value)}
                />
              </label>
              {filteredPacks.length > 0 ? (
                <div className="stack" style={{ gap: 6 }}>
                  <strong>Packs</strong>
                  {filteredPacks.map((pack) => {
                    const contents =
                      (pack.product_names && pack.product_names.length > 0
                        ? pack.product_names
                        : pack.product_ids) || []
                    return (
                      <label key={pack.id} className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
                        <input
                          type="checkbox"
                          checked={selectedPacks.has(pack.id)}
                          disabled={busy}
                          onChange={(e) => togglePack(pack.id, e.target.checked)}
                        />
                        <span>
                          {pack.name}
                          {pack.price_pence != null ? ` — ${penceGb(pack.price_pence)}` : ''}
                          {contents.length > 0 ? (
                            <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
                              Includes: {contents.join(', ')}
                            </div>
                          ) : null}
                        </span>
                      </label>
                    )
                  })}
                </div>
              ) : availablePacks.length > 0 && filterQ ? (
                <div className="muted" style={{ fontSize: 13 }}>
                  No packs match this filter.
                </div>
              ) : null}
              {filteredProducts.length > 0 ? (
                <div className="stack" style={{ gap: 6 }}>
                  <strong>Products</strong>
                  {filteredProducts.map((p) => {
                    const inPack = coveredByPacks.has(p.id)
                    return (
                      <label
                        key={p.id}
                        className="row"
                        style={{
                          gap: 8,
                          alignItems: 'flex-start',
                          opacity: inPack ? 0.55 : 1,
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={inPack || selectedProducts.has(p.id)}
                          disabled={busy || inPack}
                          onChange={(e) => toggleProduct(p.id, e.target.checked)}
                        />
                        <span>
                          {p.name}
                          {p.price_pence != null ? ` — ${penceGb(p.price_pence)}` : ''}
                          {recommendedProductIds.has(p.id) ? (
                            <span className="muted" style={{ fontSize: 12, marginLeft: 6 }}>
                              (recommended)
                            </span>
                          ) : null}
                          {inPack ? (
                            <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
                              Included in a selected pack
                            </div>
                          ) : null}
                        </span>
                      </label>
                    )
                  })}
                </div>
              ) : availableProducts.length > 0 && filterQ ? (
                <div className="muted">No products match this filter.</div>
              ) : availableProducts.length === 0 ? (
                <div className="muted">No products available for this order type.</div>
              ) : null}
            </div>
          ) : null}
        </div>
      </CaseDocPanelScroll>
    </div>
  )
}
