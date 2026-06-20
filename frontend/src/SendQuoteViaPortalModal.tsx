import { useEffect, useMemo, useState } from 'react'
import { apiFetch } from './api'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import type { CasePortalFolderShareContactOut, QuotePortalDeliveryOut } from './types'

export type SendQuoteViaPortalModalProps = {
  token: string
  caseId: string
  fileId: string
  fileName?: string
  /** @deprecated Folder path no longer gates quote send — kept for call-site compatibility. */
  folderPath?: string
  preferredContactId?: string | null
  open: boolean
  onClose: () => void
  onSent?: () => void
}

export function SendQuoteViaPortalModal({
  token,
  caseId,
  fileId,
  fileName,
  folderPath: _folderPath = '',
  preferredContactId = null,
  open,
  onClose,
  onSent,
}: SendQuoteViaPortalModalProps) {
  const [recipients, setRecipients] = useState<CasePortalFolderShareContactOut[]>([])
  const [contactId, setContactId] = useState('')
  const [contactOpen, setContactOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [loadBusy, setLoadBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setErr(null)
    setNotice(null)
    setContactId('')
    setRecipients([])
    let cancelled = false
    void (async () => {
      setLoadBusy(true)
      try {
        const rows = await apiFetch<CasePortalFolderShareContactOut[]>(
          `/cases/${caseId}/portal/folder-share?grant_scope=matter`,
          { token },
        )
        if (cancelled) return
        setRecipients(rows)
        if (rows.length === 0) {
          setErr(
            'No contacts on this matter have active portal access. Enable portal access for a contact under Contacts first.',
          )
          return
        }
        const preferred =
          preferredContactId && rows.some((r) => r.contact_id === preferredContactId)
            ? preferredContactId
            : null
        setContactId(preferred ?? rows[0]?.contact_id ?? '')
      } catch (e: unknown) {
        if (!cancelled) setErr((e as { message?: string }).message ?? 'Could not load portal contacts')
      } finally {
        if (!cancelled) setLoadBusy(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [open, caseId, token, preferredContactId])

  const recipientOptions = useMemo(
    () => recipients.map((r) => ({ value: r.contact_id, label: r.contact_name })),
    [recipients],
  )

  async function send() {
    if (!contactId) return
    setBusy(true)
    setErr(null)
    setNotice(null)
    try {
      const out = await apiFetch<QuotePortalDeliveryOut>(
        `/cases/${caseId}/files/${fileId}/quote-portal/send`,
        { token, method: 'POST', json: { contact_id: contactId } },
      )
      const msg = out.email_sent
        ? `Quote sent to ${out.contact_name} via portal.`
        : `Quote queued for ${out.contact_name}; e-mail was not sent${out.email_skip_reason ? `: ${out.email_skip_reason}` : '.'}`
      setNotice(msg)
      onSent?.()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not send via portal')
    } finally {
      setBusy(false)
    }
  }

  if (!open) return null

  const title = fileName?.trim() ? `Send quote via portal — ${fileName.trim()}` : 'Send quote via portal'

  return (
    <div className="modalOverlay" role="dialog" aria-modal="true" onClick={() => !busy && onClose()}>
      <div className="modal card modal--scrollBody" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480 }}>
        <div className="paneHead">
          <h2 style={{ margin: 0, fontSize: 18 }}>{title}</h2>
          <button type="button" className="btn" disabled={busy} onClick={onClose}>
            Close
          </button>
        </div>
        <div className="stack modalBodyScroll" style={{ marginTop: 12, gap: 12 }}>
          {err ? <div className="error">{err}</div> : null}
          {notice ? <div className="notice">{notice}</div> : null}
          {loadBusy ? (
            <div className="muted">Loading portal contacts…</div>
          ) : (
            <>
              <p className="muted" style={{ margin: 0 }}>
                Choose the contact who will receive the quote and can accept or decline it on the portal. They need
                active portal access; sharing a document folder is not required.
              </p>
              <SingleSelectDropdown
                label="Portal contact"
                options={recipientOptions}
                value={contactId}
                onChange={setContactId}
                open={contactOpen}
                onOpenChange={setContactOpen}
                disabled={busy || recipientOptions.length === 0}
              />
              <div className="row" style={{ justifyContent: 'flex-end', gap: 8 }}>
                <button type="button" className="btn" disabled={busy} onClick={onClose}>
                  {notice ? 'Done' : 'Cancel'}
                </button>
                {!notice ? (
                  <button
                    type="button"
                    className="btn primary"
                    disabled={busy || !contactId || loadBusy}
                    onClick={() => void send()}
                  >
                    {busy ? 'Sending…' : 'Send via portal'}
                  </button>
                ) : null}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
