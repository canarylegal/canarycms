import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../api'
import { SearchInput } from '../SearchInput'
import { SingleSelectDropdown } from '../SingleSelectDropdown'
import type {
  CasePortalActivityOut,
  CasePortalNotificationSettingsOut,
  CasePortalPreviewContactOut,
  CasePortalPreviewOut,
  CasePortalStaffUserOut,
  UserSummary,
} from '../types'

type Props = {
  token: string
  caseId: string
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

export function CasePortalPanel({ token, caseId }: Props) {
  const [activity, setActivity] = useState<CasePortalActivityOut[]>([])
  const [previewContacts, setPreviewContacts] = useState<CasePortalPreviewContactOut[]>([])
  const [previewContactId, setPreviewContactId] = useState('')
  const [previewBusy, setPreviewBusy] = useState(false)
  const [selectedStaff, setSelectedStaff] = useState<CasePortalStaffUserOut[]>([])
  const [staffSearch, setStaffSearch] = useState('')
  const [staffSearchResults, setStaffSearchResults] = useState<UserSummary[]>([])
  const [staffSearchBusy, setStaffSearchBusy] = useState(false)
  const [busy, setBusy] = useState(false)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [previewContactOpen, setPreviewContactOpen] = useState(false)

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
    setPreviewContactId((current) => {
      if (current && previewRows.some((row) => row.contact_id === current)) return current
      return previewRows[0]?.contact_id ?? ''
    })
  }, [caseId, token])

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
  )
}
