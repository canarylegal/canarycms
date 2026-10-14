import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { apiUrl, applyAuthHeaders, formatApiErrorDetail } from './api'
import { triggerBlobDownload } from './case/caseDocFileOps'
import {
  CANARY_SIGN_SIGNER_PALETTE,
  CanarySignPdfDocument,
  fieldTypeLabel,
  formatUkDate,
  renderTypedSignaturePng,
  SIGNATURE_STYLES,
  type CanarySignFormWidget,
} from './CanarySignPdfDocument'
import type { CanarySignFieldOut, PortalCanarySignOut } from './types'

type Props = {
  signing: PortalCanarySignOut
  portalToken: string
  previewMode?: boolean
  onBack: () => void
  onCompleted: (next: PortalCanarySignOut) => void
  onDeclined: () => void
  onSigningUpdated?: (next: PortalCanarySignOut) => void
}

type FieldDraft = {
  text?: string
  image_b64?: string
  checked?: boolean
  style_id?: string
}

async function portalFetchJson<T>(
  path: string,
  opts: RequestInit & { portalToken?: string; json?: unknown } = {},
): Promise<T> {
  const { portalToken, json, ...rest } = opts
  const headers = new Headers(rest.headers ?? {})
  if (portalToken) applyAuthHeaders(headers, portalToken)
  if (json !== undefined) headers.set('Content-Type', 'application/json')
  const res = await fetch(apiUrl(path), {
    ...rest,
    headers,
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  })
  const body = await res.text()
  let parsed: unknown = null
  if (body) {
    try {
      parsed = JSON.parse(body)
    } catch {
      parsed = body
    }
  }
  if (!res.ok) {
    throw new Error(formatApiErrorDetail(parsed, res.statusText, apiUrl(path)))
  }
  return parsed as T
}

async function portalDownloadFile(path: string, portalToken: string, fallbackName: string) {
  const headers = new Headers()
  applyAuthHeaders(headers, portalToken)
  const res = await fetch(apiUrl(path), { headers })
  if (!res.ok) {
    const body = await res.text()
    let parsed: unknown = body
    try {
      parsed = JSON.parse(body)
    } catch {
      /* keep text */
    }
    throw new Error(formatApiErrorDetail(parsed, res.statusText, apiUrl(path)))
  }
  const blob = await res.blob()
  const cd = res.headers.get('Content-Disposition') || ''
  const match = /filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(cd)
  const name = match ? decodeURIComponent(match[1].replace(/"/g, '')) : fallbackName
  triggerBlobDownload(blob, name || fallbackName)
}

function isLockedField(fieldType: string) {
  return fieldType === 'printed_name' || fieldType === 'date'
}

function friendlyPortalError(e: unknown, fallback: string): string {
  const raw = ((e as { message?: string }).message || '').trim() || fallback
  if (/onlyoffice|pikepdf|httpx|traceback|ConvertService|RuntimeError|PdfError/i.test(raw)) {
    return 'This PDF could not be prepared for signing. Please contact the sender.'
  }
  return raw
}

function formatSignedWhen(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function statusBadge(signing: PortalCanarySignOut): { label: string; className: string } {
  const status = (signing.status || '').toLowerCase()
  const recip = (signing.recipient_status || '').toLowerCase()
  if (status === 'completed' || recip === 'signed') {
    return { label: 'Complete', className: 'portalActionBadge portalActionBadge--complete' }
  }
  if (status === 'declined' || recip === 'declined') {
    return { label: 'Declined', className: 'portalActionBadge portalActionBadge--declined' }
  }
  if (status === 'expired') {
    return { label: 'Expired', className: 'portalActionBadge portalActionBadge--expired' }
  }
  if (status === 'voided') {
    return { label: 'Cancelled', className: 'portalActionBadge portalActionBadge--cancelled' }
  }
  return { label: 'Outstanding', className: 'portalActionBadge portalActionBadge--outstanding' }
}

export function PortalCanarySignPanel({
  signing: signingProp,
  portalToken,
  previewMode = false,
  onBack,
  onCompleted,
  onDeclined,
  onSigningUpdated,
}: Props) {
  const padRef = useRef<HTMLCanvasElement>(null)
  const drawing = useRef(false)
  const [signing, setSigning] = useState(signingProp)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [declineOpen, setDeclineOpen] = useState(false)
  const [declineReason, setDeclineReason] = useState('')
  const [consent, setConsent] = useState(false)
  const [signMode, setSignMode] = useState<'draw' | 'type'>('type')
  const [styleIndex, setStyleIndex] = useState(0)
  const [activeFieldId, setActiveFieldId] = useState<string | null>(null)
  const [drafts, setDrafts] = useState<Record<string, FieldDraft>>({})
  const [formDrafts, setFormDrafts] = useState<Record<string, string | boolean>>({})
  const [lockConfirmOpen, setLockConfirmOpen] = useState(false)
  const [signingName, setSigningName] = useState('')
  const [reviewedAnswers, setReviewedAnswers] = useState(false)

  useEffect(() => {
    setSigning(signingProp)
  }, [signingProp])

  function applySigning(next: PortalCanarySignOut) {
    setSigning(next)
    onSigningUpdated?.(next)
  }

  const recipientName = (signing.recipient_name || '').trim()
  useEffect(() => {
    // Default signing name without courtesy title (Mr/Mrs/Ms/Dr…) — titles look typeset, not handwritten.
    const stripped = recipientName.replace(/^(mr|mrs|ms|miss|dr|prof)\.?\s+/i, '').trim()
    setSigningName(stripped || recipientName)
  }, [signing.id, recipientName])

  const badge = statusBadge(signing)
  const isReceipt =
    !signing.can_sign &&
    ((signing.status || '').toLowerCase() === 'completed' ||
      (signing.recipient_status || '').toLowerCase() === 'signed')
  const formFilledByOther =
    Boolean(signing.has_fillable_form) &&
    Boolean(signing.form_completed || (signing.form_locked && !signing.form_lock_held_by_me))
  const waitingForFormFiller =
    Boolean(signing.has_fillable_form) &&
    !signing.can_sign &&
    (signing.status || '').toLowerCase() === 'pending' &&
    (signing.recipient_status || '').toLowerCase() !== 'signed' &&
    (signing.recipient_status || '').toLowerCase() !== 'declined' &&
    !signing.form_completed &&
    Boolean(signing.form_locked) &&
    !signing.form_lock_held_by_me

  const myFields = useMemo(
    () =>
      (signing.fields || [])
        .filter((f) => f.recipient_id === signing.recipient_id)
        .sort((a, b) => a.sort_order - b.sort_order),
    [signing.fields, signing.recipient_id],
  )

  const pdfUrl = useMemo(
    () => `${apiUrl(`/portal/canary-sign/${signing.id}/pdf`)}?v=${signing.status}-${signing.completed_at || ''}`,
    [signing.id, signing.status, signing.completed_at],
  )
  const firstSigId = useMemo(
    () => myFields.find((f) => f.field_type === 'signature' || f.field_type === 'initials')?.id ?? null,
    [myFields],
  )

  useEffect(() => {
    if (isReceipt) return
    const init: Record<string, FieldDraft> = {}
    for (const f of myFields) {
      if (f.field_type === 'date') init[f.id] = { text: formatUkDate() }
      else if (f.field_type === 'printed_name') init[f.id] = { text: signingName || recipientName }
      else if (f.field_type === 'checkbox') init[f.id] = { checked: false }
      else init[f.id] = {}
    }
    setDrafts(init)
    setSignMode('type')
    setStyleIndex(0)
    setActiveFieldId(firstSigId ?? myFields[0]?.id ?? null)
    setReviewedAnswers(false)
  }, [signing.id, recipientName, signingName, myFields, firstSigId, isReceipt])

  useEffect(() => {
    const next: Record<string, string | boolean> = {}
    for (const f of signing.form_fields || []) {
      const existing = signing.form_responses?.[f.name]
      if (f.field_type === 'radio' && f.export_value) {
        if (existing === true || String(existing).toLowerCase() === 'true') {
          // Legacy boolean ticks → treat as Included when that option exists.
          const opts = f.options || []
          next[f.name] = opts.includes('Included') ? 'Included' : f.export_value
        } else if (existing != null && String(existing).trim() !== '') {
          next[f.name] = String(existing).replace(/^\//, '')
        } else {
          next[f.name] = ''
        }
      } else if (f.field_type === 'checkbox') {
        next[f.name] = Boolean(existing) && String(existing).toLowerCase() !== 'off'
      } else {
        next[f.name] = existing != null ? String(existing) : f.current_value || ''
      }
    }
    setFormDrafts(next)
  }, [signing.id, signing.form_fields, signing.form_responses])

  const applyTypedStyle = useCallback(
    async (index: number, fieldId: string | null) => {
      const nameForSig = (signingName || recipientName).trim()
      if (!fieldId || !nameForSig) return
      const field = myFields.find((f) => f.id === fieldId)
      if (!field || (field.field_type !== 'signature' && field.field_type !== 'initials')) return
      try {
        const image_b64 = await renderTypedSignaturePng(nameForSig, { styleIndex: index })
        const style = SIGNATURE_STYLES[index % SIGNATURE_STYLES.length]
        setDrafts((d) => ({
          ...d,
          [fieldId]: { ...d[fieldId], image_b64, text: nameForSig, style_id: style.id },
        }))
        setErr(null)
      } catch {
        setErr('Could not create typed signature.')
      }
    },
    [myFields, recipientName, signingName],
  )

  useEffect(() => {
    if (isReceipt || signMode !== 'type' || !activeFieldId || previewMode) return
    const field = myFields.find((f) => f.id === activeFieldId)
    if (!field || (field.field_type !== 'signature' && field.field_type !== 'initials')) return
    void applyTypedStyle(styleIndex, activeFieldId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeFieldId, signMode, previewMode, isReceipt])

  useEffect(() => {
    const prev = document.body.style.cursor
    if (busy) document.body.style.cursor = 'wait'
    return () => {
      document.body.style.cursor = prev || ''
    }
  }, [busy])

  const clearPad = useCallback(() => {
    const c = padRef.current
    if (!c) return
    const ctx = c.getContext('2d')
    if (!ctx) return
    ctx.clearRect(0, 0, c.width, c.height)
    ctx.fillStyle = '#fff'
    ctx.fillRect(0, 0, c.width, c.height)
  }, [])

  useEffect(() => {
    if (signMode === 'draw') clearPad()
  }, [activeFieldId, signMode, clearPad])

  function padPointer(e: React.PointerEvent<HTMLCanvasElement>, type: 'down' | 'move' | 'up') {
    const c = padRef.current
    if (!c) return
    const ctx = c.getContext('2d')
    if (!ctx) return
    const rect = c.getBoundingClientRect()
    const x = ((e.clientX - rect.left) / rect.width) * c.width
    const y = ((e.clientY - rect.top) / rect.height) * c.height
    if (type === 'down') {
      drawing.current = true
      c.setPointerCapture(e.pointerId)
      ctx.beginPath()
      ctx.moveTo(x, y)
      return
    }
    if (type === 'up') {
      drawing.current = false
      return
    }
    if (!drawing.current) return
    ctx.lineWidth = 2.5
    ctx.lineCap = 'round'
    ctx.strokeStyle = '#0f172a'
    ctx.lineTo(x, y)
    ctx.stroke()
  }

  function applyDrawnSignature() {
    if (!activeFieldId) return
    const c = padRef.current
    if (!c) return
    const dataUrl = c.toDataURL('image/png')
    const b64 = dataUrl.replace(/^data:image\/png;base64,/, '')
    setDrafts((d) => ({ ...d, [activeFieldId]: { ...d[activeFieldId], image_b64: b64, text: undefined } }))
    setErr(null)
  }

  async function cycleSignatureStyle(delta: number) {
    const next = (styleIndex + delta + SIGNATURE_STYLES.length) % SIGNATURE_STYLES.length
    setStyleIndex(next)
    setSignMode('type')
    const targetId = activeFieldId || firstSigId
    await applyTypedStyle(next, targetId)
  }

  function fieldReady(f: CanarySignFieldOut): boolean {
    const d = drafts[f.id] || {}
    if (f.page == null || f.x_pct == null || f.y_pct == null) return false
    if (f.field_type === 'signature' || f.field_type === 'initials') {
      if (!(d.image_b64 || (d.text || '').trim())) return false
    } else if (f.field_type === 'checkbox') {
      if (f.required && d.checked !== true) return false
    } else if (f.required && !(d.text || '').trim()) {
      return false
    }
    return true
  }

  async function claimFormLock() {
    if (previewMode) {
      setErr('Staff preview cannot lock the form.')
      return
    }
    setBusy(true)
    setErr(null)
    setLockConfirmOpen(false)
    try {
      const next = await portalFetchJson<PortalCanarySignOut>(`/portal/canary-sign/${signing.id}/form/lock`, {
        method: 'POST',
        portalToken,
      })
      applySigning(next)
    } catch (e: unknown) {
      setErr(friendlyPortalError(e, 'Could not lock the form'))
    } finally {
      setBusy(false)
    }
  }

  async function saveFormDrafts() {
    if (previewMode || !signing.form_lock_held_by_me) return
    setBusy(true)
    setErr(null)
    try {
      const next = await portalFetchJson<PortalCanarySignOut>(`/portal/canary-sign/${signing.id}/form/responses`, {
        method: 'PUT',
        portalToken,
        json: { responses: formDrafts },
      })
      applySigning(next)
    } catch (e: unknown) {
      setErr(friendlyPortalError(e, 'Could not save form answers'))
    } finally {
      setBusy(false)
    }
  }

  async function submit() {
    if (previewMode) {
      setErr('Staff preview cannot sign.')
      return
    }
    if (!consent) {
      setErr('Please confirm you agree to sign electronically.')
      return
    }
    if (formFilledByOther && !reviewedAnswers) {
      setErr('Please confirm you have reviewed the answers on this form before signing.')
      return
    }
    if (signing.has_fillable_form && !signing.form_completed && !signing.form_lock_held_by_me) {
      setErr('Someone must fill and lock the form before signing can finish.')
      return
    }
    for (const f of myFields) {
      if (f.required && !fieldReady(f)) {
        setErr(`Please complete: ${f.label || fieldTypeLabel(f.field_type)}`)
        return
      }
    }
    setBusy(true)
    setErr(null)
    try {
      const field_values: Record<string, FieldDraft> = {}
      for (const f of myFields) {
        const d = drafts[f.id] || {}
        field_values[f.id] = {
          text: d.text,
          image_b64: d.image_b64,
          checked: d.checked,
        }
      }
      const next = await portalFetchJson<PortalCanarySignOut>(`/portal/canary-sign/${signing.id}/sign`, {
        method: 'POST',
        portalToken,
        json: {
          field_values,
          consent: true,
          form_responses:
            signing.has_fillable_form && signing.form_lock_held_by_me && !signing.form_completed
              ? formDrafts
              : undefined,
        },
      })
      applySigning(next)
      onCompleted(next)
    } catch (e: unknown) {
      setErr(friendlyPortalError(e, 'Could not submit signature'))
    } finally {
      setBusy(false)
    }
  }

  async function decline() {
    if (previewMode) {
      setErr('Staff preview cannot decline.')
      return
    }
    setBusy(true)
    setErr(null)
    try {
      await portalFetchJson(`/portal/canary-sign/${signing.id}/decline`, {
        method: 'POST',
        portalToken,
        json: { reason: declineReason.trim() || null },
      })
      onDeclined()
    } catch (e: unknown) {
      setErr(friendlyPortalError(e, 'Could not decline'))
    } finally {
      setBusy(false)
    }
  }

  async function downloadSigned() {
    setBusy(true)
    setErr(null)
    try {
      await portalDownloadFile(
        `/portal/canary-sign/${signing.id}/signed-pdf`,
        portalToken,
        'signed-document.pdf',
      )
    } catch (e: unknown) {
      setErr(friendlyPortalError(e, 'Could not download signed document'))
    } finally {
      setBusy(false)
    }
  }

  async function downloadCertificate() {
    setBusy(true)
    setErr(null)
    try {
      await portalDownloadFile(
        `/portal/canary-sign/${signing.id}/certificate`,
        portalToken,
        'signature-certificate.pdf',
      )
    } catch (e: unknown) {
      setErr(friendlyPortalError(e, 'Could not download certificate'))
    } finally {
      setBusy(false)
    }
  }

  const canSign = signing.can_sign && !previewMode
  const missingPlacement = myFields.some((f) => f.page == null || f.x_pct == null || f.y_pct == null)
  const palette = CANARY_SIGN_SIGNER_PALETTE[0]
  const currentStyle = SIGNATURE_STYLES[styleIndex % SIGNATURE_STYLES.length]

  const overlays = isReceipt
    ? []
    : myFields
        .filter((f) => f.page != null && f.x_pct != null && f.y_pct != null)
        .map((f) => {
          const d = drafts[f.id] || {}
          const isSig = f.field_type === 'signature' || f.field_type === 'initials'
          return {
            id: f.id,
            page: f.page as number,
            x_pct: f.x_pct as number,
            y_pct: f.y_pct as number,
            w_pct: f.w_pct ?? 25,
            h_pct: f.h_pct ?? 5,
            label: f.label || fieldTypeLabel(f.field_type),
            color: palette.border,
            fill: palette.fill,
            selected: activeFieldId === f.id,
            textStyle: isSig ? ('script' as const) : ('plain' as const),
            previewText: d.image_b64 ? null : d.text || null,
            previewImageB64: d.image_b64 || null,
          }
        })

  const formEditable = Boolean(
    !isReceipt &&
      signing.has_fillable_form &&
      signing.form_locked &&
      signing.can_edit_form &&
      signing.form_lock_held_by_me &&
      !signing.form_completed &&
      !previewMode &&
      !busy,
  )
  const showFormWidgets = Boolean(!isReceipt && signing.has_fillable_form && signing.form_locked)
  const formWidgets: CanarySignFormWidget[] = showFormWidgets
    ? (signing.form_fields || []).map((f) => ({
        name: f.name,
        label: f.label || f.name,
        field_type: f.field_type,
        page: f.page,
        x_pct: f.x_pct,
        y_pct: f.y_pct,
        w_pct: f.w_pct,
        h_pct: f.h_pct,
        options: f.options || [],
        multiline: Boolean(f.multiline),
        export_value: f.export_value || '',
        value:
          formDrafts[f.name] ??
          (f.field_type === 'checkbox' && !f.export_value ? false : ''),
        editable: formEditable,
      }))
    : []

  return (
    <div className="portalCanarySignPanel" style={{ marginTop: 16, cursor: busy ? 'wait' : undefined }} aria-busy={busy}>
      <div className="row" style={{ gap: 8, flexWrap: 'wrap', marginBottom: 12, alignItems: 'center' }}>
        <button type="button" className="btn" onClick={onBack} disabled={busy}>
          ← Back
        </button>
        <h2 style={{ margin: 0, flex: 1, fontSize: 18 }}>{signing.subject}</h2>
        <span className={badge.className}>{badge.label}</span>
      </div>
      {signing.matter_label ? <div className="muted" style={{ marginBottom: 8 }}>{signing.matter_label}</div> : null}
      {err ? <div className="error" style={{ marginBottom: 12 }}>{err}</div> : null}

      {isReceipt ? (
        <div className="card" style={{ padding: 16, marginBottom: 16 }}>
          <h3 style={{ marginTop: 0, fontSize: 16 }}>Signing complete</h3>
          <p style={{ marginTop: 0, fontSize: 14 }}>
            Thank you. Your signature has been recorded
            {signing.recipient_signed_at ? ` on ${formatSignedWhen(signing.recipient_signed_at)}` : ''}.
            {(signing.status || '').toLowerCase() === 'completed'
              ? ' The signed document is ready to download.'
              : ' Waiting for remaining signers before the final document is issued.'}
          </p>
          {(signing.signers || []).length > 0 ? (
            <div style={{ marginBottom: 12 }}>
              <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
                Signers
              </div>
              <ul className="stack" style={{ listStyle: 'none', padding: 0, margin: 0, gap: 6 }}>
                {(signing.signers || []).map((s, idx) => (
                  <li key={`${s.email || s.name}-${idx}`} style={{ fontSize: 14 }}>
                    <strong>{s.name}</strong>
                    <span className="muted" style={{ marginLeft: 8 }}>
                      {(s.status || '').toLowerCase() === 'signed'
                        ? `Signed ${formatSignedWhen(s.signed_at)}`
                        : (s.status || 'pending').replace(/_/g, ' ')}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
            {signing.has_signed_document ? (
              <button type="button" className="btn primary" disabled={busy} onClick={() => void downloadSigned()}>
                Download signed document
              </button>
            ) : null}
            {signing.has_certificate ? (
              <button type="button" className="btn" disabled={busy} onClick={() => void downloadCertificate()}>
                Download certificate
              </button>
            ) : null}
          </div>
          {!signing.has_signed_document && !signing.has_certificate ? (
            <div className="muted" style={{ marginTop: 8, fontSize: 13 }}>
              Downloads will appear here once all parties have signed.
            </div>
          ) : null}
        </div>
      ) : (
        <>
          {signing.disclaimer ? <p className="muted" style={{ fontSize: 13 }}>{signing.disclaimer}</p> : null}
          {missingPlacement ? (
            <div className="error" style={{ marginBottom: 12 }}>
              This signing request is missing field positions. Ask the sender to amend and re-send with fields placed on
              the document.
            </div>
          ) : null}
          <p className="muted" style={{ fontSize: 13, marginBottom: 8 }}>
            Coloured boxes show your signature fields. Choose a signature style below — your name and date are filled
            automatically.
          </p>
        </>
      )}

      {!isReceipt && signing.has_fillable_form ? (
        <div className="card" style={{ padding: 16, marginBottom: 16 }}>
          <h3 style={{ marginTop: 0, fontSize: 16 }}>Fillable form</h3>
          {!signing.form_locked ? (
            <div>
              <p style={{ marginTop: 0, fontSize: 14, marginBottom: 8 }}>
                This document has fillable fields shown on the pages below. The first recipient to start editing locks
                the form for everyone else.
              </p>
              {signing.can_claim_form_lock && !previewMode ? (
                !lockConfirmOpen ? (
                  <button type="button" className="btn primary" disabled={busy} onClick={() => setLockConfirmOpen(true)}>
                    Start filling this form
                  </button>
                ) : (
                  <div className="stack" style={{ gap: 8 }}>
                    <div className="notice">
                      Confirm: you will lock this form so only you can edit the fillable fields on the document. Other
                      recipients will review your answers after you complete your part.
                    </div>
                    <div className="row" style={{ gap: 8 }}>
                      <button type="button" className="btn primary" disabled={busy} onClick={() => void claimFormLock()}>
                        Confirm and lock form
                      </button>
                      <button type="button" className="btn" disabled={busy} onClick={() => setLockConfirmOpen(false)}>
                        Cancel
                      </button>
                    </div>
                  </div>
                )
              ) : (
                <div className="muted">Waiting for a recipient to lock and fill the form.</div>
              )}
            </div>
          ) : (
            <div className="row" style={{ gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
              <div className="muted" style={{ fontSize: 13, flex: 1, minWidth: 200 }}>
                {signing.form_completed
                  ? `Form completed by ${signing.form_locked_by_name || 'a recipient'} (read-only on the document).`
                  : signing.form_lock_held_by_me
                    ? 'You hold the form lock — fill the fields on the document below, then complete your signature.'
                    : `Locked by ${signing.form_locked_by_name || 'another recipient'} — answers appear on the document when available.`}
              </div>
              {signing.form_lock_held_by_me && !signing.form_completed && !previewMode ? (
                <button type="button" className="btn" disabled={busy} onClick={() => void saveFormDrafts()}>
                  Save form answers
                </button>
              ) : null}
            </div>
          )}
        </div>
      ) : null}

      <CanarySignPdfDocument
        pdfUrl={pdfUrl}
        authToken={portalToken}
        overlays={overlays}
        formWidgets={formWidgets}
        onFormWidgetChange={(name, value) => {
          if (busy || isReceipt) return
          setFormDrafts((d) => ({ ...d, [name]: value }))
        }}
        onOverlayClick={(id) => {
          if (isReceipt) return
          const f = myFields.find((x) => x.id === id)
          if (f && isLockedField(f.field_type)) {
            setActiveFieldId(firstSigId)
            return
          }
          setActiveFieldId(id)
        }}
      />

      {isReceipt ? null : canSign && !missingPlacement ? (
        <div className="card" style={{ padding: 16 }}>
          <h3 style={{ marginTop: 0, fontSize: 16 }}>Your fields</h3>
          <ul className="stack" style={{ listStyle: 'none', padding: 0, margin: '0 0 12px', gap: 8 }}>
            {myFields.map((f) => {
              const ready = fieldReady(f)
              const locked = isLockedField(f.field_type)
              const d = drafts[f.id] || {}
              return (
                <li key={f.id} className="row" style={{ justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                  <div>
                    <strong>{f.label || fieldTypeLabel(f.field_type)}</strong>
                    <div className="muted" style={{ fontSize: 12 }}>
                      {locked
                        ? `${d.text || '—'} · automatic`
                        : ready
                          ? 'Ready'
                          : 'Incomplete'}
                      {f.page != null ? ` · page ${f.page}` : ''}
                    </div>
                  </div>
                  {locked ? null : (
                    <button
                      type="button"
                      className={`btn${activeFieldId === f.id ? ' primary' : ''}`}
                      disabled={busy}
                      onClick={() => setActiveFieldId(f.id)}
                    >
                      {f.field_type === 'signature' || f.field_type === 'initials' ? 'Choose' : 'Edit'}
                    </button>
                  )}
                </li>
              )
            })}
          </ul>

          {activeFieldId ? (
            (() => {
              const field = myFields.find((f) => f.id === activeFieldId)
              if (!field || isLockedField(field.field_type)) return null
              if (field.field_type === 'signature' || field.field_type === 'initials') {
                return (
                  <div>
                    <div className="row" style={{ gap: 8, marginBottom: 8 }}>
                      <button
                        type="button"
                        className={`btn${signMode === 'type' ? ' primary' : ''}`}
                        onClick={() => {
                          setSignMode('type')
                          void applyTypedStyle(styleIndex, field.id)
                        }}
                      >
                        Type
                      </button>
                      <button
                        type="button"
                        className={`btn${signMode === 'draw' ? ' primary' : ''}`}
                        onClick={() => setSignMode('draw')}
                      >
                        Draw
                      </button>
                    </div>
                    {signMode === 'type' ? (
                      <div>
                        <label className="field" style={{ marginBottom: 8 }}>
                          <span>Name for signature</span>
                          <input
                            value={signingName}
                            disabled={busy}
                            onChange={(e) => {
                              setSigningName(e.target.value)
                            }}
                            onBlur={() => void applyTypedStyle(styleIndex, field.id)}
                            placeholder="Your name as you sign"
                          />
                        </label>
                        <div
                          className="canarySignStylePreview"
                          style={{ fontFamily: `"${currentStyle.family}", cursive` }}
                        >
                          {(signingName || recipientName || 'Your name').trim()}
                        </div>
                        <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
                          Style: {currentStyle.label}
                        </div>
                        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                          <button type="button" className="btn" disabled={busy} onClick={() => void cycleSignatureStyle(-1)}>
                            ← Previous style
                          </button>
                          <button
                            type="button"
                            className="btn primary"
                            disabled={busy}
                            onClick={() => void cycleSignatureStyle(1)}
                          >
                            Next style →
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <canvas
                          ref={padRef}
                          width={480}
                          height={140}
                          style={{
                            width: '100%',
                            maxWidth: 480,
                            height: 140,
                            border: '1px solid #cbd5e1',
                            borderRadius: 8,
                            touchAction: 'none',
                            background: '#fff',
                          }}
                          onPointerDown={(e) => padPointer(e, 'down')}
                          onPointerMove={(e) => padPointer(e, 'move')}
                          onPointerUp={(e) => padPointer(e, 'up')}
                        />
                        <div className="row" style={{ gap: 8, marginTop: 8 }}>
                          <button type="button" className="btn" onClick={clearPad}>
                            Clear
                          </button>
                          <button type="button" className="btn primary" onClick={applyDrawnSignature}>
                            Use drawn signature
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                )
              }
              if (field.field_type === 'checkbox') {
                return (
                  <label className="row" style={{ gap: 8, alignItems: 'center' }}>
                    <input
                      type="checkbox"
                      checked={Boolean(drafts[field.id]?.checked)}
                      onChange={(e) =>
                        setDrafts((d) => ({ ...d, [field.id]: { ...d[field.id], checked: e.target.checked } }))
                      }
                    />
                    <span>{field.label || 'I agree'}</span>
                  </label>
                )
              }
              return null
            })()
          ) : null}

          {formFilledByOther ? (
            <label className="row" style={{ gap: 8, alignItems: 'flex-start', marginTop: 16 }}>
              <input
                type="checkbox"
                checked={reviewedAnswers}
                onChange={(e) => setReviewedAnswers(e.target.checked)}
              />
              <span style={{ fontSize: 14 }}>
                I have reviewed the answers completed by{' '}
                {signing.form_locked_by_name || 'the other recipient'} and I am content to sign.
              </span>
            </label>
          ) : null}

          <label className="row" style={{ gap: 8, alignItems: 'flex-start', marginTop: 16 }}>
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            <span style={{ fontSize: 14 }}>
              I agree to sign this document electronically. My signature is intended to be my electronic signature under
              the law of England and Wales.
            </span>
          </label>

          <div className="row" style={{ gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
            <button type="button" className="btn primary" disabled={busy} onClick={() => void submit()}>
              {busy ? 'Submitting…' : 'Complete signing'}
            </button>
            {!declineOpen ? (
              <button type="button" className="btn" disabled={busy} onClick={() => setDeclineOpen(true)}>
                Decline
              </button>
            ) : (
              <>
                <input
                  style={{ flex: '1 1 200px' }}
                  placeholder="Reason (optional)"
                  value={declineReason}
                  onChange={(e) => setDeclineReason(e.target.value)}
                />
                <button type="button" className="btn" disabled={busy} onClick={() => void decline()}>
                  Confirm decline
                </button>
                <button type="button" className="btn" disabled={busy} onClick={() => setDeclineOpen(false)}>
                  Cancel
                </button>
              </>
            )}
          </div>
        </div>
      ) : isReceipt ? null : (
        <div className="muted">
          {previewMode
            ? 'Staff preview — signing is disabled.'
            : missingPlacement
              ? null
              : waitingForFormFiller
                ? `${signing.form_locked_by_name || 'Another recipient'} is completing the form. You can review and sign once they finish.`
                : signing.status === 'pending'
                  ? 'Waiting for another signer to finish before you can sign.'
                  : `Status: ${signing.status}`}
        </div>
      )}
    </div>
  )
}
