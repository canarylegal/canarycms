import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../api'
import { useDialogs } from '../DialogProvider'
import { MainMenuFilterCheckboxDropdown } from '../MainMenuFilterCheckboxDropdown'
import { SendQuoteViaPortalModal } from '../SendQuoteViaPortalModal'
import { SingleSelectDropdown } from '../SingleSelectDropdown'
import { CaseFileSelectDropdown } from './CaseFileSelectDropdown'
import { DocMimeIcon } from './DocCells'
import type {
  CanarySignRecipientOut,
  CanarySignSigningRequestOut,
  CasePortalActivityOut,
  CasePortalNotificationSettingsOut,
  CasePortalPreviewContactOut,
  CasePortalPreviewOut,
  CasePortalStaffUserOut,
  FileSummary,
  PortalFormSubmissionOut,
  QuotePortalDeliveryOut,
  UserSummary,
} from '../types'

type Props = {
  token: string
  caseId: string
  onFilesChanged?: () => void
}

function formatWhen(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
  } catch {
    return iso
  }
}

function staffUserLabel(u: Pick<CasePortalStaffUserOut, 'display_name' | 'email'>): string {
  const name = (u.display_name || '').trim()
  const email = (u.email || '').trim()
  if (name && email && name.toLowerCase() !== email.toLowerCase()) return `${name} (${email})`
  return name || email || 'Unknown user'
}

function previewContactSummary(row: CasePortalPreviewContactOut): string {
  const parts: string[] = []
  if (row.shared_folder_count > 0) {
    parts.push(
      row.shared_folder_count === 1 ? '1 shared folder' : `${row.shared_folder_count} shared folders`,
    )
  }
  const quotes = row.pending_quote_count ?? 0
  if (quotes > 0) {
    parts.push(quotes === 1 ? '1 quote' : `${quotes} quotes`)
  }
  const forms = row.pending_form_count ?? 0
  if (forms > 0) {
    parts.push(forms === 1 ? '1 form' : `${forms} forms`)
  }
  const signs = row.pending_canary_sign_count ?? 0
  if (signs > 0) {
    parts.push(signs === 1 ? '1 signature' : `${signs} signatures`)
  }
  return parts.length > 0 ? ` · ${parts.join(' · ')}` : ''
}

export function CasePortalPanel({ token, caseId, onFilesChanged }: Props) {
  const { askConfirm } = useDialogs()
  const [activity, setActivity] = useState<CasePortalActivityOut[]>([])
  const [previewContacts, setPreviewContacts] = useState<CasePortalPreviewContactOut[]>([])
  const [previewContactId, setPreviewContactId] = useState('')
  const [previewBusy, setPreviewBusy] = useState(false)
  const [selectedStaff, setSelectedStaff] = useState<CasePortalStaffUserOut[]>([])
  const [staffUsers, setStaffUsers] = useState<UserSummary[]>([])
  const [staffUsersBusy, setStaffUsersBusy] = useState(false)
  const [staffDropdownOpen, setStaffDropdownOpen] = useState(false)
  const [caseFiles, setCaseFiles] = useState<FileSummary[]>([])
  const [filesBusy, setFilesBusy] = useState(false)
  const [tagBusyFileId, setTagBusyFileId] = useState<string | null>(null)
  const [portalQuoteSend, setPortalQuoteSend] = useState<{
    fileId: string
    fileName: string
    folderPath: string
  } | null>(null)
  const [busy, setBusy] = useState(false)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [previewContactOpen, setPreviewContactOpen] = useState(false)
  const [quoteFileId, setQuoteFileId] = useState('')
  const [formSubmissions, setFormSubmissions] = useState<PortalFormSubmissionOut[]>([])
  const [formActionBusyId, setFormActionBusyId] = useState<string | null>(null)
  const [canaryRequests, setCanaryRequests] = useState<CanarySignSigningRequestOut[]>([])
  const [quoteResendBusyId, setQuoteResendBusyId] = useState<string | null>(null)
  const [signActionBusyId, setSignActionBusyId] = useState<string | null>(null)
  const [remindPicker, setRemindPicker] = useState<{
    request: CanarySignSigningRequestOut
    selected: Set<string>
  } | null>(null)

  const previewContactOptions = useMemo(
    () =>
      previewContacts.map((row) => ({
        value: row.contact_id,
        label: `${row.contact_name}${previewContactSummary(row)}`,
      })),
    [previewContacts],
  )

  const portalUrl = useMemo(() => {
    if (typeof window === 'undefined') return '/portal'
    return `${window.location.origin}/portal`
  }, [])

  const staffUserIds = useMemo(() => selectedStaff.map((u) => u.id), [selectedStaff])

  const staffOptions = useMemo(() => {
    const byId = new Map<string, { value: string; label: string }>()
    for (const u of staffUsers) {
      if (!u.is_active) continue
      byId.set(u.id, { value: u.id, label: staffUserLabel(u) })
    }
    // Keep currently selected recipients visible even if inactive.
    for (const u of selectedStaff) {
      if (!byId.has(u.id)) {
        byId.set(u.id, { value: u.id, label: staffUserLabel(u) })
      }
    }
    return Array.from(byId.values()).sort((a, b) => a.label.localeCompare(b.label, undefined, { sensitivity: 'base' }))
  }, [staffUsers, selectedStaff])

  const quotableFiles = useMemo(
    () => caseFiles.filter((f) => f.mime_type !== 'application/x-directory' && f.category !== 'system'),
    [caseFiles],
  )

  const taggedQuoteFiles = useMemo(
    () => quotableFiles.filter((f) => f.is_portal_quote),
    [quotableFiles],
  )

  const selectedQuoteFile = useMemo(
    () => quotableFiles.find((f) => f.id === quoteFileId) ?? null,
    [quotableFiles, quoteFileId],
  )

  const loadFiles = useCallback(async () => {
    setFilesBusy(true)
    try {
      const rows = await apiFetch<FileSummary[]>(`/cases/${caseId}/files`, { token })
      setCaseFiles(Array.isArray(rows) ? rows : [])
    } catch {
      setCaseFiles([])
    } finally {
      setFilesBusy(false)
    }
  }, [caseId, token])

  const loadFormSubmissions = useCallback(async () => {
    try {
      const rows = await apiFetch<PortalFormSubmissionOut[]>(`/cases/${caseId}/portal/forms/submissions`, { token })
      setFormSubmissions(Array.isArray(rows) ? rows : [])
    } catch {
      setFormSubmissions([])
    }
  }, [caseId, token])

  const loadCanaryRequests = useCallback(async () => {
    try {
      const rows = await apiFetch<CanarySignSigningRequestOut[]>(`/cases/${caseId}/canary-sign/requests`, { token })
      setCanaryRequests(Array.isArray(rows) ? rows : [])
    } catch {
      setCanaryRequests([])
    }
  }, [caseId, token])

  const load = useCallback(async () => {
    setErr(null)
    const [activityRows, settings, previewRows, users] = await Promise.all([
      apiFetch<CasePortalActivityOut[]>(`/cases/${caseId}/portal/activity`, { token }),
      apiFetch<CasePortalNotificationSettingsOut>(`/cases/${caseId}/portal/notification-settings`, { token }),
      apiFetch<CasePortalPreviewContactOut[]>(`/cases/${caseId}/portal/preview-contacts`, { token }),
      apiFetch<UserSummary[]>('/users', { token }).catch(() => [] as UserSummary[]),
    ])
    setActivity(activityRows)
    setSelectedStaff(settings.staff_users ?? [])
    setStaffUsers(Array.isArray(users) ? users : [])
    setPreviewContacts(previewRows)
    await Promise.all([loadFormSubmissions(), loadCanaryRequests()])
    setPreviewContactId((current) => {
      if (current && previewRows.some((row) => row.contact_id === current)) return current
      return previewRows[0]?.contact_id ?? ''
    })
    await loadFiles()
  }, [caseId, token, loadFiles, loadFormSubmissions, loadCanaryRequests])

  async function voidFormSubmission(submissionId: string) {
    const ok = await askConfirm({
      title: 'Void pending form?',
      message: 'The client will no longer be able to submit it.',
      danger: true,
      confirmLabel: 'Void form',
    })
    if (!ok) return
    setFormActionBusyId(submissionId)
    setErr(null)
    setNotice(null)
    try {
      await apiFetch<PortalFormSubmissionOut>(`/cases/${caseId}/portal/forms/submissions/${submissionId}/void`, {
        token,
        method: 'POST',
      })
      await loadFormSubmissions()
      await load()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not void form')
    } finally {
      setFormActionBusyId(null)
    }
  }

  async function resendFormSubmission(submissionId: string) {
    const ok = await askConfirm({
      title: 'Resend form?',
      message: 'The client will receive another e-mail with a link to complete this form.',
      confirmLabel: 'Resend',
    })
    if (!ok) return
    setFormActionBusyId(submissionId)
    setErr(null)
    setNotice(null)
    try {
      const out = await apiFetch<PortalFormSubmissionOut>(
        `/cases/${caseId}/portal/forms/submissions/${submissionId}/resend`,
        { token, method: 'POST' },
      )
      if (out.email_sent === false) {
        setNotice(out.email_skip_reason || 'Form is still available, but the notification e-mail was not sent.')
      } else {
        setNotice('Form resent.')
      }
      await loadFormSubmissions()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not resend form')
    } finally {
      setFormActionBusyId(null)
    }
  }

  async function resendQuote(fileId: string) {
    const ok = await askConfirm({
      title: 'Resend quote?',
      message: 'The client will receive another e-mail with a link to this quote.',
      confirmLabel: 'Resend',
    })
    if (!ok) return
    setQuoteResendBusyId(fileId)
    setErr(null)
    setNotice(null)
    try {
      const out = await apiFetch<QuotePortalDeliveryOut>(
        `/cases/${caseId}/files/${fileId}/quote-portal/resend`,
        { token, method: 'POST' },
      )
      if (out.email_sent === false) {
        setNotice(out.email_skip_reason || 'Quote is still available, but the notification e-mail was not sent.')
      } else {
        setNotice('Quote resent.')
      }
      await loadFiles()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not resend quote')
    } finally {
      setQuoteResendBusyId(null)
    }
  }

  function outstandingSignRecipients(req: CanarySignSigningRequestOut): CanarySignRecipientOut[] {
    return (req.recipients || []).filter((r) => r.status === 'pending' || r.status === 'viewed')
  }

  function openRemindPicker(req: CanarySignSigningRequestOut) {
    const outstanding = outstandingSignRecipients(req)
    setRemindPicker({
      request: req,
      selected: new Set(outstanding.map((r) => r.id)),
    })
  }

  async function confirmRemind() {
    if (!remindPicker) return
    const ids = Array.from(remindPicker.selected)
    if (ids.length === 0) {
      setErr('Select at least one recipient to remind.')
      return
    }
    setSignActionBusyId(remindPicker.request.id)
    setErr(null)
    setNotice(null)
    try {
      await apiFetch(`/cases/${caseId}/canary-sign/requests/${remindPicker.request.id}/remind`, {
        token,
        method: 'POST',
        json: { recipient_ids: ids },
      })
      setNotice(ids.length === 1 ? 'Reminder sent.' : `Reminders sent to ${ids.length} recipients.`)
      setRemindPicker(null)
      await loadCanaryRequests()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not send reminder')
    } finally {
      setSignActionBusyId(null)
    }
  }

  async function voidCanarySign(req: CanarySignSigningRequestOut) {
    const ok = await askConfirm({
      title: 'Void signing request?',
      message: 'Recipients will no longer be able to sign this document.',
      danger: true,
      confirmLabel: 'Void',
    })
    if (!ok) return
    setSignActionBusyId(req.id)
    setErr(null)
    setNotice(null)
    try {
      await apiFetch(`/cases/${caseId}/canary-sign/requests/${req.id}/void`, {
        token,
        method: 'POST',
        json: { reason: null },
      })
      setNotice('Signing request voided.')
      await loadCanaryRequests()
      onFilesChanged?.()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not void signing request')
    } finally {
      setSignActionBusyId(null)
    }
  }

  function formStatusLabel(status: string): string {
    if (status === 'pending') return 'Awaiting client'
    if (status === 'completed') return 'Completed'
    if (status === 'voided') return 'Voided'
    if (status === 'superseded') return 'Superseded'
    return status
  }

  function canaryStatusLabel(status: string): string {
    if (status === 'pending') return 'Awaiting signatures'
    if (status === 'completed') return 'Completed'
    if (status === 'declined') return 'Declined'
    if (status === 'voided') return 'Voided'
    if (status === 'expired') return 'Expired'
    return status
  }

  function recipientStatusLabel(status: string): string {
    if (status === 'pending') return 'Outstanding'
    if (status === 'viewed') return 'Viewed'
    if (status === 'signed') return 'Signed'
    if (status === 'declined') return 'Declined'
    return status
  }

  useEffect(() => {
    void (async () => {
      setBusy(true)
      setStaffUsersBusy(true)
      try {
        await load()
      } catch (e: unknown) {
        setErr((e as { message?: string }).message ?? 'Failed to load portal settings')
      } finally {
        setBusy(false)
        setStaffUsersBusy(false)
      }
    })()
  }, [load])

  function onStaffSelectionChange(nextIds: string[]) {
    const byId = new Map<string, CasePortalStaffUserOut>()
    for (const u of selectedStaff) {
      byId.set(u.id, u)
    }
    for (const u of staffUsers) {
      byId.set(u.id, { id: u.id, display_name: u.display_name, email: u.email })
    }
    setSelectedStaff(
      nextIds
        .map((id) => byId.get(id))
        .filter((u): u is CasePortalStaffUserOut => Boolean(u)),
    )
  }

  async function openClientPreview() {
    if (!previewContactId) return
    setPreviewBusy(true)
    setErr(null)
    try {
      const out = await apiFetch<CasePortalPreviewOut>(`/cases/${caseId}/portal/preview`, {
        token,
        method: 'POST',
        json: { contact_id: previewContactId },
      })
      const path = out.preview_url.startsWith('/') ? out.preview_url : `/${out.preview_url}`
      window.open(`${window.location.origin}${path}`, '_blank', 'noopener,noreferrer')
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not open preview')
    } finally {
      setPreviewBusy(false)
    }
  }

  async function setPortalQuoteTag(file: FileSummary, isPortalQuote: boolean) {
    setTagBusyFileId(file.id)
    setErr(null)
    setNotice(null)
    try {
      await apiFetch(`/cases/${caseId}/files/${file.id}/portal-quote-tag`, {
        token,
        method: 'PATCH',
        json: { is_portal_quote: isPortalQuote },
      })
      await loadFiles()
      onFilesChanged?.()
      setNotice(isPortalQuote ? 'Document marked as quotable.' : 'Quotable mark removed.')
      if (!isPortalQuote && quoteFileId === file.id) {
        setQuoteFileId('')
      }
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not update quotable mark')
    } finally {
      setTagBusyFileId(null)
    }
  }

  async function saveStaffRecipients() {
    setSaving(true)
    setErr(null)
    setNotice(null)
    try {
      const out = await apiFetch<CasePortalNotificationSettingsOut>(`/cases/${caseId}/portal/notification-settings`, {
        token,
        method: 'PUT',
        json: { staff_user_ids: staffUserIds },
      })
      setSelectedStaff(out.staff_users ?? [])
      setNotice('Staff notification recipients saved.')
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not save settings')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
    <div className="card caseDocEditEmbed stack" style={{ gap: 16 }}>
      <div>
        <h3 style={{ margin: 0, marginBottom: 6 }}>Client portal</h3>
        <p className="muted" style={{ margin: 0 }}>
          Share folders from Documents (right-click → Portal → Share). Clients sign in at{' '}
          <a href={portalUrl} target="_blank" rel="noreferrer">
            {portalUrl}
          </a>
          .
        </p>
      </div>

      <section className="stack portalPreviewSection" style={{ gap: 8 }}>
        <h4 style={{ margin: 0 }}>Preview client view</h4>
        <p className="muted" style={{ margin: 0 }}>
          Open the portal as a contact on this matter — no access code needed. Contacts with portal login and shared
          folders, pending quotes, and/or pending forms on this matter are listed.
        </p>
        {busy && previewContacts.length === 0 ? <div className="muted">Loading contacts…</div> : null}
        {!busy && previewContacts.length === 0 ? (
          <div className="muted">
            No previewable contacts yet. Grant portal access on the contact card, then share a folder, send a quote, or
            send a form on this matter.
          </div>
        ) : null}
        {previewContacts.length > 0 ? (
          <div className="row portalPreviewRow">
            <div className="portalPreviewContactSelect">
              <SingleSelectDropdown
                label="Contact to preview"
                options={previewContactOptions}
                value={previewContactId}
                onChange={setPreviewContactId}
                open={previewContactOpen}
                onOpenChange={setPreviewContactOpen}
                disabled={previewBusy || busy}
                placeholder="Select contact…"
              />
            </div>
            <button
              type="button"
              className="btn primary portalPreviewBtn"
              disabled={previewBusy || busy || !previewContactId}
              onClick={() => void openClientPreview()}
            >
              {previewBusy ? 'Opening…' : 'Preview as contact'}
            </button>
          </div>
        ) : null}
      </section>

      <section className="stack" style={{ gap: 8 }}>
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
          <h4 style={{ margin: 0 }}>Portal quotes</h4>
          <button type="button" className="btn" disabled={filesBusy} onClick={() => void loadFiles()}>
            Refresh
          </button>
        </div>
        <p className="muted" style={{ margin: 0 }}>
          Mark documents as quotable so Canary treats them as quotes for portal accept/decline when you send them.
          Sending via portal also marks the document automatically and creates a PDF snapshot for clients to read on
          mobile. Saving a marked quote as PDF moves the mark to the PDF and clears it from the source document.
        </p>
        {filesBusy && quotableFiles.length === 0 ? <div className="muted">Loading documents…</div> : null}
        {!filesBusy && quotableFiles.length === 0 ? (
          <div className="muted">No documents on this matter yet.</div>
        ) : null}
        {quotableFiles.length > 0 ? (
          <div className="stack" style={{ gap: 10 }}>
            <CaseFileSelectDropdown
              label="Document"
              files={quotableFiles}
              value={quoteFileId}
              onChange={setQuoteFileId}
              disabled={filesBusy}
              placeholder="Select document…"
            />
            {selectedQuoteFile ? (
              <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                {selectedQuoteFile.is_portal_quote ? (
                  <>
                    <button
                      type="button"
                      className="btn primary"
                      disabled={tagBusyFileId === selectedQuoteFile.id || filesBusy}
                      onClick={() =>
                        setPortalQuoteSend({
                          fileId: selectedQuoteFile.id,
                          fileName: selectedQuoteFile.original_filename,
                          folderPath: selectedQuoteFile.folder_path ?? '',
                        })
                      }
                    >
                      Send quote via portal
                    </button>
                    <button
                      type="button"
                      className="btn"
                      disabled={tagBusyFileId === selectedQuoteFile.id || filesBusy}
                      onClick={() => void setPortalQuoteTag(selectedQuoteFile, false)}
                    >
                      {tagBusyFileId === selectedQuoteFile.id ? 'Updating…' : 'Remove quotable mark'}
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    className="btn"
                    disabled={tagBusyFileId === selectedQuoteFile.id || filesBusy}
                    onClick={() => void setPortalQuoteTag(selectedQuoteFile, true)}
                  >
                    {tagBusyFileId === selectedQuoteFile.id ? 'Updating…' : 'Mark as quotable'}
                  </button>
                )}
              </div>
            ) : (
              <div className="muted">Select a document to mark it or send it via the portal.</div>
            )}
            {taggedQuoteFiles.length > 0 ? (
              <div className="stack" style={{ gap: 6 }}>
                <div className="muted" style={{ fontSize: 13 }}>
                  Marked quotable ({taggedQuoteFiles.length})
                </div>
                {taggedQuoteFiles.map((f) => (
                  <div
                    key={f.id}
                    className="row"
                    style={{ gap: 8, flexWrap: 'wrap', alignItems: 'center', fontSize: 14 }}
                  >
                    <button
                      type="button"
                      className="portalStaffSearchHit rowbtn caseFileSelectQuickPick"
                      disabled={filesBusy}
                      onClick={() => setQuoteFileId(f.id)}
                    >
                      <span className="caseFileSelectOptionIcon" aria-hidden>
                        <DocMimeIcon mime={f.mime_type} filename={f.original_filename} />
                      </span>
                      <span>{f.original_filename}</span>
                    </button>
                    {f.quote_portal_delivery ? (
                      <span className="muted" style={{ fontSize: 13 }}>
                        {f.quote_portal_delivery.status === 'pending'
                          ? `Awaiting ${f.quote_portal_delivery.contact_name}`
                          : f.quote_portal_delivery.status}
                      </span>
                    ) : (
                      <span className="muted" style={{ fontSize: 13 }}>
                        Not sent yet
                      </span>
                    )}
                    {f.quote_portal_delivery?.status === 'pending' ? (
                      <button
                        type="button"
                        className="btn"
                        disabled={quoteResendBusyId === f.id || filesBusy}
                        onClick={() => void resendQuote(f.id)}
                      >
                        {quoteResendBusyId === f.id ? 'Resending…' : 'Resend'}
                      </button>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </section>

      <section className="stack" style={{ gap: 8 }}>
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
          <h4 style={{ margin: 0 }}>Portal forms</h4>
          <button type="button" className="btn" disabled={busy} onClick={() => void loadFormSubmissions()}>
            Refresh
          </button>
        </div>
        <p className="muted" style={{ margin: 0 }}>
          Send forms from Documents → New → Portal form. Submissions appear here with status; you can resend or void
          pending forms.
        </p>
        {formSubmissions.length === 0 ? (
          <div className="muted">No portal forms sent on this matter yet.</div>
        ) : (
          <div className="table">
            <div className="tr th" style={{ gridTemplateColumns: '1fr 140px 120px 160px' }}>
              <div className="thCell">Form</div>
              <div className="thCell">Contact</div>
              <div className="thCell">Status</div>
              <div className="thCell">Actions</div>
            </div>
            {formSubmissions.map((row) => (
              <div key={row.id} className="tr" style={{ gridTemplateColumns: '1fr 140px 120px 160px' }}>
                <div className="td">
                  <div>{row.template_name}</div>
                  <div className="muted" style={{ fontSize: 12 }}>{formatWhen(row.sent_at)}</div>
                </div>
                <div className="td">{row.contact_name}</div>
                <div className="td muted">{formStatusLabel(row.status)}</div>
                <div className="td">
                  {row.status === 'pending' ? (
                    <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                      <button
                        type="button"
                        className="btn"
                        disabled={formActionBusyId === row.id}
                        onClick={() => void resendFormSubmission(row.id)}
                      >
                        {formActionBusyId === row.id ? '…' : 'Resend'}
                      </button>
                      <button
                        type="button"
                        className="btn"
                        disabled={formActionBusyId === row.id}
                        onClick={() => void voidFormSubmission(row.id)}
                      >
                        Void
                      </button>
                    </div>
                  ) : row.snapshot_filename ? (
                    <span className="muted" style={{ fontSize: 12 }}>{row.snapshot_filename}</span>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="stack" style={{ gap: 8 }}>
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
          <h4 style={{ margin: 0 }}>Canary Sign</h4>
          <button type="button" className="btn" disabled={busy} onClick={() => void loadCanaryRequests()}>
            Refresh
          </button>
        </div>
        <p className="muted" style={{ margin: 0 }}>
          Documents sent for signature from the matter file list. Remind outstanding recipients or void a pending
          request.
        </p>
        {canaryRequests.length === 0 ? (
          <div className="muted">No Canary Sign requests on this matter yet.</div>
        ) : (
          <div className="table">
            <div className="tr th" style={{ gridTemplateColumns: '1.2fr 1fr 120px 160px' }}>
              <div className="thCell">Document</div>
              <div className="thCell">Recipients</div>
              <div className="thCell">Status</div>
              <div className="thCell">Actions</div>
            </div>
            {canaryRequests.map((req) => {
              const outstanding = outstandingSignRecipients(req)
              return (
                <div key={req.id} className="tr" style={{ gridTemplateColumns: '1.2fr 1fr 120px 160px' }}>
                  <div className="td">
                    <div>{req.subject || req.source_filename || 'Document'}</div>
                    <div className="muted" style={{ fontSize: 12 }}>
                      {req.created_at ? formatWhen(req.created_at) : ''}
                    </div>
                  </div>
                  <div className="td" style={{ fontSize: 13 }}>
                    {(req.recipients || []).length === 0 ? (
                      <span className="muted">—</span>
                    ) : (
                      <div className="stack" style={{ gap: 2 }}>
                        {(req.recipients || []).map((r) => (
                          <div key={r.id}>
                            {r.name}{' '}
                            <span className="muted">({recipientStatusLabel(r.status)})</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="td muted">{canaryStatusLabel(req.status)}</div>
                  <div className="td">
                    {req.status === 'pending' ? (
                      <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                        {outstanding.length > 0 ? (
                          <button
                            type="button"
                            className="btn"
                            disabled={signActionBusyId === req.id}
                            onClick={() => openRemindPicker(req)}
                          >
                            Resend
                          </button>
                        ) : null}
                        <button
                          type="button"
                          className="btn"
                          disabled={signActionBusyId === req.id}
                          onClick={() => void voidCanarySign(req)}
                        >
                          Void
                        </button>
                      </div>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </section>

      {err ? <div className="error">{err}</div> : null}
      {notice ? <div className="notice">{notice}</div> : null}

      <section className="stack" style={{ gap: 8 }}>
        <h4 style={{ margin: 0 }}>Staff e-mail notifications</h4>
        <p className="muted" style={{ margin: 0 }}>
          When a client uploads, completes a form, or responds to a quote via the portal, these staff members receive
          an e-mail. If none are selected, the fee earner is notified.
        </p>

        <MainMenuFilterCheckboxDropdown
          label="Staff to notify"
          options={staffOptions}
          selected={staffUserIds}
          onChange={onStaffSelectionChange}
          open={staffDropdownOpen}
          onOpenChange={setStaffDropdownOpen}
          emptyLabel="Fee earner (default)"
        />
        {staffUsersBusy && staffOptions.length === 0 ? <div className="muted">Loading staff…</div> : null}
        {!staffUsersBusy && staffOptions.length === 0 ? (
          <div className="muted">No active staff users available.</div>
        ) : null}

        <button type="button" className="btn primary" disabled={saving || busy} onClick={() => void saveStaffRecipients()}>
          {saving ? 'Saving…' : 'Save recipients'}
        </button>
      </section>

      <section className="stack" style={{ gap: 8 }}>
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
          <h4 style={{ margin: 0 }}>Portal activity</h4>
          <button type="button" className="btn" disabled={busy} onClick={() => void load()}>
            Refresh
          </button>
        </div>
        {busy && activity.length === 0 ? <div className="muted">Loading activity…</div> : null}
        {!busy && activity.length === 0 ? <div className="muted">No portal activity recorded yet.</div> : null}
        {activity.length > 0 ? (
          <div className="stack" style={{ gap: 6 }}>
            {activity.map((row) => (
              <div key={row.id} className="card" style={{ padding: '8px 12px' }}>
                <div>{row.summary}</div>
                <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
                  {formatWhen(row.created_at)}
                  {row.contact_name ? ` · ${row.contact_name}` : ''}
                </div>
              </div>
            ))}
          </div>
        ) : null}
      </section>
    </div>

    {portalQuoteSend ? (
      <SendQuoteViaPortalModal
        token={token}
        caseId={caseId}
        fileId={portalQuoteSend.fileId}
        fileName={portalQuoteSend.fileName}
        folderPath={portalQuoteSend.folderPath}
        open
        onClose={() => setPortalQuoteSend(null)}
        onSent={() => {
          void loadFiles()
          onFilesChanged?.()
        }}
      />
    ) : null}

    {remindPicker ? (
      <div className="modalOverlay" role="dialog" aria-modal="true" aria-labelledby="canary-remind-title">
        <div className="card modal" style={{ maxWidth: 440, padding: 20 }}>
          <h3 id="canary-remind-title" style={{ marginTop: 0 }}>
            Resend signing reminder
          </h3>
          <p className="muted" style={{ marginTop: 0 }}>
            Choose who should receive another e-mail. Recipients who have already signed cannot be selected.
          </p>
          <div className="stack" style={{ gap: 8, marginBottom: 16 }}>
            {(remindPicker.request.recipients || []).map((r) => {
              const outstanding = r.status === 'pending' || r.status === 'viewed'
              const checked = remindPicker.selected.has(r.id)
              return (
                <label
                  key={r.id}
                  className="row"
                  style={{
                    gap: 8,
                    alignItems: 'center',
                    opacity: outstanding ? 1 : 0.55,
                  }}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={!outstanding}
                    onChange={(e) => {
                      setRemindPicker((prev) => {
                        if (!prev) return prev
                        const next = new Set(prev.selected)
                        if (e.target.checked) next.add(r.id)
                        else next.delete(r.id)
                        return { ...prev, selected: next }
                      })
                    }}
                  />
                  <span>
                    {r.name}{' '}
                    <span className="muted">({recipientStatusLabel(r.status)})</span>
                  </span>
                </label>
              )
            })}
          </div>
          <div className="row" style={{ gap: 8, justifyContent: 'flex-end' }}>
            <button type="button" className="btn" disabled={signActionBusyId === remindPicker.request.id} onClick={() => setRemindPicker(null)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn primary"
              disabled={signActionBusyId === remindPicker.request.id || remindPicker.selected.size === 0}
              onClick={() => void confirmRemind()}
            >
              {signActionBusyId === remindPicker.request.id ? 'Sending…' : 'Send reminder'}
            </button>
          </div>
        </div>
      </div>
    ) : null}
    </>
  )
}
