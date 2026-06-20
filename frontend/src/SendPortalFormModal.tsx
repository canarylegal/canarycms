import { useEffect, useMemo, useState } from 'react'
import { apiFetch } from './api'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import type {
  CasePortalFolderShareContactOut,
  PortalFormSubmissionOut,
  PortalFormTemplateOut,
} from './types'

export type SendPortalFormModalProps = {
  token: string
  caseId: string
  open: boolean
  onClose: () => void
  onSent?: () => void
}

export function SendPortalFormModal({ token, caseId, open, onClose, onSent }: SendPortalFormModalProps) {
  const [templates, setTemplates] = useState<PortalFormTemplateOut[]>([])
  const [recipients, setRecipients] = useState<CasePortalFolderShareContactOut[]>([])
  const [templateId, setTemplateId] = useState('')
  const [contactId, setContactId] = useState('')
  const [templateOpen, setTemplateOpen] = useState(false)
  const [contactOpen, setContactOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [loadBusy, setLoadBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setErr(null)
    setNotice(null)
    setTemplateId('')
    setContactId('')
    setTemplates([])
    setRecipients([])
    let cancelled = false
    void (async () => {
      setLoadBusy(true)
      try {
        const [tplRows, contactRows] = await Promise.all([
          apiFetch<PortalFormTemplateOut[]>(`/cases/${caseId}/portal/forms/templates`, { token }),
          apiFetch<CasePortalFolderShareContactOut[]>(
            `/cases/${caseId}/portal/folder-share?grant_scope=matter`,
            { token },
          ),
        ])
        if (cancelled) return
        setTemplates(Array.isArray(tplRows) ? tplRows : [])
        setRecipients(Array.isArray(contactRows) ? contactRows : [])
        const eligible = contactRows.filter((r) => r.has_grant)
        if (eligible.length === 0) {
          setErr('No portal contacts have access to this matter. Share a folder under Portal first.')
        } else {
          setContactId(eligible[0]?.contact_id ?? '')
        }
        if (tplRows.length === 0) {
          setErr((prev) => prev ?? 'No form templates match this matter type. Add templates under Admin → Portal forms.')
        } else {
          setTemplateId(tplRows[0]?.id ?? '')
        }
      } catch (e: unknown) {
        if (!cancelled) setErr((e as { message?: string }).message ?? 'Could not load send options')
      } finally {
        if (!cancelled) setLoadBusy(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [open, caseId, token])

  const templateOptions = useMemo(
    () => templates.map((t) => ({ value: t.id, label: `${t.name} (${t.reference})` })),
    [templates],
  )

  const recipientOptions = useMemo(
    () =>
      recipients
        .filter((r) => r.has_grant)
        .map((r) => ({ value: r.contact_id, label: r.contact_name })),
    [recipients],
  )

  async function send() {
    if (!templateId || !contactId) return
    setBusy(true)
    setErr(null)
    setNotice(null)
    try {
      const out = await apiFetch<PortalFormSubmissionOut>(`/cases/${caseId}/portal/forms/send`, {
        token,
        method: 'POST',
        json: { template_id: templateId, contact_id: contactId },
      })
      setNotice(`Form sent to ${out.contact_name} via portal.`)
      onSent?.()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not send form')
    } finally {
      setBusy(false)
    }
  }

  if (!open) return null

  return (
    <div className="modalOverlay" role="dialog" aria-modal="true" onClick={() => !busy && onClose()}>
      <div className="modal card modal--scrollBody" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480 }}>
        <div className="paneHead">
          <h2 style={{ margin: 0, fontSize: 18 }}>Send portal form</h2>
          <button type="button" className="btn" disabled={busy} onClick={onClose}>
            Close
          </button>
        </div>
        <div className="stack modalBodyScroll" style={{ marginTop: 12, gap: 12 }}>
          {err ? <div className="error">{err}</div> : null}
          {notice ? <div className="notice">{notice}</div> : null}
          {loadBusy ? <div className="muted">Loading…</div> : null}
          {!loadBusy && templateOptions.length > 0 ? (
            <SingleSelectDropdown
              label="Form template"
              options={templateOptions}
              value={templateId}
              onChange={setTemplateId}
              open={templateOpen}
              onOpenChange={setTemplateOpen}
              disabled={busy}
              placeholder="Select template…"
            />
          ) : null}
          {!loadBusy && recipientOptions.length > 0 ? (
            <SingleSelectDropdown
              label="Contact"
              options={recipientOptions}
              value={contactId}
              onChange={setContactId}
              open={contactOpen}
              onOpenChange={setContactOpen}
              disabled={busy}
              placeholder="Select contact…"
            />
          ) : null}
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>
            The contact receives an e-mail alert and can complete the form in the portal. Only one pending submission
            per contact and template at a time.
          </p>
          <div className="row" style={{ gap: 8, justifyContent: 'flex-end' }}>
            <button type="button" className="btn" disabled={busy} onClick={onClose}>
              Cancel
            </button>
            <button
              type="button"
              className="btn primary"
              disabled={busy || loadBusy || !templateId || !contactId || !!notice}
              onClick={() => void send()}
            >
              {busy ? 'Sending…' : 'Send form'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
