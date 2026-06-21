import { useEffect, useMemo, useState } from 'react'
import { apiFetch } from './api'
import { lockBodyWaitCursor, unlockBodyWaitCursor } from './bodyCursorLock'
import { useDialogs } from './DialogProvider'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import type {
  CasePortalFolderShareContactOut,
  PortalFormSubmissionOut,
  PortalFormTemplateOut,
  QuotePortalSendPreflightOut,
} from './types'
import { PORTAL_ALERTS_NOT_CONFIGURED_MSG } from './types'

export type SendPortalFormModalProps = {
  token: string
  caseId: string
  open: boolean
  onClose: () => void
  onSent?: () => void
}

export function SendPortalFormModal({ token, caseId, open, onClose, onSent }: SendPortalFormModalProps) {
  const { askConfirm } = useDialogs()
  const [templates, setTemplates] = useState<PortalFormTemplateOut[]>([])
  const [recipients, setRecipients] = useState<CasePortalFolderShareContactOut[]>([])
  const [templateId, setTemplateId] = useState('')
  const [contactId, setContactId] = useState('')
  const [templateOpen, setTemplateOpen] = useState(false)
  const [contactOpen, setContactOpen] = useState(false)
  const [alertsConfigured, setAlertsConfigured] = useState<boolean | null>(null)
  const [busy, setBusy] = useState(false)
  const [loadBusy, setLoadBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    if (!busy) return
    lockBodyWaitCursor()
    return () => unlockBodyWaitCursor()
  }, [busy])

  useEffect(() => {
    if (!open) return
    setErr(null)
    setNotice(null)
    setTemplateId('')
    setContactId('')
    setTemplates([])
    setRecipients([])
    setAlertsConfigured(null)
    let cancelled = false
    void (async () => {
      setLoadBusy(true)
      try {
        const [tplRows, contactRows, preflight] = await Promise.all([
          apiFetch<PortalFormTemplateOut[]>(`/cases/${caseId}/portal/forms/templates`, { token }),
          apiFetch<CasePortalFolderShareContactOut[]>(
            `/cases/${caseId}/portal/folder-share?grant_scope=matter`,
            { token },
          ),
          apiFetch<QuotePortalSendPreflightOut>(`/cases/${caseId}/portal/forms/send-preflight`, { token }),
        ])
        if (cancelled) return
        setTemplates(Array.isArray(tplRows) ? tplRows : [])
        setRecipients(Array.isArray(contactRows) ? contactRows : [])
        setAlertsConfigured(preflight.alerts_configured)
        if (contactRows.length === 0) {
          setErr(
            'No contacts on this matter have active portal access. Enable portal access for a contact under Contacts first.',
          )
        } else {
          setContactId(contactRows[0]?.contact_id ?? '')
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
    () => templates.map((t) => ({ value: t.id, label: t.name })),
    [templates],
  )

  const recipientOptions = useMemo(
    () => recipients.map((r) => ({ value: r.contact_id, label: r.contact_name })),
    [recipients],
  )

  async function confirmSendWithoutEmail(): Promise<boolean> {
    return askConfirm({
      title: 'Send without e-mail notification?',
      message: `${PORTAL_ALERTS_NOT_CONFIGURED_MSG} The form will still be sent via the portal, but the contact will not receive an automated e-mail alert. Send anyway?`,
      confirmLabel: 'Send anyway',
      cancelLabel: 'Cancel',
    })
  }

  async function send() {
    if (!templateId || !contactId) return
    if (alertsConfigured === false) {
      const ok = await confirmSendWithoutEmail()
      if (!ok) return
    }
    setBusy(true)
    setErr(null)
    setNotice(null)
    try {
      const out = await apiFetch<PortalFormSubmissionOut>(`/cases/${caseId}/portal/forms/send`, {
        token,
        method: 'POST',
        json: { template_id: templateId, contact_id: contactId },
      })
      onSent?.()
      if (out.email_sent) {
        onClose()
        return
      }
      const msg = out.email_skip_reason
        ? `Form sent to ${out.contact_name} via portal; e-mail was not sent: ${out.email_skip_reason}`
        : `Form sent to ${out.contact_name} via portal; e-mail was not sent.`
      setNotice(msg)
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
          <h2 style={{ margin: 0, fontSize: 18 }}>New portal form</h2>
          <button type="button" className="btn" disabled={busy} onClick={onClose}>
            Close
          </button>
        </div>
        <div className="stack modalBodyScroll" style={{ marginTop: 12, gap: 12 }}>
          {err ? <div className="error">{err}</div> : null}
          {notice ? <div className="notice">{notice}</div> : null}
          {loadBusy ? <div className="muted">Loading…</div> : null}
          {!loadBusy && alertsConfigured === false ? (
            <div className="notice">{PORTAL_ALERTS_NOT_CONFIGURED_MSG}</div>
          ) : null}
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
            <>
              <p className="muted" style={{ margin: 0 }}>
                Choose the contact who will complete the form on the portal. They need active portal access; sharing a
                document folder is not required.
              </p>
              <SingleSelectDropdown
                label="Portal contact"
                options={recipientOptions}
                value={contactId}
                onChange={setContactId}
                open={contactOpen}
                onOpenChange={setContactOpen}
                disabled={busy}
                placeholder="Select contact…"
              />
            </>
          ) : null}
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>
            The form appears in document history with its status. Only one pending submission per contact and template at
            a time.
          </p>
          <div className="row" style={{ gap: 8, justifyContent: 'flex-end' }}>
            <button type="button" className="btn" disabled={busy} onClick={onClose}>
              {notice ? 'Done' : 'Cancel'}
            </button>
            {!notice ? (
              <button
                type="button"
                className="btn primary"
                disabled={busy || loadBusy || !templateId || !contactId}
                onClick={() => void send()}
              >
                {busy ? 'Sending…' : 'Send via portal'}
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}
