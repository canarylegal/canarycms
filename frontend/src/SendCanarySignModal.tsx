import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { apiFetch, apiUrl } from './api'
import {
  CANARY_SIGN_SIGNER_PALETTE,
  CanarySignPdfDocument,
  defaultFieldSize,
  fieldTypeLabel,
} from './CanarySignPdfDocument'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import type {
  CanarySignAcroFormFieldOut,
  CanarySignSendRecipientIn,
  CanarySignSigningRequestOut,
  CaseContactOut,
  CasePortalFolderShareContactOut,
} from './types'

type RecipientRow = CanarySignSendRecipientIn & { key: string }

type PlaceableFieldType = 'signature' | 'printed_name' | 'date' | 'initials' | 'checkbox'

type PlacedField = {
  key: string
  field_type: PlaceableFieldType
  recipientKey: string
  routing_order: number
  label: string
  required: boolean
  sort_order: number
  page: number
  x_pct: number
  y_pct: number
  w_pct: number
  h_pct: number
}

export type SendCanarySignModalProps = {
  token: string
  caseId: string
  fileId: string
  fileName: string
  caseContacts: CaseContactOut[]
  existing?: CanarySignSigningRequestOut | null
  amendFromId?: string | null
  open: boolean
  onClose: () => void
  onSent?: () => void
}

function newRecipient(order = 1): RecipientRow {
  return {
    key: crypto.randomUUID(),
    name: '',
    email: '',
    routing_order: order,
    case_contact_id: null,
    contact_id: null,
  }
}

function clampPlace(x: number, y: number, w: number, h: number) {
  return {
    x_pct: Math.max(0, Math.min(100 - w, x)),
    y_pct: Math.max(0, Math.min(100 - h, y)),
  }
}

export function SendCanarySignModal({
  token,
  caseId,
  fileId,
  fileName,
  caseContacts,
  existing = null,
  amendFromId = null,
  open,
  onClose,
  onSent,
}: SendCanarySignModalProps) {
  const [subject, setSubject] = useState('')
  const [orderMode, setOrderMode] = useState<'parallel' | 'sequential'>('parallel')
  const [expiresInDays, setExpiresInDays] = useState(14)
  const [recipients, setRecipients] = useState<RecipientRow[]>([newRecipient()])
  const [fields, setFields] = useState<PlacedField[]>([])
  const [activeRecipientKey, setActiveRecipientKey] = useState<string>('')
  const [placeType, setPlaceType] = useState<PlaceableFieldType>('signature')
  const [selectedFieldKey, setSelectedFieldKey] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [fillableFields, setFillableFields] = useState<CanarySignAcroFormFieldOut[]>([])
  /** null = not chosen yet; required before send when fillableFields.length > 0 */
  const [retainFillableForm, setRetainFillableForm] = useState<boolean | null>(null)
  /** contact_id → currently has active portal access */
  const [portalAccessByContactId, setPortalAccessByContactId] = useState<Record<string, boolean>>({})


  const contactOptions = useMemo(
    () =>
      caseContacts
        .filter((c) => (c.email || '').trim())
        .map((c) => ({
          value: c.id,
          label: `${c.name}${c.email ? ` (${c.email})` : ''}`,
          email: (c.email || '').trim(),
          name: c.name,
          contactId: c.contact_id ?? null,
        })),
    [caseContacts],
  )

  const previewPdfUrl = useMemo(
    () => apiUrl(`/cases/${caseId}/canary-sign/files/${fileId}/preview-pdf`),
    [caseId, fileId],
  )

  useEffect(() => {
    if (!open) return
    setErr(null)
    setNotice(null)
    setSubject(existing?.subject || fileName)
    setOrderMode((existing?.order_mode as 'parallel' | 'sequential') || 'parallel')
    setExpiresInDays(14)
    setPlaceType('signature')
    setSelectedFieldKey(null)

    let cancelled = false

    async function hydrate(from: CanarySignSigningRequestOut | null) {
      let nextRecipients: RecipientRow[]
      if (from?.recipients?.length) {
        nextRecipients = from.recipients.map((r, i) => ({
          key: r.id,
          name: r.name,
          email: r.email,
          routing_order: r.routing_order || i + 1,
          case_contact_id: r.case_contact_id ?? null,
          contact_id: r.contact_id ?? null,
        }))
      } else {
        nextRecipients = [newRecipient()]
      }
      if (cancelled) return
      setRecipients(nextRecipients)
      setActiveRecipientKey(nextRecipients[0]?.key || '')
      if (from?.subject) setSubject(from.subject)
      if (from?.order_mode === 'parallel' || from?.order_mode === 'sequential') {
        setOrderMode(from.order_mode)
      }

      if (from?.fields?.length && from.recipients?.length) {
        const byRecipientId = new Map(from.recipients.map((r) => [r.id, r]))
        setFields(
          from.fields
            .filter((f) => f.page != null)
            .map((f, i) => {
              const recip = byRecipientId.get(f.recipient_id)
              const recipientKey = recip?.id || nextRecipients[0]?.key || ''
              const size = defaultFieldSize(f.field_type)
              return {
                key: f.id,
                field_type: f.field_type as PlaceableFieldType,
                recipientKey,
                routing_order: recip?.routing_order || 1,
                label: f.label || fieldTypeLabel(f.field_type),
                required: f.required !== false,
                sort_order: f.sort_order ?? i,
                page: f.page as number,
                x_pct: f.x_pct ?? 10,
                y_pct: f.y_pct ?? 80,
                w_pct: f.w_pct ?? size.w_pct,
                h_pct: f.h_pct ?? size.h_pct,
              }
            }),
        )
      } else {
        setFields([])
      }
    }

    void (async () => {
      let from = existing && existing.recipients?.length ? existing : null
      const requestId = amendFromId || existing?.id
      if (requestId) {
        try {
          const rows = await apiFetch<CanarySignSigningRequestOut[]>(`/cases/${caseId}/canary-sign/requests`, {
            token,
          })
          const match = rows.find((r) => r.id === requestId) || null
          if (match) from = match
        } catch {
          // keep truncated existing / blank
        }
      }
      if (!cancelled) await hydrate(from)
    })()

    return () => {
      cancelled = true
    }
  }, [open, fileName, existing, amendFromId, caseId, token])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setPortalAccessByContactId({})
    void (async () => {
      try {
        const rows = await apiFetch<CasePortalFolderShareContactOut[]>(
          `/cases/${caseId}/portal/folder-share?grant_scope=matter&require_portal_access=false`,
          { token },
        )
        if (cancelled) return
        const map: Record<string, boolean> = {}
        for (const r of rows) {
          map[r.contact_id] = r.portal_access_active !== false
        }
        setPortalAccessByContactId(map)
      } catch {
        if (!cancelled) setPortalAccessByContactId({})
      }
    })()
    return () => {
      cancelled = true
    }
  }, [open, caseId, token])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setFillableFields([])
    setRetainFillableForm(null)
    void (async () => {
      try {
        const rows = await apiFetch<CanarySignAcroFormFieldOut[]>(
          `/cases/${caseId}/canary-sign/files/${fileId}/form-fields`,
          { token },
        )
        if (!cancelled) setFillableFields(rows || [])
      } catch {
        if (!cancelled) setFillableFields([])
      }
    })()
    return () => {
      cancelled = true
    }
  }, [open, caseId, fileId, token])

  const recipientsNeedingPortal = useMemo(() => {
    const names: string[] = []
    const seen = new Set<string>()
    for (const r of recipients) {
      const cid = (r.contact_id || '').trim()
      if (!cid || seen.has(cid)) continue
      if (portalAccessByContactId[cid] === false) {
        seen.add(cid)
        names.push(r.name?.trim() || 'Signer')
      }
    }
    return names
  }, [recipients, portalAccessByContactId])

  useEffect(() => {
    if (!open) return
    const prev = document.body.style.cursor
    if (busy) document.body.style.cursor = 'wait'
    else document.body.style.cursor = prev || ''
    return () => {
      document.body.style.cursor = prev || ''
    }
  }, [busy, open])

  useEffect(() => {
    if (!recipients.some((r) => r.key === activeRecipientKey)) {
      setActiveRecipientKey(recipients[0]?.key || '')
    }
  }, [recipients, activeRecipientKey])

  function applyContact(rowKey: string, caseContactId: string) {
    const contact = contactOptions.find((c) => c.value === caseContactId)
    if (!contact) return
    setRecipients((rows) =>
      rows.map((r) =>
        r.key === rowKey
          ? {
              ...r,
              name: contact.name,
              email: contact.email,
              case_contact_id: caseContactId,
              contact_id: contact.contactId,
            }
          : r,
      ),
    )
  }

  function placeOrMoveField(page: number, x_pct: number, y_pct: number) {
    // With a field selected, click repositions it; otherwise place a new field.
    if (selectedFieldKey) {
      setFields((rows) =>
        rows.map((f) => {
          if (f.key !== selectedFieldKey) return f
          const clamped = clampPlace(x_pct, y_pct, f.w_pct, f.h_pct)
          return { ...f, page, x_pct: clamped.x_pct, y_pct: clamped.y_pct }
        }),
      )
      setErr(null)
      return
    }
    const recip = recipients.find((r) => r.key === activeRecipientKey)
    if (!recip) {
      setErr('Select a signer before placing fields.')
      return
    }
    const size = defaultFieldSize(placeType)
    const clamped = clampPlace(x_pct, y_pct, size.w_pct, size.h_pct)
    const key = crypto.randomUUID()
    setFields((rows) => [
      ...rows,
      {
        key,
        field_type: placeType,
        recipientKey: recip.key,
        routing_order: recip.routing_order || 1,
        label: fieldTypeLabel(placeType),
        required: true,
        sort_order: rows.length,
        page,
        x_pct: clamped.x_pct,
        y_pct: clamped.y_pct,
        w_pct: size.w_pct,
        h_pct: size.h_pct,
      },
    ])
    setSelectedFieldKey(key)
    setErr(null)
  }

  function moveField(id: string, page: number, x_pct: number, y_pct: number) {
    setFields((rows) =>
      rows.map((f) => {
        if (f.key !== id) return f
        const clamped = clampPlace(x_pct, y_pct, f.w_pct, f.h_pct)
        return { ...f, page, x_pct: clamped.x_pct, y_pct: clamped.y_pct }
      }),
    )
    setSelectedFieldKey(id)
  }

  function resizeField(
    id: string,
    page: number,
    x_pct: number,
    y_pct: number,
    w_pct: number,
    h_pct: number,
  ) {
    setFields((rows) =>
      rows.map((f) => {
        if (f.key !== id) return f
        return {
          ...f,
          page,
          x_pct,
          y_pct,
          w_pct: Math.max(6, Math.min(100 - x_pct, w_pct)),
          h_pct: Math.max(3, Math.min(100 - y_pct, h_pct)),
        }
      }),
    )
    setSelectedFieldKey(id)
  }

  async function send() {
    setBusy(true)
    setErr(null)
    setNotice(null)
    try {
      const cleaned = recipients.map(({ key: _k, ...r }) => ({
        name: r.name.trim(),
        email: r.email.trim(),
        routing_order: r.routing_order,
        case_contact_id: r.case_contact_id,
        contact_id: r.contact_id,
      }))
      if (cleaned.some((r) => !r.name || !r.email)) {
        throw new Error('Each recipient needs a name and e-mail')
      }
      if (!fields.length) {
        throw new Error('Place at least one field on the document for each signer')
      }
      if (fillableFields.length && retainFillableForm === null) {
        throw new Error('Choose whether to keep or remove the fillable form fields before sending')
      }
      for (const r of recipients) {
        const theirs = fields.filter((f) => f.recipientKey === r.key)
        if (!theirs.length) {
          throw new Error(`Place fields for ${r.name.trim() || 'each signer'} on the document`)
        }
        if (!theirs.some((f) => f.field_type === 'signature' || f.field_type === 'initials')) {
          throw new Error(`Place a signature field for ${r.name.trim() || 'each signer'}`)
        }
      }
      const payload = {
        source_file_id: fileId,
        subject: subject.trim() || fileName,
        order_mode: orderMode,
        expires_in_days: expiresInDays,
        recipients: cleaned,
        retain_fillable_form: fillableFields.length ? retainFillableForm : null,
        fields: fields.map((f, i) => {
          const recip = recipients.find((r) => r.key === f.recipientKey)
          return {
            field_type: f.field_type,
            routing_order: recip?.routing_order || f.routing_order,
            label: f.label,
            required: f.required,
            sort_order: i,
            placement_mode: 'fixed' as const,
            page: f.page,
            x_pct: f.x_pct,
            y_pct: f.y_pct,
            w_pct: f.w_pct,
            h_pct: f.h_pct,
          }
        }),
      }
      const path = amendFromId
        ? `/cases/${caseId}/canary-sign/requests/${amendFromId}/amend`
        : `/cases/${caseId}/canary-sign/send`
      await apiFetch<CanarySignSigningRequestOut>(path, { token, method: 'POST', json: payload })
      setNotice(amendFromId ? 'Amended signing request sent.' : 'Document sent for signature.')
      onSent?.()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not send for signature')
    } finally {
      setBusy(false)
    }
  }

  if (!open) return null

  const title = amendFromId ? `Amend & re-send — ${fileName}` : `Send for signature — ${fileName}`
  const recipIndex = new Map(recipients.map((r, i) => [r.key, i]))

  const overlays = fields.map((f) => {
    const idx = recipIndex.get(f.recipientKey) ?? 0
    const recip = recipients.find((r) => r.key === f.recipientKey)
    const palette = CANARY_SIGN_SIGNER_PALETTE[idx % CANARY_SIGN_SIGNER_PALETTE.length]
    return {
      id: f.key,
      page: f.page,
      x_pct: f.x_pct,
      y_pct: f.y_pct,
      w_pct: f.w_pct,
      h_pct: f.h_pct,
      label: `${recip?.name?.trim() || `Signer ${idx + 1}`} · ${f.label}`,
      color: palette.border,
      fill: palette.fill,
      selected: selectedFieldKey === f.key,
      textStyle: 'plain' as const,
    }
  })

  const overlay = (
    <div
      className="modalOverlay emlPreviewOverlay"
      role="dialog"
      aria-modal="true"
      aria-busy={busy}
      style={{ cursor: busy ? 'wait' : undefined }}
      onClick={busy ? undefined : onClose}
    >
      <div
        className="modal card modal--scrollBody"
        style={{ maxWidth: 980, width: 'min(980px, 96vw)', cursor: busy ? 'wait' : undefined }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="paneHead">
          <div>
            <h2 style={{ margin: 0, fontSize: 18 }}>{title}</h2>
            <div className="muted">Canary Sign — place required fields, then send</div>
          </div>
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            Close
          </button>
        </div>
        <div className="stack modalBodyScroll" style={{ marginTop: 12, gap: 12 }}>
          {err ? <div className="error">{err}</div> : null}
          {notice ? <div className="notice">{notice}</div> : null}
          {recipientsNeedingPortal.length > 0 ? (
            <div className="notice">
              Portal access will be enabled for{' '}
              {recipientsNeedingPortal.length === 1
                ? recipientsNeedingPortal[0]
                : recipientsNeedingPortal.join(', ')}
              . Their signing invite will include an access code.
            </div>
          ) : null}

          <label className="field">
            <span>Subject</span>
            <input value={subject} onChange={(e) => setSubject(e.target.value)} disabled={busy} />
          </label>

          <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
            <label className="field" style={{ flex: '1 1 180px' }}>
              <span>Signing order</span>
              <SingleSelectDropdown
                label="Signing order"
                hideLabel
                value={orderMode}
                options={[
                  { value: 'parallel', label: 'Parallel (any order)' },
                  { value: 'sequential', label: 'Sequential (routing order)' },
                ]}
                onChange={(v) => setOrderMode(v as 'parallel' | 'sequential')}
                disabled={busy}
              />
            </label>
            <label className="field" style={{ flex: '0 0 140px' }}>
              <span>Expires (days)</span>
              <input
                type="number"
                min={1}
                max={365}
                value={expiresInDays}
                onChange={(e) => setExpiresInDays(Math.max(1, Math.min(365, Number(e.target.value) || 14)))}
                disabled={busy}
              />
            </label>
          </div>

          <div>
            <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <strong>Signers</strong>
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => {
                  const row = newRecipient(recipients.length + 1)
                  setRecipients((rows) => [...rows, row])
                  setActiveRecipientKey(row.key)
                }}
              >
                Add signer
              </button>
            </div>
            <div className="stack" style={{ gap: 10 }}>
              {recipients.map((r, idx) => (
                <div
                  key={r.key}
                  className="card"
                      style={{
                    padding: 12,
                    outline:
                      activeRecipientKey === r.key
                        ? `2px solid ${CANARY_SIGN_SIGNER_PALETTE[idx % CANARY_SIGN_SIGNER_PALETTE.length].border}`
                        : undefined,
                    borderLeft: `4px solid ${CANARY_SIGN_SIGNER_PALETTE[idx % CANARY_SIGN_SIGNER_PALETTE.length].border}`,
                    background: CANARY_SIGN_SIGNER_PALETTE[idx % CANARY_SIGN_SIGNER_PALETTE.length].fill,
                  }}
                >
                  <div className="row" style={{ gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
                    <label className="field" style={{ flex: '1 1 200px' }}>
                      <span>Matter contact</span>
                      <SingleSelectDropdown
                        label="Matter contact"
                        hideLabel
                        value={r.case_contact_id || ''}
                        options={[
                          { value: '', label: 'Manual entry' },
                          ...contactOptions.map((c) => ({ value: c.value, label: c.label })),
                        ]}
                        onChange={(v) => {
                          if (!v) {
                            setRecipients((rows) =>
                              rows.map((row) =>
                                row.key === r.key ? { ...row, case_contact_id: null, contact_id: null } : row,
                              ),
                            )
                            return
                          }
                          applyContact(r.key, v)
                        }}
                        disabled={busy}
                      />
                    </label>
                    <label className="field" style={{ flex: '0 0 90px' }}>
                      <span>Order</span>
                      <input
                        type="number"
                        min={1}
                        value={r.routing_order}
                        onChange={(e) => {
                          const n = Math.max(1, Number(e.target.value) || 1)
                          setRecipients((rows) =>
                            rows.map((row) => (row.key === r.key ? { ...row, routing_order: n } : row)),
                          )
                          setFields((fs) =>
                            fs.map((f) => (f.recipientKey === r.key ? { ...f, routing_order: n } : f)),
                          )
                        }}
                        disabled={busy}
                      />
                    </label>
                    <button
                      type="button"
                      className={`btn${activeRecipientKey === r.key ? ' primary' : ''}`}
                      style={{ alignSelf: 'end' }}
                      disabled={busy}
                      onClick={() => setActiveRecipientKey(r.key)}
                    >
                      Place for this signer
                    </button>
                    {recipients.length > 1 ? (
                      <button
                        type="button"
                        className="btn"
                        style={{ alignSelf: 'end' }}
                        disabled={busy}
                        onClick={() => {
                          setRecipients((rows) => rows.filter((row) => row.key !== r.key))
                          setFields((fs) => fs.filter((f) => f.recipientKey !== r.key))
                        }}
                      >
                        Remove
                      </button>
                    ) : null}
                  </div>
                  <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                    <label className="field" style={{ flex: '1 1 160px' }}>
                      <span>Name</span>
                      <input
                        value={r.name}
                        onChange={(e) =>
                          setRecipients((rows) =>
                            rows.map((row) => (row.key === r.key ? { ...row, name: e.target.value } : row)),
                          )
                        }
                        disabled={busy}
                      />
                    </label>
                    <label className="field" style={{ flex: '1 1 200px' }}>
                      <span>E-mail</span>
                      <input
                        type="email"
                        value={r.email}
                        onChange={(e) =>
                          setRecipients((rows) =>
                            rows.map((row) => (row.key === r.key ? { ...row, email: e.target.value } : row)),
                          )
                        }
                        disabled={busy}
                      />
                    </label>
                  </div>
                  <div className="muted" style={{ marginTop: 6, fontSize: 12 }}>
                    Signer {idx + 1}
                    {fields.filter((f) => f.recipientKey === r.key).length
                      ? ` · ${fields.filter((f) => f.recipientKey === r.key).length} field(s)`
                      : ' · no fields placed yet'}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div>
            {fillableFields.length ? (
              <div className="notice" style={{ marginBottom: 12 }}>
                <div style={{ marginBottom: 8 }}>
                  This PDF has <strong>{fillableFields.length}</strong> fillable form field
                  {fillableFields.length === 1 ? '' : 's'}. Choose what to do with them before sending:
                </div>
                <div className="stack" style={{ gap: 8 }}>
                  <label className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
                    <input
                      type="radio"
                      name="retainFillableForm"
                      checked={retainFillableForm === true}
                      onChange={() => setRetainFillableForm(true)}
                      disabled={busy}
                      style={{ marginTop: 3 }}
                    />
                    <span>
                      <strong>Keep fillable fields</strong>
                      <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
                        Recipients can fill them in the portal. The first person to start editing locks the form;
                        others review those answers and complete only their signature fields.
                      </div>
                    </span>
                  </label>
                  <label className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
                    <input
                      type="radio"
                      name="retainFillableForm"
                      checked={retainFillableForm === false}
                      onChange={() => setRetainFillableForm(false)}
                      disabled={busy}
                      style={{ marginTop: 3 }}
                    />
                    <span>
                      <strong>Remove fillable fields</strong>
                      <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
                        Strip interactive form fields from the signing copy. Recipients only complete the Canary Sign
                        fields you place below (signature, name, date, etc.).
                      </div>
                    </span>
                  </label>
                </div>
                {retainFillableForm === null ? (
                  <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
                    Select an option above to enable send.
                  </div>
                ) : null}
              </div>
            ) : null}
            <strong>Place fields on the document</strong>
            <p className="muted" style={{ margin: '6px 0 10px', fontSize: 13 }}>
              Choose a field type, then click to place. Drag to move; use the corner handle to resize. Each signer has a
              distinct colour.
            </p>
            <div className="row" style={{ gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
              {(
                [
                  ['signature', 'Signature'],
                  ['printed_name', 'Printed name'],
                  ['date', 'Date'],
                  ['initials', 'Initials'],
                  ['checkbox', 'Checkbox'],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  className={`btn${placeType === value && !selectedFieldKey ? ' primary' : ''}`}
                  disabled={busy}
                  onClick={() => {
                    setPlaceType(value)
                    setSelectedFieldKey(null)
                  }}
                >
                  {label}
                </button>
              ))}
              {selectedFieldKey ? (
                <>
                  <button type="button" className="btn" disabled={busy} onClick={() => setSelectedFieldKey(null)}>
                    Place new field
                  </button>
                  <button
                    type="button"
                    className="btn"
                    disabled={busy}
                    onClick={() => {
                      setFields((fs) => fs.filter((f) => f.key !== selectedFieldKey))
                      setSelectedFieldKey(null)
                    }}
                  >
                    Remove selected field
                  </button>
                </>
              ) : null}
            </div>
            <CanarySignPdfDocument
              pdfUrl={previewPdfUrl}
              authToken={token}
              overlays={overlays}
              placing={!busy && !selectedFieldKey}
              resizable={!busy}
              onPageClick={({ page, x_pct, y_pct }) => {
                if (busy) return
                placeOrMoveField(page, x_pct, y_pct)
              }}
              onOverlayClick={(id) => setSelectedFieldKey(id)}
              onOverlayMove={(id, { page, x_pct, y_pct }) => {
                if (busy) return
                moveField(id, page, x_pct, y_pct)
              }}
              onOverlayResize={(id, { page, x_pct, y_pct, w_pct, h_pct }) => {
                if (busy) return
                resizeField(id, page, x_pct, y_pct, w_pct, h_pct)
              }}
            />
          </div>

          <div className="row" style={{ justifyContent: 'flex-end', gap: 8 }}>
            <button type="button" className="btn" disabled={busy} onClick={onClose}>
              Cancel
            </button>
            <button
              type="button"
              className="btn primary"
              disabled={busy || (fillableFields.length > 0 && retainFillableForm === null)}
              onClick={() => void send()}
            >
              {busy ? 'Sending…' : amendFromId ? 'Amend & send' : 'Send for signature'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )

  return createPortal(overlay, document.body)
}
