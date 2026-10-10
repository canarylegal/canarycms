import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from './api'
import { CopyButton } from './CopyButton'
import { useDialogs } from './DialogProvider'
import {
  choosePortalEmailConflictResolution,
  parsePortalEmailConflict,
  type PortalConflictResolution,
} from './portalEmailConflict'
import type {
  ContactPortalAccessCreateOut,
  ContactPortalAccessOut,
  ContactPortalGrantOut,
  ContactPortalNotificationPrefsOut,
} from './types'
import { PORTAL_ALERTS_NOT_CONFIGURED_MSG } from './types'

type Props = {
  token: string
  contactId: string
  contactName: string
  contactEmail?: string | null
}

export function ContactPortalPanel({ token, contactId, contactName, contactEmail }: Props) {
  const { askConfirm, askConfirmChoice, alert: showAlert } = useDialogs()
  const [access, setAccess] = useState<ContactPortalAccessOut | null>(null)
  const [grants, setGrants] = useState<ContactPortalGrantOut[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [emailNotice, setEmailNotice] = useState<string | null>(null)
  const [revealedCode, setRevealedCode] = useState<string | null>(null)

  const portalUrl = useMemo(() => {
    if (typeof window === 'undefined') return '/portal'
    return `${window.location.origin}/portal`
  }, [])

  const load = useCallback(async () => {
    setErr(null)
    const [accessRow, grantRows] = await Promise.all([
      apiFetch<ContactPortalAccessOut>(`/contacts/${contactId}/portal/access`, { token }),
      apiFetch<ContactPortalGrantOut[]>(`/contacts/${contactId}/portal/grants`, { token }),
    ])
    setAccess(accessRow)
    setGrants(grantRows)
    if (accessRow.access_code) {
      setRevealedCode(accessRow.access_code)
    } else if (!accessRow.has_access) {
      setRevealedCode(null)
    }
  }, [contactId, token])

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

  async function postAccess(
    path: 'access' | 'access/rotate',
    opts: { conflictResolution?: PortalConflictResolution } = {},
  ): Promise<ContactPortalAccessCreateOut> {
    return apiFetch<ContactPortalAccessCreateOut>(`/contacts/${contactId}/portal/${path}`, {
      token,
      method: 'POST',
      json: {
        send_email: false,
        ...(opts.conflictResolution ? { conflict_resolution: opts.conflictResolution } : {}),
      },
    })
  }

  async function sendAccessEmailForCode(opts: {
    accessCode: string
    emailContactId: string
    joinedExisting: boolean
  }): Promise<boolean> {
    const email = (contactEmail || '').trim()
    if (!email || !opts.accessCode.trim()) return false
    const send = await askConfirm({
      title: 'Send access e-mail?',
      message: opts.joinedExisting
        ? `Send the existing portal access code to ${email}?`
        : `Send the portal access code to ${email}?`,
      confirmLabel: 'Send e-mail',
      cancelLabel: 'Skip',
    })
    if (!send) return false
    try {
      await apiFetch(`/contacts/${opts.emailContactId}/portal/access/email`, {
        token,
        method: 'POST',
        json: { access_code: opts.accessCode },
      })
      return true
    } catch (e: unknown) {
      setEmailNotice((e as { message?: string }).message ?? PORTAL_ALERTS_NOT_CONFIGURED_MSG)
      return false
    }
  }

  async function enableAccess() {
    setBusy(true)
    setErr(null)
    setEmailNotice(null)
    try {
      let out: ContactPortalAccessCreateOut
      try {
        out = await postAccess('access')
      } catch (e: unknown) {
        const conflict = parsePortalEmailConflict(e)
        if (!conflict) throw e
        const resolution = await choosePortalEmailConflictResolution(askConfirmChoice, conflict)
        if (!resolution) return
        out = await postAccess('access', { conflictResolution: resolution })
      }
      setRevealedCode(out.access_code || null)
      const emailContactId =
        out.joined_existing && out.joined_contact_id ? out.joined_contact_id : contactId
      const emailed = await sendAccessEmailForCode({
        accessCode: out.access_code || '',
        emailContactId,
        joinedExisting: Boolean(out.joined_existing),
      })
      if (out.joined_existing) {
        const joinMsg = `Joined existing portal login on ${out.joined_contact_name || 'the other contact'}. That access code remains active.`
        setEmailNotice(emailed ? `${joinMsg} Access e-mail sent to ${contactEmail}.` : joinMsg)
      } else if (emailed) {
        setEmailNotice(`Access e-mail sent to ${contactEmail}.`)
      }
      await load()
    } catch (e: unknown) {
      const conflict = parsePortalEmailConflict(e)
      setErr(conflict?.message ?? (e as { message?: string }).message ?? 'Could not create portal access')
    } finally {
      setBusy(false)
    }
  }

  async function rotateCode() {
    setBusy(true)
    setErr(null)
    setEmailNotice(null)
    try {
      let out: ContactPortalAccessCreateOut
      try {
        out = await postAccess('access/rotate')
      } catch (e: unknown) {
        const conflict = parsePortalEmailConflict(e)
        if (!conflict) throw e
        const resolution = await choosePortalEmailConflictResolution(askConfirmChoice, conflict)
        if (!resolution) return
        out = await postAccess('access/rotate', { conflictResolution: resolution })
      }
      setRevealedCode(out.access_code || null)
      const emailContactId =
        out.joined_existing && out.joined_contact_id ? out.joined_contact_id : contactId
      const emailed = await sendAccessEmailForCode({
        accessCode: out.access_code || '',
        emailContactId,
        joinedExisting: Boolean(out.joined_existing),
      })
      if (out.joined_existing) {
        const joinMsg = `Joined existing portal login on ${out.joined_contact_name || 'the other contact'}. That access code remains active.`
        setEmailNotice(emailed ? `${joinMsg} Access e-mail sent to ${contactEmail}.` : joinMsg)
      } else if (emailed) {
        setEmailNotice(`Access e-mail sent to ${contactEmail}.`)
      }
      await load()
    } catch (e: unknown) {
      const conflict = parsePortalEmailConflict(e)
      setErr(conflict?.message ?? (e as { message?: string }).message ?? 'Could not rotate access code')
    } finally {
      setBusy(false)
    }
  }

  async function revokePortalAccess() {
    const ok = await askConfirm({
      title: 'Revoke portal access?',
      message: 'This removes the portal login code and revokes all folder access for this contact. They cannot sign in until access is granted again.',
      danger: true,
      confirmLabel: 'Revoke access',
    })
    if (!ok) return
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/contacts/${contactId}/portal/access`, { token, method: 'DELETE' })
      setRevealedCode(null)
      await load()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not revoke portal access')
    } finally {
      setBusy(false)
    }
  }

  async function revokeGrant(grantId: string) {
    const ok = await askConfirm({
      title: 'Revoke folder access?',
      message: 'This contact will no longer see this shared area in the portal.',
      danger: true,
      confirmLabel: 'Revoke',
    })
    if (!ok) return
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/contacts/${contactId}/portal/grants/${grantId}`, { token, method: 'DELETE' })
      await load()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not revoke access')
    } finally {
      setBusy(false)
    }
  }

  function copyInvite() {
    const code = revealedCode || access?.access_code
    if (!code) return
    const body = [
      `Dear ${contactName},`,
      '',
      'You can access your documents using Canary Portal:',
      '',
      portalUrl,
      '',
      `Access code: ${code}`,
      '',
      'Keep this code confidential. Contact us if you need a new code.',
    ].join('\n')
    void navigator.clipboard.writeText(body)
    void showAlert('Invite text copied to clipboard.', 'Copied')
  }

  async function updateNotificationPref(key: 'notify_files_added' | 'notify_folder_shared', value: boolean) {
    setBusy(true)
    setErr(null)
    try {
      const out = await apiFetch<ContactPortalNotificationPrefsOut>(`/contacts/${contactId}/portal/access/notifications`, {
        token,
        method: 'PATCH',
        json: { [key]: value },
      })
      setAccess((prev) =>
        prev
          ? {
              ...prev,
              notify_files_added: out.notify_files_added,
              notify_folder_shared: out.notify_folder_shared,
            }
          : prev,
      )
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not update notification preferences')
    } finally {
      setBusy(false)
    }
  }

  const displayCode = access?.has_access ? revealedCode || access?.access_code : null

  return (
    <div className="stack contactPortalPanel" style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--border)' }}>
      <div>
        <h3 style={{ margin: 0 }}>Client portal access</h3>
        <p className="muted" style={{ margin: '6px 0 0' }}>
          Global client login for {contactName}. One access code across all matters. Share folders from each matter
          (Documents → right-click folder → Portal → Share).
        </p>
      </div>
      {err ? <div className="error">{err}</div> : null}
      {emailNotice ? <div className="muted">{emailNotice}</div> : null}

      <div className="card" style={{ padding: 12 }}>
        <div className="muted" style={{ marginBottom: 8 }}>
          Portal URL
        </div>
        <code>{portalUrl}</code>
      </div>

      {!access?.has_access ? (
        <button type="button" className="btn primary" disabled={busy} onClick={() => void enableAccess()}>
          Enable client portal login
        </button>
      ) : (
        <div className="stack" style={{ gap: 10 }}>
          <div className="row" style={{ flexWrap: 'wrap', gap: 8 }}>
            <button type="button" className="btn" disabled={busy} onClick={() => void rotateCode()}>
              Rotate access code
            </button>
            <button type="button" className="btn" disabled={busy} onClick={() => void revokePortalAccess()}>
              Revoke portal access
            </button>
          </div>
          {access?.last_login_at ? (
            <div className="muted">Last sign-in: {new Date(access.last_login_at).toLocaleString()}</div>
          ) : null}
          {displayCode ? (
            <div className="card" style={{ padding: 12 }}>
              <div className="muted">Access code</div>
              <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap', marginTop: 8 }}>
                <code style={{ fontSize: '1.1rem', letterSpacing: '0.06em' }}>{displayCode}</code>
                <CopyButton text={displayCode} label="Copy code" copiedLabel="Copied" primary disabled={busy} />
                <button type="button" className="btn" onClick={copyInvite}>
                  Copy invite text
                </button>
              </div>
            </div>
          ) : (
            <div className="muted">Rotate the access code to generate a new code you can copy.</div>
          )}
          <div className="card stack" style={{ padding: 12, gap: 8 }}>
            <div className="muted">E-mail notifications</div>
            <label className="row" style={{ gap: 10, alignItems: 'center', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={access?.notify_files_added !== false}
                disabled={busy}
                onChange={(e) => void updateNotificationPref('notify_files_added', e.target.checked)}
              />
              <span>New files added to shared folders</span>
            </label>
            <label className="row" style={{ gap: 10, alignItems: 'center', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={access?.notify_folder_shared !== false}
                disabled={busy}
                onChange={(e) => void updateNotificationPref('notify_folder_shared', e.target.checked)}
              />
              <span>Folder shared with this contact</span>
            </label>
          </div>
        </div>
      )}

      <div>
        <h4 style={{ margin: '0 0 8px' }}>Current folder access</h4>
        {grants.length === 0 ? (
          <div className="muted">No folder grants yet. Grant access from a matter&apos;s documents.</div>
        ) : (
          <div className="list">
            {grants.map((g) => (
              <div key={g.id} className="listCard row" style={{ justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                <div>
                  <div className="listTitle">{g.label?.trim() || g.case_title}</div>
                  <div className="muted">
                    {g.case_title}
                    {g.folder_path ? ` · ${g.folder_path}` : ' · (matter root)'}
                  </div>
                </div>
                <button type="button" className="btn" disabled={busy} onClick={() => void revokeGrant(g.id)}>
                  Revoke
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
