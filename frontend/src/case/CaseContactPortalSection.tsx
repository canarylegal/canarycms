import { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../api'
import { CopyButton } from '../CopyButton'
import { useDialogs } from '../DialogProvider'
import {
  choosePortalEmailConflictResolution,
  parsePortalEmailConflict,
  type PortalConflictResolution,
} from '../portalEmailConflict'
import type { ContactPortalAccessCreateOut, ContactPortalAccessOut } from '../types'

type Props = {
  token: string
  caseId: string
  /** Matter must have portal enabled before granting access from this screen. */
  portalEnabled: boolean
  globalContactId: string | null
  contactName: string
  contactEmail?: string | null
  /** When join-existing relinks the matter contact to another global card. */
  onGlobalContactRelinked?: (contactId: string) => void
}

export function CaseContactPortalSection({
  token,
  caseId,
  portalEnabled,
  globalContactId,
  contactName,
  contactEmail,
  onGlobalContactRelinked,
}: Props) {
  const { askConfirm, askConfirmChoice } = useDialogs()
  const [access, setAccess] = useState<ContactPortalAccessOut | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [loadFailed, setLoadFailed] = useState(false)

  const load = useCallback(async () => {
    if (!globalContactId) {
      setAccess(null)
      setLoadFailed(false)
      return
    }
    const row = await apiFetch<ContactPortalAccessOut>(`/contacts/${globalContactId}/portal/access`, { token })
    setAccess(row)
    setLoadFailed(false)
  }, [globalContactId, token])

  const reload = useCallback(async () => {
    setBusy(true)
    setErr(null)
    try {
      await load()
    } catch (e: unknown) {
      setLoadFailed(true)
      setErr((e as { message?: string }).message ?? 'Failed to load portal access')
    } finally {
      setBusy(false)
    }
  }, [load])

  useEffect(() => {
    void reload()
  }, [reload])

  if (!globalContactId) {
    return (
      <div className="stack" style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
        <h4 style={{ margin: 0 }}>Client portal access</h4>
        <p className="muted" style={{ margin: 0, lineHeight: 1.5 }}>
          Global client login — link this matter contact to a global contact card before enabling portal access.
        </p>
      </div>
    )
  }

  async function postGrant(opts: {
    conflictResolution?: PortalConflictResolution
  }): Promise<ContactPortalAccessCreateOut> {
    return apiFetch<ContactPortalAccessCreateOut>(`/contacts/${globalContactId}/portal/access`, {
      token,
      method: 'POST',
      json: {
        send_email: false,
        case_id: caseId,
        ...(opts.conflictResolution ? { conflict_resolution: opts.conflictResolution } : {}),
      },
    })
  }

  async function sendAccessEmail(contactId: string, accessCode: string, email: string): Promise<boolean> {
    try {
      await apiFetch(`/contacts/${contactId}/portal/access/email`, {
        token,
        method: 'POST',
        json: { access_code: accessCode },
      })
      return true
    } catch (e: unknown) {
      setNotice((e as { message?: string }).message ?? `Could not send access e-mail to ${email}.`)
      return false
    }
  }

  async function grantAccess() {
    if (!portalEnabled) {
      setErr('Enable the portal on this matter (Edit details) before granting portal access.')
      return
    }
    setBusy(true)
    setErr(null)
    setNotice(null)
    try {
      // Resolve login conflicts before offering to e-mail — never mail a code that may then be revoked/joined away.
      let out: ContactPortalAccessCreateOut
      try {
        out = await postGrant({})
      } catch (e: unknown) {
        const conflict = parsePortalEmailConflict(e)
        if (!conflict) throw e
        const resolution = await choosePortalEmailConflictResolution(askConfirmChoice, conflict)
        if (!resolution) return
        out = await postGrant({ conflictResolution: resolution })
      }

      const email = (contactEmail || '').trim()
      const code = (out.access_code || '').trim()
      const emailContactId =
        out.joined_existing && out.joined_contact_id ? out.joined_contact_id : globalContactId
      let emailed = false
      if (email && code && emailContactId) {
        const sendEmail = await askConfirm({
          title: 'Send access e-mail?',
          message: out.joined_existing
            ? `Send the existing portal access code to ${email}?`
            : `Send the portal access code to ${email}?`,
          confirmLabel: 'Send e-mail',
          cancelLabel: 'Skip',
        })
        if (sendEmail) {
          emailed = await sendAccessEmail(emailContactId, code, email)
        }
      }

      if (out.joined_existing) {
        const name = out.joined_contact_name || 'the other contact'
        const joinMsg = out.matter_contact_relinked
          ? `Joined existing portal login on ${name}. This matter contact now links to that card.`
          : `Joined existing portal login on ${name}. Use that contact for portal sharing.`
        setNotice(emailed ? `${joinMsg} Access e-mail sent to ${email}.` : joinMsg)
        if (out.matter_contact_relinked && out.joined_contact_id) {
          onGlobalContactRelinked?.(out.joined_contact_id)
        }
      } else if (emailed) {
        setNotice(`Access e-mail sent to ${email}.`)
      }
      await load()
    } catch (e: unknown) {
      const msg = (e as { message?: string }).message ?? ''
      const conflict = parsePortalEmailConflict(e)
      if (conflict) {
        setErr(conflict.message)
      } else if (msg.toLowerCase().includes('already exists')) {
        await load()
      } else {
        setErr(msg || 'Could not grant portal access')
      }
    } finally {
      setBusy(false)
    }
  }

  const code = access?.access_code
  const hasAccess = access?.has_access

  return (
    <div className="stack" style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
      <h4 style={{ margin: 0 }}>Client portal access</h4>
      <p className="muted" style={{ margin: 0, lineHeight: 1.5 }}>
        Global client login for {contactName}. One access code works across all matters where folders, quotes, or forms
        are shared with them.
      </p>
      {err ? <div className="error">{err}</div> : null}
      {notice ? <div className="muted">{notice}</div> : null}
      {!portalEnabled ? (
        <p className="muted" style={{ margin: 0, lineHeight: 1.5 }}>
          Portal is not enabled for this matter. Turn on <strong>Enable portal</strong> in Edit details before enabling
          client login or sharing folders with {contactName}.
        </p>
      ) : loadFailed && !access ? (
        <>
          <p className="muted" style={{ margin: 0, lineHeight: 1.5 }}>
            Could not load portal status for {contactName}. The access code was not changed — try again.
          </p>
          <button type="button" className="btn" disabled={busy} onClick={() => void reload()}>
            {busy ? 'Loading…' : 'Retry'}
          </button>
        </>
      ) : !hasAccess ? (
        <>
          <button type="button" className="btn primary" disabled={busy} onClick={() => void grantAccess()}>
            Enable client portal login
          </button>
          <p className="muted" style={{ margin: 0, fontSize: '0.9rem' }}>
            Folder sharing is still managed per matter after login is enabled.
          </p>
        </>
      ) : (
        <div className="stack" style={{ gap: 8 }}>
          {code ? (
            <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <span className="muted">Client access code</span>
              <code style={{ letterSpacing: '0.06em' }}>{code}</code>
              <CopyButton text={code} label="Copy" copiedLabel="Copied" disabled={busy} />
            </div>
          ) : (
            <div className="muted">
              Client login is active. Rotate the code from the global contact card to view it here.
            </div>
          )}
          <p className="muted" style={{ margin: 0 }}>
            Share folders on this matter via Documents → right-click folder → Portal → Share.
          </p>
        </div>
      )}
    </div>
  )
}
