import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { apiUrl, applyAuthHeaders, formatApiErrorDetail } from './api'
import {
  CANARY_SIGN_SIGNER_PALETTE,
  CanarySignPdfDocument,
  fieldTypeLabel,
  formatUkDate,
  renderTypedSignaturePng,
  SIGNATURE_STYLES,
} from './CanarySignPdfDocument'
import type { CanarySignFieldOut, PortalCanarySignOut } from './types'

type Props = {
  signing: PortalCanarySignOut
  portalToken: string
  previewMode?: boolean
  onBack: () => void
  onCompleted: () => void
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

  useEffect(() => {
    setSigning(signingProp)
  }, [signingProp])

  function applySigning(next: PortalCanarySignOut) {
    setSigning(next)
    onSigningUpdated?.(next)
  }

  const recipientName = (signing.recipient_name || '').trim()

  const myFields = useMemo(
    () =>
      (signing.fields || [])
        .filter((f) => f.recipient_id === signing.recipient_id)
        .sort((a, b) => a.sort_order - b.sort_order),
    [signing.fields, signing.recipient_id],
  )

  const pdfUrl = useMemo(() => apiUrl(`/portal/canary-sign/${signing.id}/pdf`), [signing.id])
  const firstSigId = useMemo(
    () => myFields.find((f) => f.field_type === 'signature' || f.field_type === 'initials')?.id ?? null,
    [myFields],
  )

  useEffect(() => {
    const init: Record<string, FieldDraft> = {}
    for (const f of myFields) {
      if (f.field_type === 'date') init[f.id] = { text: formatUkDate() }
      else if (f.field_type === 'printed_name') init[f.id] = { text: recipientName }
      else if (f.field_type === 'checkbox') init[f.id] = { checked: false }
      else init[f.id] = {}
    }
    setDrafts(init)
    setSignMode('type')
    setStyleIndex(0)
    setActiveFieldId(firstSigId ?? myFields[0]?.id ?? null)
  }, [signing.id, recipientName, myFields, firstSigId])

  useEffect(() => {
    const next: Record<string, string | boolean> = {}
    for (const f of signing.form_fields || []) {
      const existing = signing.form_responses?.[f.name]
      if (f.field_type === 'checkbox') {
        next[f.name] = Boolean(existing) && String(existing).toLowerCase() !== 'off'
      } else {
        next[f.name] = existing != null ? String(existing) : f.current_value || ''
      }
    }
    setFormDrafts(next)
  }, [signing.id, signing.form_fields, signing.form_responses])

  const applyTypedStyle = useCallback(
    async (index: number, fieldId: string | null) => {
      if (!fieldId || !recipientName) return
      const field = myFields.find((f) => f.id === fieldId)
      if (!field || (field.field_type !== 'signature' && field.field_type !== 'initials')) return
      try {
        const image_b64 = await renderTypedSignaturePng(recipientName, { styleIndex: index })
        const style = SIGNATURE_STYLES[index % SIGNATURE_STYLES.length]
        setDrafts((d) => ({
          ...d,
          [fieldId]: { ...d[fieldId], image_b64, text: recipientName, style_id: style.id },
        }))
        setErr(null)
      } catch {
        setErr('Could not create typed signature.')
      }
    },
    [myFields, recipientName],
  )

  // Auto-apply first typed style when opening a signature field in type mode
  useEffect(() => {
    if (signMode !== 'type' || !activeFieldId || previewMode) return
    const field = myFields.find((f) => f.id === activeFieldId)
    if (!field || (field.field_type !== 'signature' && field.field_type !== 'initials')) return
    void applyTypedStyle(styleIndex, activeFieldId)
    // Only when field/mode changes — styleIndex changes handled by cycle button
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeFieldId, signMode, previewMode])

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
    if (signing.has_fillable_form && !signing.form_completed && !signing.form_lock_held_by_me) {
      setErr('Someone must fill and lock the form before signing can finish.')
      return
    }
    if (signing.has_fillable_form && signing.form_lock_held_by_me && !signing.form_completed) {
      // Ensure latest answers are included
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
      await portalFetchJson(`/portal/canary-sign/${signing.id}/sign`, {
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
      onCompleted()
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

  const canSign = signing.can_sign && !previewMode
  const missingPlacement = myFields.some((f) => f.page == null || f.x_pct == null || f.y_pct == null)
  const palette = CANARY_SIGN_SIGNER_PALETTE[0]
  const currentStyle = SIGNATURE_STYLES[styleIndex % SIGNATURE_STYLES.length]

  const overlays = myFields
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

  return (
    <div className="portalCanarySignPanel" style={{ marginTop: 16, cursor: busy ? 'wait' : undefined }} aria-busy={busy}>
      <div className="row" style={{ gap: 8, flexWrap: 'wrap', marginBottom: 12, alignItems: 'center' }}>
        <button type="button" className="btn" onClick={onBack} disabled={busy}>
          ← Back
        </button>
        <h2 style={{ margin: 0, flex: 1, fontSize: 18 }}>{signing.subject}</h2>
        <span className="portalActionBadge portalActionBadge--outstanding">Outstanding</span>
      </div>
      {signing.matter_label ? <div className="muted" style={{ marginBottom: 8 }}>{signing.matter_label}</div> : null}
      {signing.disclaimer ? <p className="muted" style={{ fontSize: 13 }}>{signing.disclaimer}</p> : null}
      {err ? <div className="error" style={{ marginBottom: 12 }}>{err}</div> : null}
      {missingPlacement ? (
        <div className="error" style={{ marginBottom: 12 }}>
          This signing request is missing field positions. Ask the sender to amend and re-send with fields placed on the
          document.
        </div>
      ) : null}

      <p className="muted" style={{ fontSize: 13, marginBottom: 8 }}>
        Coloured boxes show your signature fields. Choose a signature style below — your name and date are filled
        automatically.
      </p>

      {signing.has_fillable_form ? (
        <div className="card" style={{ padding: 16, marginBottom: 16 }}>
          <h3 style={{ marginTop: 0, fontSize: 16 }}>Fillable form</h3>
          {!signing.form_locked ? (
            <div>
              <p style={{ marginTop: 0, fontSize: 14 }}>
                This PDF has {(signing.form_fields || []).length} fillable field
                {(signing.form_fields || []).length === 1 ? '' : 's'}. The first recipient to start editing locks the
                form for everyone else.
              </p>
              {signing.can_claim_form_lock && !previewMode ? (
                !lockConfirmOpen ? (
                  <button type="button" className="btn primary" disabled={busy} onClick={() => setLockConfirmOpen(true)}>
                    Start filling this form
                  </button>
                ) : (
                  <div className="stack" style={{ gap: 8 }}>
                    <div className="notice">
                      Confirm: you will lock this form so only you can edit the fillable fields. Other recipients will
                      review your answers after you complete your part.
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
            <div>
              <div className="muted" style={{ marginBottom: 10, fontSize: 13 }}>
                {signing.form_completed
                  ? `Form completed by ${signing.form_locked_by_name || 'a recipient'} (read-only).`
                  : signing.form_lock_held_by_me
                    ? 'You hold the form lock — fill the fields below, then complete your signature.'
                    : `Locked by ${signing.form_locked_by_name || 'another recipient'} — you can review answers when available.`}
              </div>
              <div className="stack" style={{ gap: 10 }}>
                {(signing.form_fields || []).map((f) => {
                  const editable = Boolean(signing.can_edit_form && signing.form_lock_held_by_me && !previewMode)
                  const value = formDrafts[f.name]
                  return (
                    <div key={f.name}>
                      {f.field_type === 'checkbox' ? (
                        <label className="row" style={{ gap: 8, alignItems: 'center' }}>
                          <input
                            type="checkbox"
                            checked={Boolean(value)}
                            disabled={!editable || busy}
                            onChange={(e) => setFormDrafts((d) => ({ ...d, [f.name]: e.target.checked }))}
                          />
                          <span>{f.label || f.name}</span>
                        </label>
                      ) : f.field_type === 'choice' || f.field_type === 'radio' ? (
                        <label className="field">
                          <span>{f.label || f.name}</span>
                          <select
                            value={String(value ?? '')}
                            disabled={!editable || busy}
                            onChange={(e) => setFormDrafts((d) => ({ ...d, [f.name]: e.target.value }))}
                          >
                            <option value="">Select…</option>
                            {(f.options || []).map((opt) => (
                              <option key={opt} value={opt}>
                                {opt}
                              </option>
                            ))}
                          </select>
                        </label>
                      ) : (
                        <label className="field">
                          <span>{f.label || f.name}</span>
                          {f.multiline ? (
                            <textarea
                              rows={3}
                              value={String(value ?? '')}
                              disabled={!editable || busy}
                              onChange={(e) => setFormDrafts((d) => ({ ...d, [f.name]: e.target.value }))}
                            />
                          ) : (
                            <input
                              value={String(value ?? '')}
                              disabled={!editable || busy}
                              onChange={(e) => setFormDrafts((d) => ({ ...d, [f.name]: e.target.value }))}
                            />
                          )}
                        </label>
                      )}
                    </div>
                  )
                })}
              </div>
              {signing.form_lock_held_by_me && !signing.form_completed && !previewMode ? (
                <button
                  type="button"
                  className="btn"
                  style={{ marginTop: 12 }}
                  disabled={busy}
                  onClick={() => void saveFormDrafts()}
                >
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
        onOverlayClick={(id) => {
          const f = myFields.find((x) => x.id === id)
          if (f && isLockedField(f.field_type)) {
            setActiveFieldId(firstSigId)
            return
          }
          setActiveFieldId(id)
        }}
      />

      {canSign && !missingPlacement ? (
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
                        <div
                          className="canarySignStylePreview"
                          style={{ fontFamily: `"${currentStyle.family}", cursive` }}
                        >
                          {recipientName || 'Your name'}
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
      ) : (
        <div className="muted">
          {previewMode
            ? 'Staff preview — signing is disabled.'
            : missingPlacement
              ? null
              : signing.status === 'pending'
                ? 'Waiting for another signer, or this request is no longer available to you.'
                : `Status: ${signing.status}`}
        </div>
      )}
    </div>
  )
}
