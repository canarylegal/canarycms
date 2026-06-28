import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { apiFetch } from './api'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import type {
  CaseContactOut,
  DocusignSendRecipientIn,
  DocusignSigningRequestOut,
  DocusignStaffOptionsOut,
  DocusignTemplateOut,
} from './types'

type RecipientRow = DocusignSendRecipientIn & { key: string }

export type SendDocusignModalProps = {
  token: string
  caseId: string
  fileId: string
  fileName: string
  caseContacts: CaseContactOut[]
  existing?: DocusignSigningRequestOut | null
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
    role_name: null,
    case_contact_id: null,
    contact_id: null,
  }
}

export function SendDocusignModal({
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
}: SendDocusignModalProps) {
  const [options, setOptions] = useState<DocusignStaffOptionsOut | null>(null)
  const [templates, setTemplates] = useState<DocusignTemplateOut[]>([])
  const [templateId, setTemplateId] = useState('')
  const [subject, setSubject] = useState('')
  const [tier, setTier] = useState<'a' | 'b' | 'c'>('a')
  const [signatureLevel, setSignatureLevel] = useState<'standard' | 'wes' | 'qes'>('standard')
  const [recipients, setRecipients] = useState<RecipientRow[]>([newRecipient()])
  const [busy, setBusy] = useState(false)
  const [loadBusy, setLoadBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

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

  const selectedTemplate = templates.find((t) => t.template_id === templateId) ?? null

  useEffect(() => {
    if (!open) return
    setErr(null)
    setNotice(null)
    setSubject(fileName)
    setTemplateId('')
    setTier('a')
    setSignatureLevel('standard')
    setRecipients([newRecipient()])
    let cancelled = false
    void (async () => {
      setLoadBusy(true)
      try {
        const opt = await apiFetch<DocusignStaffOptionsOut>('/docusign/options', { token })
        if (cancelled) return
        setOptions(opt)
        try {
          const tpls = await apiFetch<DocusignTemplateOut[]>('/docusign/templates', { token })
          if (!cancelled) setTemplates(tpls)
        } catch (e: unknown) {
          if (!cancelled) {
            setTemplates([])
            setNotice((e as { message?: string }).message ?? 'Could not load DocuSign templates (optional).')
          }
        }
        if (cancelled) return
        if (existing?.recipients?.length) {
          setSubject(existing.envelope_subject || fileName)
          setTier((existing.document_tier as 'a' | 'b' | 'c') || 'a')
          setSignatureLevel((existing.signature_level as 'standard' | 'wes' | 'qes') || 'standard')
          setTemplateId(existing.docusign_template_id || '')
          setRecipients(
            existing.recipients.map((r, i) => ({
              key: r.id,
              name: r.name,
              email: r.email,
              routing_order: r.routing_order || i + 1,
              role_name: r.role_name,
              case_contact_id: null,
              contact_id: null,
            })),
          )
        }
      } catch (e: unknown) {
        if (!cancelled) setErr((e as { message?: string }).message ?? 'Could not load DocuSign options')
      } finally {
        if (!cancelled) setLoadBusy(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [open, token, fileName, existing])

  useEffect(() => {
    if (!selectedTemplate?.roles?.length) return
    setRecipients(
      selectedTemplate.roles.map((role, i) => ({
        ...newRecipient(i + 1),
        role_name: role,
      })),
    )
  }, [templateId, selectedTemplate?.template_id])

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

  async function send() {
    setBusy(true)
    setErr(null)
    setNotice(null)
    try {
      const payload = {
        source_file_id: templateId ? null : fileId,
        template_id: templateId || null,
        envelope_subject: subject.trim() || fileName,
        document_tier: tier,
        signature_level: signatureLevel,
        recipients: recipients.map(({ key: _k, ...r }) => ({
          name: r.name.trim(),
          email: r.email.trim(),
          routing_order: r.routing_order,
          role_name: r.role_name,
          case_contact_id: r.case_contact_id,
          contact_id: r.contact_id,
        })),
      }
      const path = amendFromId
        ? `/cases/${caseId}/docusign/requests/${amendFromId}/amend`
        : `/cases/${caseId}/docusign/send`
      await apiFetch<DocusignSigningRequestOut>(path, { token, method: 'POST', json: payload })
      setNotice(amendFromId ? 'Amended envelope sent.' : 'Document sent for signature via DocuSign.')
      onSent?.()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not send for signature')
    } finally {
      setBusy(false)
    }
  }

  if (!open) return null

  const title = amendFromId
    ? `Amend & re-send — ${fileName}`
    : `Send for signature — ${fileName}`

  const tierOptions = (
    [
      { value: 'a' as const, label: 'Tier A — client care / terms', enabled: !!options?.allow_tier_a },
      { value: 'b' as const, label: 'Tier B — contractual', enabled: !!options?.allow_tier_b },
      { value: 'c' as const, label: 'Tier C — Land Registry deeds', enabled: !!options?.allow_tier_c },
    ] as const
  ).filter((o) => o.enabled)

  const levelOptions = (
    [
      { value: 'standard' as const, label: 'Standard eSignature', enabled: true },
      { value: 'wes' as const, label: 'Witnessed (WES)', enabled: !!options?.allow_wes },
      { value: 'qes' as const, label: 'Qualified (QES)', enabled: !!options?.allow_qes },
    ] as const
  ).filter((o) => o.enabled)

  const overlay = (
    <div
      className="modalOverlay emlPreviewOverlay"
      role="dialog"
      aria-modal="true"
      onClick={() => !busy && onClose()}
    >
      <div
        className="modal card modal--scrollBody"
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: 560, width: 'min(560px, 96vw)' }}
      >
        <div className="paneHead">
          <h2 style={{ margin: 0, fontSize: 18 }}>{title}</h2>
          <button type="button" className="btn" disabled={busy} onClick={onClose}>
            Close
          </button>
        </div>
        <div className="stack modalBodyScroll" style={{ marginTop: 12, gap: 12 }}>
          {loadBusy ? <div className="muted">Loading…</div> : null}
          {err ? <div className="error">{err}</div> : null}
          {notice ? <div className="notice">{notice}</div> : null}

          {!loadBusy ? (
            <>
              <label className="field">
                <span>Envelope subject</span>
                <input className="input" value={subject} onChange={(e) => setSubject(e.target.value)} disabled={busy} />
              </label>

              {templates.length > 0 ? (
                <label className="field">
                  <span>DocuSign template (optional)</span>
                  <p className="muted" style={{ margin: '4px 0 0', fontSize: 13 }}>
                    Templates include pre-placed fields. Without a template, Canary places Sign here and Date on
                    the last page of the document.
                  </p>
                  <select className="input" value={templateId} onChange={(e) => setTemplateId(e.target.value)} disabled={busy}>
                    <option value="">Send this document (no template)</option>
                    {templates.map((t) => (
                      <option key={t.template_id} value={t.template_id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}

              <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
                {tierOptions.length > 1 ? (
                  <label className="field" style={{ flex: 1, minWidth: 160 }}>
                    <span>Document tier</span>
                    <select className="input" value={tier} onChange={(e) => setTier(e.target.value as 'a' | 'b' | 'c')} disabled={busy}>
                      {tierOptions.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}
                {levelOptions.length > 1 ? (
                  <label className="field" style={{ flex: 1, minWidth: 160 }}>
                    <span>Signature level</span>
                    <select
                      className="input"
                      value={signatureLevel}
                      onChange={(e) => setSignatureLevel(e.target.value as 'standard' | 'wes' | 'qes')}
                      disabled={busy}
                    >
                      {levelOptions.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : levelOptions.length === 1 ? (
                  <label className="field" style={{ flex: 1, minWidth: 160 }}>
                    <span>Signature level</span>
                    <select className="input" value={signatureLevel} disabled>
                      <option value={levelOptions[0].value}>{levelOptions[0].label}</option>
                    </select>
                  </label>
                ) : null}
              </div>
              {!templateId ? (
                <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                  Sign here and Date signed are placed on the last page automatically. For exact positions on
                  complex forms, use a DocuSign template.
                </p>
              ) : null}

              <div className="stack" style={{ gap: 8 }}>
                <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
                  <strong>Recipients</strong>
                  {!templateId ? (
                    <button
                      type="button"
                      className="btn"
                      disabled={busy}
                      onClick={() => setRecipients((r) => [...r, newRecipient(r.length + 1)])}
                    >
                      Add recipient
                    </button>
                  ) : null}
                </div>
                {recipients.map((row, idx) => (
                  <div
                    key={row.key}
                    className="stack"
                    style={{ gap: 8, padding: 10, border: '1px solid var(--border)', borderRadius: 8 }}
                  >
                    {templateId && row.role_name ? <div className="muted">Role: {row.role_name}</div> : null}
                    {contactOptions.length > 0 ? (
                      <SingleSelectDropdown
                        label="From matter contact"
                        value=""
                        options={[
                          { value: '', label: '— pick contact —' },
                          ...contactOptions.map((c) => ({ value: c.value, label: c.label })),
                        ]}
                        onChange={(v) => {
                          if (v) applyContact(row.key, v)
                        }}
                        disabled={busy}
                      />
                    ) : null}
                    <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                      <input
                        className="input"
                        placeholder="Name"
                        value={row.name}
                        onChange={(e) =>
                          setRecipients((rs) => rs.map((r) => (r.key === row.key ? { ...r, name: e.target.value } : r)))
                        }
                        disabled={busy}
                        style={{ flex: 1, minWidth: 120 }}
                      />
                      <input
                        className="input"
                        placeholder="Email"
                        value={row.email}
                        onChange={(e) =>
                          setRecipients((rs) => rs.map((r) => (r.key === row.key ? { ...r, email: e.target.value } : r)))
                        }
                        disabled={busy}
                        style={{ flex: 1, minWidth: 160 }}
                      />
                      <input
                        className="input"
                        type="number"
                        min={1}
                        max={99}
                        value={row.routing_order}
                        onChange={(e) =>
                          setRecipients((rs) =>
                            rs.map((r) =>
                              r.key === row.key ? { ...r, routing_order: Number(e.target.value) || 1 } : r,
                            ),
                          )
                        }
                        disabled={busy}
                        style={{ width: 72 }}
                        title="Signing order"
                      />
                    </div>
                    {!templateId && recipients.length > 1 ? (
                      <button
                        type="button"
                        className="btn"
                        disabled={busy}
                        onClick={() => setRecipients((rs) => rs.filter((r) => r.key !== row.key))}
                      >
                        Remove
                      </button>
                    ) : null}
                    {idx < recipients.length - 1 ? <div className="muted" style={{ fontSize: 12 }}>Then →</div> : null}
                  </div>
                ))}
              </div>

              <div className="row" style={{ justifyContent: 'flex-end', gap: 8 }}>
                <button type="button" className="btn" disabled={busy} onClick={onClose}>
                  {notice ? 'Done' : 'Cancel'}
                </button>
                {!notice ? (
                  <button type="button" className="btn primary" disabled={busy} onClick={() => void send()}>
                    {busy ? 'Sending…' : amendFromId ? 'Send amended envelope' : 'Send for signature'}
                  </button>
                ) : null}
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  )

  return createPortal(overlay, document.body)
}
