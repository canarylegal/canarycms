import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../api'
import { SearchInput } from '../SearchInput'
import { SendQuoteViaPortalModal } from '../SendQuoteViaPortalModal'
import { SendPortalFormModal } from '../SendPortalFormModal'
import { SingleSelectDropdown } from '../SingleSelectDropdown'
import { CaseFileSelectDropdown } from './CaseFileSelectDropdown'
import { DocMimeIcon } from './DocCells'
import type {
  CasePortalActivityOut,
  CasePortalNotificationSettingsOut,
  CasePortalPreviewContactOut,
  CasePortalPreviewOut,
  CasePortalStaffUserOut,
  FileSummary,
  PortalFormSubmissionOut,
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

export function CasePortalPanel({ token, caseId, onFilesChanged }: Props) {
  const [activity, setActivity] = useState<CasePortalActivityOut[]>([])
  const [previewContacts, setPreviewContacts] = useState<CasePortalPreviewContactOut[]>([])
  const [previewContactId, setPreviewContactId] = useState('')
  const [previewBusy, setPreviewBusy] = useState(false)
  const [selectedStaff, setSelectedStaff] = useState<CasePortalStaffUserOut[]>([])
  const [staffSearch, setStaffSearch] = useState('')
  const [staffSearchResults, setStaffSearchResults] = useState<UserSummary[]>([])
  const [staffSearchBusy, setStaffSearchBusy] = useState(false)
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
  const [formSendOpen, setFormSendOpen] = useState(false)
  const [formVoidBusyId, setFormVoidBusyId] = useState<string | null>(null)

  const previewContactOptions = useMemo(
    () =>
      previewContacts.map((row) => ({
        value: row.contact_id,
        label: `${row.contact_name}${
          row.shared_folder_count === 1
            ? ' · 1 shared folder'
            : ` · ${row.shared_folder_count} shared folders`
        }`,
      })),
    [previewContacts],
  )

  const portalUrl = useMemo(() => {
    if (typeof window === 'undefined') return '/portal'
    return `${window.location.origin}/portal`
  }, [])

  const staffUserIds = useMemo(() => selectedStaff.map((u) => u.id), [selectedStaff])
  const selectedIdSet = useMemo(() => new Set(staffUserIds), [staffUserIds])

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

  const load = useCallback(async () => {
    setErr(null)
    const [activityRows, settings, previewRows] = await Promise.all([
      apiFetch<CasePortalActivityOut[]>(`/cases/${caseId}/portal/activity`, { token }),
      apiFetch<CasePortalNotificationSettingsOut>(`/cases/${caseId}/portal/notification-settings`, { token }),
      apiFetch<CasePortalPreviewContactOut[]>(`/cases/${caseId}/portal/preview-contacts`, { token }),
    ])
    setActivity(activityRows)
    setSelectedStaff(settings.staff_users ?? [])
    setPreviewContacts(previewRows)
    await loadFormSubmissions()
    setPreviewContactId((current) => {
      if (current && previewRows.some((row) => row.contact_id === current)) return current
      return previewRows[0]?.contact_id ?? ''
    })
    await loadFiles()
  }, [caseId, token, loadFiles, loadFormSubmissions])

  async function voidFormSubmission(submissionId: string) {
    if (!window.confirm('Void this pending form? The client will no longer be able to submit it.')) return
    setFormVoidBusyId(submissionId)
    setErr(null)
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
      setFormVoidBusyId(null)
    }
  }

  function formStatusLabel(status: string): string {
    if (status === 'pending') return 'Awaiting client'
    if (status === 'completed') return 'Completed'
    if (status === 'voided') return 'Voided'
    if (status === 'superseded') return 'Superseded'
    return status
  }

  useEffect(() => {
    void (async () => {
      setBusy(true)
      try {
        await load()
      } catch (e: unknown) {
        setErr((e as { message?: string }).message ?? 'Failed to load portal settings')
      } finally {
        setBusy(false)
      }
    })()
  }, [load])

  useEffect(() => {
    const q = staffSearch.trim()
    if (q.length < 2) {
      setStaffSearchResults([])
      return
    }
    let cancelled = false
    const timer = window.setTimeout(() => {
      void (async () => {
        setStaffSearchBusy(true)
        try {
          const rows = await apiFetch<UserSummary[]>(`/users/search?q=${encodeURIComponent(q)}&limit=20`, { token })
          if (!cancelled) setStaffSearchResults(rows)
        } catch {
          if (!cancelled) setStaffSearchResults([])
        } finally {
          if (!cancelled) setStaffSearchBusy(false)
        }
      })()
    }, 250)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [staffSearch, token])

  function addStaffUser(u: UserSummary) {
    if (!u.is_active || selectedIdSet.has(u.id)) return
    setSelectedStaff((prev) => [
      ...prev,
      { id: u.id, display_name: u.display_name, email: u.email },
    ])
    setStaffSearch('')
    setStaffSearchResults([])
  }

  function removeStaffUser(userId: string) {
    setSelectedStaff((prev) => prev.filter((u) => u.id !== userId))
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

  const visibleSearchResults = staffSearchResults.filter((u) => u.is_active && !selectedIdSet.has(u.id))

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
          Open the portal as a contact on this matter — no access code needed. Only contacts with portal login and at
          least one shared folder on this matter are listed.
        </p>
        {busy && previewContacts.length === 0 ? <div className="muted">Loading contacts…</div> : null}
        {!busy && previewContacts.length === 0 ? (
          <div className="muted">
            No previewable contacts yet. Grant portal access on the contact card and share a folder from Documents.
          </div>
        ) : null}
        {previewContacts.length > 0 ? (
          <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <div style={{ flex: '1 1 220px', minWidth: 0 }}>
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
              className="btn primary"
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
          Sending via portal also marks the document automatically. Saving a marked quote as PDF moves the mark to the
          PDF and clears it from the source document.
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
          <div className="row" style={{ gap: 6 }}>
            <button type="button" className="btn" disabled={busy} onClick={() => void loadFormSubmissions()}>
              Refresh
            </button>
            <button type="button" className="btn primary" disabled={busy} onClick={() => setFormSendOpen(true)}>
              Send form
            </button>
          </div>
        </div>
        <p className="muted" style={{ margin: 0 }}>
          Send precedent-based information-gathering forms to portal contacts. Submissions are saved to matter history
          and documents when the client completes the form.
        </p>
        {formSubmissions.length === 0 ? (
          <div className="muted">No portal forms sent on this matter yet.</div>
        ) : (
          <div className="table">
            <div className="tr th" style={{ gridTemplateColumns: '1fr 140px 120px 100px' }}>
              <div className="thCell">Form</div>
              <div className="thCell">Contact</div>
              <div className="thCell">Status</div>
              <div className="thCell">Actions</div>
            </div>
            {formSubmissions.map((row) => (
              <div key={row.id} className="tr" style={{ gridTemplateColumns: '1fr 140px 120px 100px' }}>
                <div className="td">
                  <div>{row.template_name}</div>
                  <div className="muted" style={{ fontSize: 12 }}>{formatWhen(row.sent_at)}</div>
                </div>
                <div className="td">{row.contact_name}</div>
                <div className="td muted">{formStatusLabel(row.status)}</div>
                <div className="td">
                  {row.status === 'pending' ? (
                    <button
                      type="button"
                      className="btn"
                      disabled={formVoidBusyId === row.id}
                      onClick={() => void voidFormSubmission(row.id)}
                    >
                      {formVoidBusyId === row.id ? 'Voiding…' : 'Void'}
                    </button>
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

      {err ? <div className="error">{err}</div> : null}
      {notice ? <div className="notice">{notice}</div> : null}

      <section className="stack" style={{ gap: 8 }}>
        <h4 style={{ margin: 0 }}>Staff e-mail notifications</h4>
        <p className="muted" style={{ margin: 0 }}>
          When a client uploads via the portal, these staff members receive an e-mail. If none are selected, the fee
          earner is notified.
        </p>

        {selectedStaff.length > 0 ? (
          <div className="portalStaffChipRow">
            {selectedStaff.map((u) => (
              <span key={u.id} className="portalStaffChip">
                <span>{staffUserLabel(u)}</span>
                <button
                  type="button"
                  className="portalStaffChipRemove"
                  aria-label={`Remove ${staffUserLabel(u)}`}
                  disabled={saving}
                  onClick={() => removeStaffUser(u.id)}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        ) : (
          <div className="muted">No staff recipients selected (fee earner will be notified).</div>
        )}

        <SearchInput
          placeholder="Search staff by name or e-mail…"
          value={staffSearch}
          onChange={(e) => setStaffSearch(e.target.value)}
          onClear={() => {
            setStaffSearch('')
            setStaffSearchResults([])
          }}
          disabled={saving || busy}
          aria-label="Search staff to notify"
        />
        {staffSearch.trim().length > 0 && staffSearch.trim().length < 2 ? (
          <div className="muted">Type at least 2 characters to search.</div>
        ) : null}
        {staffSearchBusy ? <div className="muted">Searching…</div> : null}
        {!staffSearchBusy && staffSearch.trim().length >= 2 && visibleSearchResults.length === 0 ? (
          <div className="muted">No matching staff.</div>
        ) : null}
        {visibleSearchResults.length > 0 ? (
          <div className="portalStaffSearchResults stack" style={{ gap: 4 }}>
            {visibleSearchResults.map((u) => (
              <button
                key={u.id}
                type="button"
                className="portalStaffSearchHit rowbtn"
                disabled={saving}
                onClick={() => addStaffUser(u)}
              >
                <span>{staffUserLabel(u)}</span>
              </button>
            ))}
          </div>
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
    {formSendOpen ? (
      <SendPortalFormModal
        token={token}
        caseId={caseId}
        open
        onClose={() => setFormSendOpen(false)}
        onSent={() => {
          void loadFormSubmissions()
          void load()
        }}
      />
    ) : null}
    </>
  )
}
