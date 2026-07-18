import { useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch } from './api'
import { fetchCaseById } from './apiSearch'
import { BusyIcon } from './BusyIcon'
import { poundsToPence } from './FeeScaleEditor'
import { MatterSearchPicker } from './MatterSearchPicker'
import { openOnlyOfficeCaseEditor } from './onlyofficeEditorWindow'
import { QuoteReviewEditor } from './QuoteReviewEditor'
import { SearchInput } from './SearchInput'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import type {
  CaseContactOut,
  CaseOut,
  FeeScaleOut,
  QuoteDraftCategory,
  QuotePreviewOut,
} from './types'
import type { QuoteAwaitingSaveContext } from './quoteAwaitingSave'

type Props = {
  token: string
  open: boolean
  onClose: () => void
  onOpenNewMatter: () => void
  onCaseCreatedRefresh: () => void | Promise<void>
  pendingNewCaseId: string | null
  onClearPendingNewCase: () => void
  /** When set, skip matter search — quote is for this matter (e.g. opened from case view). */
  presetCase?: CaseOut | null
  onQuoteCreated?: () => void
  /** Quote file opened in OnlyOffice — parent listens for save/publish before offering send options. */
  onAwaitingQuoteSave?: (ctx: QuoteAwaitingSaveContext) => void
}

type Step = 'matter' | 'fee-scale' | 'contact' | 'review'

function feeScaleMatchesSearch(f: FeeScaleOut, search: string): boolean {
  const s = search.trim().toLowerCase()
  if (!s) return false
  const parts = [f.name, f.reference, f.scope_summary ?? '']
  return parts.join(' ').toLowerCase().includes(s)
}

function feeScalesUrlForCase(c: CaseOut | null | undefined): string {
  if (!c) return '/fee-scales'
  if (c.matter_sub_type_id) {
    return `/fee-scales?matter_sub_type_id=${encodeURIComponent(c.matter_sub_type_id)}`
  }
  if (c.matter_head_type_id) {
    return `/fee-scales?matter_head_type_id=${encodeURIComponent(c.matter_head_type_id)}`
  }
  return '/fee-scales'
}

export function QuoteWizard({
  token,
  open,
  onClose,
  onOpenNewMatter,
  onCaseCreatedRefresh,
  pendingNewCaseId,
  onClearPendingNewCase,
  presetCase = null,
  onQuoteCreated,
  onAwaitingQuoteSave,
}: Props) {
  const [step, setStep] = useState<Step>('matter')
  const [caseId, setCaseId] = useState<string | null>(null)
  const [loadedCase, setLoadedCase] = useState<CaseOut | null>(null)
  const [feeScales, setFeeScales] = useState<FeeScaleOut[]>([])
  const [feeScaleId, setFeeScaleId] = useState<string | 'none'>('none')
  const [feeScaleSearch, setFeeScaleSearch] = useState('')
  const [caseContacts, setCaseContacts] = useState<CaseContactOut[]>([])
  const [pickMatterCcId, setPickMatterCcId] = useState('none')
  const [matterOpen, setMatterOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [propertyValueStr, setPropertyValueStr] = useState('')
  const [quotePreview, setQuotePreview] = useState<QuotePreviewOut | null>(null)
  const [composeDraft, setComposeDraft] = useState<QuoteDraftCategory[]>([])
  const [composeAmountOverrides, setComposeAmountOverrides] = useState<Record<string, string>>({})

  const presetCaseId = presetCase?.id ?? null
  const wasOpenRef = useRef(false)

  const selectedCase = useMemo(
    () => presetCase ?? loadedCase,
    [presetCase, loadedCase],
  )

  useEffect(() => {
    if (presetCase) {
      setLoadedCase(null)
      return
    }
    if (!caseId || !token) {
      setLoadedCase(null)
      return
    }
    let cancelled = false
    void fetchCaseById(token, caseId).then((row) => {
      if (!cancelled) setLoadedCase(row)
    })
    return () => {
      cancelled = true
    }
  }, [presetCase, caseId, token])

  /** Reset wizard only when the dialog opens — not when parent case data refreshes mid-flow. */
  useEffect(() => {
    if (!open) {
      wasOpenRef.current = false
      return
    }
    if (wasOpenRef.current) return
    wasOpenRef.current = true
    setFeeScaleId('none')
    setFeeScaleSearch('')
    setPickMatterCcId('none')
    setPropertyValueStr('')
    setQuotePreview(null)
    setComposeDraft([])
    setComposeAmountOverrides({})
    setErr(null)
    setBusy(false)
    if (presetCaseId) {
      setCaseId(presetCaseId)
      setStep('fee-scale')
    } else {
      setStep('matter')
      setCaseId(null)
    }
  }, [open, presetCaseId])

  useEffect(() => {
    if (!open || !pendingNewCaseId) return
    setCaseId(pendingNewCaseId)
    onClearPendingNewCase()
    void onCaseCreatedRefresh()
    setStep('fee-scale')
  }, [open, pendingNewCaseId, onClearPendingNewCase, onCaseCreatedRefresh])

  useEffect(() => {
    if (!open || step !== 'fee-scale') return
    const url = feeScalesUrlForCase(selectedCase)
    void apiFetch<FeeScaleOut[]>(url, { token })
      .then((d) => {
        const list = Array.isArray(d) ? d : []
        setFeeScales(list)
        setFeeScaleId((prev) => (prev !== 'none' && list.some((f) => f.id === prev) ? prev : 'none'))
      })
      .catch(() => {
        setFeeScales([])
        setFeeScaleId('none')
      })
  }, [open, step, selectedCase, token])

  useEffect(() => {
    if (!caseId) {
      setCaseContacts([])
      return
    }
    void apiFetch<CaseContactOut[]>(`/cases/${caseId}/contacts`, { token })
      .then((d) => setCaseContacts(Array.isArray(d) ? d : []))
      .catch(() => setCaseContacts([]))
  }, [caseId, token])

  useEffect(() => {
    if (step !== 'review' || feeScaleId === 'none') {
      setQuotePreview(null)
    }
  }, [step, feeScaleId])

  const displayedFeeScales = useMemo(() => {
    const q = feeScaleSearch.trim()
    if (q) return feeScales.filter((f) => feeScaleMatchesSearch(f, q))
    return feeScales.filter((f) => f.is_favorited)
  }, [feeScales, feeScaleSearch])

  const matterOptions = useMemo(
    () => [
      { value: 'none', label: 'None' },
      { value: 'all_clients', label: 'All clients' },
      ...caseContacts.map((cc) => ({
        value: cc.id,
        label: cc.name,
        hint: cc.matter_contact_type ?? undefined,
      })),
    ],
    [caseContacts],
  )

  if (!open) return null

  async function composeQuote() {
    if (!caseId) return
    if (feeScaleId !== 'none' && !quotePreview) {
      setErr('Fee preview is still loading — wait a moment and try again.')
      return
    }
    if (quotePreview?.needs_property_value && poundsToPence(propertyValueStr) == null) {
      setErr('Enter the property value (£) before creating the quote — it is required for banded fees and VAT.')
      return
    }
    setBusy(true)
    setErr(null)
    try {
      let caseContactId: string | null = null
      let mergeAll = false
      if (pickMatterCcId === 'all_clients') {
        mergeAll = true
      } else if (pickMatterCcId && pickMatterCcId !== 'none') {
        caseContactId = pickMatterCcId
      }
      const matterDescription = selectedCase?.matter_description.trim() || 'Matter'
      const amount_overrides: Record<string, number> = {}
      for (const [key, s] of Object.entries(composeAmountOverrides)) {
        const p = poundsToPence(s)
        if (p != null) amount_overrides[key] = p
      }
      const res = await apiFetch<{ id: string }>(`/cases/${caseId}/files/compose-quote`, {
        token,
        json: {
          original_filename: `Quote — ${matterDescription.replace(/[/\\]/g, '_').slice(0, 120)}.docx`,
          folder: '',
          fee_scale_id: feeScaleId === 'none' ? null : feeScaleId,
          case_contact_id: caseContactId,
          global_contact_id: null,
          precedent_merge_all_clients: mergeAll,
          property_value_pence: poundsToPence(propertyValueStr),
          amount_overrides,
          draft: feeScaleId === 'none' || composeDraft.length === 0 ? null : composeDraft,
          quote_lines: null,
        },
      })
      onQuoteCreated?.()
      const preferredContactId =
        pickMatterCcId !== 'none' && pickMatterCcId !== 'all_clients' ? pickMatterCcId : null
      onAwaitingQuoteSave?.({
        caseId,
        fileId: res.id,
        preferredContactId,
        portalEnabled: Boolean(selectedCase?.portal_enabled),
      })
      setBusy(false)
      onClose()
      window.requestAnimationFrame(() => {
        openOnlyOfficeCaseEditor(caseId, res.id)
      })
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not create quote')
      setBusy(false)
    }
  }

  return (
    <div className="modalOverlay" role="dialog" aria-modal="true">
      <div
        className={`modal card modal--scrollBody modal--quoteWizard${step === 'review' ? ' modal--quoteReview' : ''}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="paneHead">
          <h2 style={{ margin: 0, fontSize: 18 }}>New quote</h2>
          <button type="button" className="btn" disabled={busy} onClick={onClose}>
            Close
          </button>
        </div>
        <div className="stack modalBodyScroll modalBodyScroll--relative" style={{ marginTop: 12 }}>
          {err ? <div className="error">{err}</div> : null}

          {step === 'matter' ? (
            <>
              <p className="muted" style={{ marginTop: 0 }}>
                Search for an existing matter, or create a new one.
              </p>
              <label className="field">
                <span>Find matter</span>
                <MatterSearchPicker
                  token={token}
                  value={caseId ?? ''}
                  disabled={busy}
                  autoFocus
                  onChange={(id) => setCaseId(id || null)}
                />
              </label>
              <div className="row" style={{ justifyContent: 'flex-end', marginTop: 12, gap: 8 }}>
                <button
                  type="button"
                  className="btn"
                  onClick={() => {
                    onClose()
                    onOpenNewMatter()
                  }}
                >
                  New matter…
                </button>
                <button type="button" className="btn primary" disabled={!caseId} onClick={() => setStep('fee-scale')}>
                  Continue
                </button>
              </div>
            </>
          ) : null}

          {step === 'fee-scale' ? (
            <>
              {selectedCase ? (
                <p className="muted" style={{ fontSize: 12, marginTop: 0 }}>
                  Fee scales for{' '}
                  {[selectedCase.matter_head_type_name, selectedCase.matter_sub_type_name].filter(Boolean).join(' · ') ||
                    'this matter'}
                  .
                </p>
              ) : null}
              <label className="field">
                <span>Fee scale</span>
                <SearchInput
                  className="input"
                  placeholder="Search fee scales…"
                  value={feeScaleSearch}
                  onChange={(e) => setFeeScaleSearch(e.target.value)}
                  onClear={() => setFeeScaleSearch('')}
                />
              </label>
              <div className="list" style={{ maxHeight: 220, overflow: 'auto', marginTop: 8 }}>
                <button
                  type="button"
                  className={`listItem${feeScaleId === 'none' ? ' active' : ''}`}
                  onClick={() => setFeeScaleId('none')}
                >
                  <div className="listTitle">No fee scale (letterhead only)</div>
                </button>
                {displayedFeeScales.map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    className={`listItem${feeScaleId === f.id ? ' active' : ''}`}
                    onClick={() => setFeeScaleId(f.id)}
                  >
                    <div className="listTitle">
                      {f.is_favorited ? '★ ' : ''}
                      {f.name}
                    </div>
                    <div className="muted" style={{ fontSize: 12 }}>
                      {[f.reference, f.scope_summary].filter(Boolean).join(' · ')}
                    </div>
                  </button>
                ))}
                {!feeScaleSearch.trim() && displayedFeeScales.length === 0 ? (
                  <div className="muted" style={{ padding: '8px 4px', fontSize: 13 }}>
                    No favourite fee scales for this matter. Search above to find one, or star scales under Quotes → Fee
                    scales.
                  </div>
                ) : null}
                {feeScaleSearch.trim() && displayedFeeScales.length === 0 ? (
                  <div className="muted" style={{ padding: '8px 4px', fontSize: 13 }}>
                    No fee scales match your search.
                  </div>
                ) : null}
              </div>
              <p className="muted" style={{ fontSize: 12 }}>
                Favourite scales appear here first. Search to find any scale for this matter. Fee scales are configured
                under Quotes → Fee scales.
              </p>
              <div className="row" style={{ justifyContent: 'flex-end', marginTop: 12 }}>
                <button
                  type="button"
                  className="btn"
                  disabled={busy}
                  onClick={() => (presetCase ? onClose() : setStep('matter'))}
                >
                  Back
                </button>
                <button type="button" className="btn primary" disabled={busy} onClick={() => setStep('contact')}>
                  Continue
                </button>
              </div>
            </>
          ) : null}

          {step === 'contact' ? (
            <>
              <SingleSelectDropdown
                label="Matter contact (for merge codes)"
                options={matterOptions}
                value={pickMatterCcId}
                onChange={setPickMatterCcId}
                open={matterOpen}
                onOpenChange={setMatterOpen}
              />
              <div className="row" style={{ justifyContent: 'flex-end', marginTop: 12 }}>
                <button type="button" className="btn" disabled={busy} onClick={() => setStep('fee-scale')}>
                  Back
                </button>
                <button type="button" className="btn primary" disabled={busy} onClick={() => setStep('review')}>
                  Continue
                </button>
              </div>
            </>
          ) : null}

          {step === 'review' ? (
            <>
              <p className="muted" style={{ marginTop: 0, fontSize: 12 }}>
                Edit descriptions and amounts, add or remove lines, then create the quote. Values are merged into your
                quote letterhead template.
              </p>
              {feeScaleId !== 'none' ? (
                <QuoteReviewEditor
                  token={token}
                  feeScaleId={feeScaleId}
                  propertyValueStr={propertyValueStr}
                  onPropertyValueChange={setPropertyValueStr}
                  onPreviewChange={setQuotePreview}
                  onComposeDataChange={({ draft, amountOverrides, preview }) => {
                    setComposeDraft(draft)
                    setComposeAmountOverrides(amountOverrides)
                    setQuotePreview(preview)
                  }}
                />
              ) : (
                <p className="muted" style={{ fontSize: 12 }}>
                  No fee table — only letterhead merge codes will be applied.
                </p>
              )}
              <div className="row" style={{ justifyContent: 'flex-end', marginTop: 12, gap: 8 }}>
                <button type="button" className="btn" disabled={busy} onClick={() => setStep('contact')}>
                  Back
                </button>
                <button
                  type="button"
                  className="btn primary"
                  disabled={busy || (feeScaleId !== 'none' && !quotePreview)}
                  onClick={() => void composeQuote()}
                >
                  {busy ? 'Creating quote…' : 'Create quote'}
                </button>
              </div>
            </>
          ) : null}

          {busy ? (
            <div className="modalBusyOverlay" aria-hidden={false}>
              <BusyIcon label="Creating quote" />
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}
