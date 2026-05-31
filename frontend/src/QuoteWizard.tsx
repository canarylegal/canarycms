import { useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch } from './api'
import { BusyIcon } from './BusyIcon'
import { poundsToPence } from './FeeScaleEditor'
import { openOnlyOfficeCaseEditor } from './onlyofficeEditorWindow'
import { QuoteReviewEditor } from './QuoteReviewEditor'
import { SearchInput } from './SearchInput'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import type { CaseContactOut, CaseOut, FeeScaleOut, QuoteDraftCategory, QuotePreviewOut, UserSummary } from './types'
import { formatCaseStatusLabel } from './types'

type Props = {
  token: string
  cases: CaseOut[]
  users: UserSummary[]
  open: boolean
  onClose: () => void
  onOpenNewMatter: () => void
  onCaseCreatedRefresh: () => void | Promise<void>
  pendingNewCaseId: string | null
  onClearPendingNewCase: () => void
  onSendLetter: (caseId: string) => void
  onSendEmail: (caseId: string) => void
  /** When set, skip matter search — quote is for this matter (e.g. opened from case view). */
  presetCase?: CaseOut | null
  onQuoteCreated?: () => void
}

type Step = 'matter' | 'fee-scale' | 'contact' | 'review' | 'send'

function feeEarnerLabel(c: CaseOut, users: UserSummary[]): string {
  const u = users.find((x) => x.id === c.fee_earner_user_id)
  return u?.display_name ?? '—'
}

function caseMatchesQuoteSearch(c: CaseOut, users: UserSummary[], search: string): boolean {
  const s = search.trim().toLowerCase()
  if (!s) return false
  const parts = [
    c.case_number,
    c.client_name ?? '',
    c.matter_description ?? '',
    formatCaseStatusLabel(c.status),
    feeEarnerLabel(c, users),
    c.matter_head_type_name ?? '',
    c.matter_sub_type_name ?? '',
  ]
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
  cases,
  users,
  open,
  onClose,
  onOpenNewMatter,
  onCaseCreatedRefresh,
  pendingNewCaseId,
  onClearPendingNewCase,
  onSendLetter,
  onSendEmail,
  presetCase = null,
  onQuoteCreated,
}: Props) {
  const [step, setStep] = useState<Step>('matter')
  const [caseId, setCaseId] = useState<string | null>(null)
  const [caseMatterSearch, setCaseMatterSearch] = useState('')
  const [feeScales, setFeeScales] = useState<FeeScaleOut[]>([])
  const [feeScaleId, setFeeScaleId] = useState<string | 'none'>('none')
  const [feeScaleOpen, setFeeScaleOpen] = useState(false)
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
    () => presetCase ?? cases.find((c) => c.id === caseId) ?? null,
    [presetCase, cases, caseId],
  )

  /** Reset wizard only when the dialog opens — not when parent case data refreshes mid-flow. */
  useEffect(() => {
    if (!open) {
      wasOpenRef.current = false
      return
    }
    if (wasOpenRef.current) return
    wasOpenRef.current = true
    setCaseMatterSearch('')
    setFeeScaleId('none')
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
        setFeeScaleId((prev) => {
          if (prev === 'none') return 'none'
          return list.some((f) => f.id === prev) ? prev : list[0]?.id ?? 'none'
        })
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

  const matchingCases = useMemo(() => {
    const q = caseMatterSearch.trim()
    if (!q) return []
    return cases.filter((c) => caseMatchesQuoteSearch(c, users, q)).slice(0, 25)
  }, [cases, users, caseMatterSearch])

  const feeScaleOptions = useMemo(
    () => [
      { value: 'none', label: 'No fee scale (letterhead only)' },
      ...feeScales.map((f) => ({ value: f.id, label: f.name, hint: f.reference })),
    ],
    [feeScales],
  )

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
    setBusy(true)
    setErr(null)
    try {
      let label = 'Quote'
      let caseContactId: string | null = null
      let mergeAll = false
      if (pickMatterCcId === 'all_clients') {
        mergeAll = true
        label = 'All clients'
      } else if (pickMatterCcId && pickMatterCcId !== 'none') {
        caseContactId = pickMatterCcId
        label = caseContacts.find((c) => c.id === pickMatterCcId)?.name ?? 'Quote'
      }
      const amount_overrides: Record<string, number> = {}
      for (const [key, s] of Object.entries(composeAmountOverrides)) {
        const p = poundsToPence(s)
        if (p != null) amount_overrides[key] = p
      }
      const res = await apiFetch<{ id: string }>(`/cases/${caseId}/files/compose-quote`, {
        token,
        json: {
          original_filename: `Quote — ${label.replace(/[/\\]/g, '_').slice(0, 120)}.docx`,
          folder: '',
          fee_scale_id: feeScaleId === 'none' ? null : feeScaleId,
          case_contact_id: caseContactId,
          global_contact_id: null,
          precedent_merge_all_clients: mergeAll,
          property_value_pence: poundsToPence(propertyValueStr),
          amount_overrides,
          draft: feeScaleId === 'none' ? null : composeDraft,
          quote_lines:
            quotePreview?.lines.map((ln) => ({
              name: ln.name,
              line_kind: ln.line_kind,
              amount_pence: ln.amount_pence ?? null,
              is_bold: ln.is_bold,
            })) ?? null,
        },
      })
      onQuoteCreated?.()
      setStep('send')
      setBusy(false)
      window.requestAnimationFrame(() => {
        openOnlyOfficeCaseEditor(caseId, res.id)
      })
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not create quote')
      setBusy(false)
    }
  }

  const modalTitle = step === 'send' ? 'Send quote' : 'New quote'

  return (
    <div className="modalOverlay" role="dialog" aria-modal="true">
      <div
        className={`modal card modal--scrollBody modal--quoteWizard${step === 'review' ? ' modal--quoteReview' : ''}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="paneHead">
          <h2 style={{ margin: 0, fontSize: 18 }}>{modalTitle}</h2>
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
                <SearchInput
                  className="calendarMatterPickerSearch"
                  placeholder="Reference, client, description, status, fee earner…"
                  value={caseMatterSearch}
                  autoFocus
                  onChange={(e) => {
                    setCaseMatterSearch(e.target.value)
                    setCaseId(null)
                  }}
                  onClear={() => {
                    setCaseMatterSearch('')
                    setCaseId(null)
                  }}
                  aria-label="Search matters"
                />
              </label>
              <div className="list" style={{ maxHeight: 220, overflow: 'auto' }}>
                {matchingCases.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    className={`listItem ${caseId === c.id ? 'active' : ''}`}
                    onClick={() => setCaseId(c.id)}
                  >
                    <div className="listTitle">{c.case_number}</div>
                    <div className="muted">
                      {[c.client_name, c.matter_description, formatCaseStatusLabel(c.status)]
                        .filter(Boolean)
                        .join(' · ')}
                    </div>
                  </button>
                ))}
                {!caseMatterSearch.trim() ? (
                  <div className="muted">Type in the search box above to find a matter.</div>
                ) : matchingCases.length === 0 ? (
                  <div className="muted">No matters match your search.</div>
                ) : null}
              </div>
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
              <SingleSelectDropdown
                label="Fee scale"
                options={feeScaleOptions}
                value={feeScaleId}
                onChange={(v) => setFeeScaleId(v as string | 'none')}
                open={feeScaleOpen}
                onOpenChange={setFeeScaleOpen}
                emptyMessage={
                  feeScales.length === 0 ? 'No fee scales for this matter — add one under Quotes → Fee scales.' : undefined
                }
              />
              <p className="muted" style={{ fontSize: 12 }}>
                Fee scales are configured in Canary (lines, bands, VAT). The quote is generated as a Word document on
                your quote letterhead template.
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

          {step === 'send' ? (
            <>
              <p className="muted" style={{ marginTop: 0 }}>
                Your quote document is open in OnlyOffice. How would you like to send it?
              </p>
              <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                <button
                  type="button"
                  className="btn primary"
                  disabled={!caseId}
                  onClick={() => {
                    if (caseId) onSendEmail(caseId)
                    onClose()
                  }}
                >
                  Send by e-mail
                </button>
                <button
                  type="button"
                  className="btn"
                  disabled={!caseId}
                  onClick={() => {
                    if (caseId) onSendLetter(caseId)
                    onClose()
                  }}
                >
                  Send by letter
                </button>
                <button type="button" className="btn" onClick={onClose}>
                  Not now
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
