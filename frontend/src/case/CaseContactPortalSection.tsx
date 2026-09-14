import { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../api'
import { CopyButton } from '../CopyButton'
import { useDialogs } from '../DialogProvider'
import type { ContactPortalAccessCreateOut, ContactPortalAccessOut } from '../types'

type Props = {
  token: string
  caseId: string
  /** Matter must have portal enabled before granting access from this screen. */
  portalEnabled: boolean
  globalContactId: string | null
  contactName: string
  contactEmail?: string | null
}

export function CaseContactPortalSection({
  token,
  caseId,
  portalEnabled,
  globalContactId,
  contactName,
  contactEmail,
}: Props) {
  const { askConfirm } = useDialogs()
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
        <h4 style={{ margin: 0 }}>Canary Portal</h4>
        <p className="muted" style={{ margin: 0, lineHeight: 1.5 }}>
          This matter contact is not linked to a global contact card. Link or add a global contact before granting portal
          access.
        </p>
      </div>
    )
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
      let sendEmail = false
      const email = (contactEmail || '').trim()
      if (email) {
        sendEmail = await askConfirm({
          title: 'Send access e-mail?',
          message: `Send the portal access code to ${email}?`,
          confirmLabel: 'Send e-mail',
          cancelLabel: 'Skip',
        })
      }
      const out = await apiFetch<ContactPortalAccessCreateOut>(`/contacts/${globalContactId}/portal/access`, {
        token,
        method: 'POST',
        json: { send_email: sendEmail, case_id: caseId },
      })
      if (sendEmail && out.email_sent) {
        setNotice(`Access e-mail sent to ${email}.`)
      }
      await load()
    } catch (e: unknown) {
      const msg = (e as { message?: string }).message ?? ''
      if (msg.includes('409') || msg.toLowerCase().includes('already exists')) {
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
      <h4 style={{ margin: 0 }}>Canary Portal</h4>
      {err ? <div className="error">{err}</div> : null}
      {notice ? <div className="muted">{notice}</div> : null}
      {!portalEnabled ? (
        <p className="muted" style={{ margin: 0, lineHeight: 1.5 }}>
          Portal is not enabled for this matter. Turn on <strong>Enable portal</strong> in Edit details before granting
          portal access or sharing folders with {contactName}.
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
            Grant portal access
          </button>
          <p className="muted" style={{ margin: 0, fontSize: '0.9rem' }}>
            Portal login is per global contact ({contactName}). Folder sharing is managed per matter.
          </p>
        </>
      ) : (
        <div className="stack" style={{ gap: 8 }}>
          {code ? (
            <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <span className="muted">Access code</span>
              <code style={{ letterSpacing: '0.06em' }}>{code}</code>
              <CopyButton text={code} label="Copy" copiedLabel="Copied" disabled={busy} />
            </div>
          ) : (
            <div className="muted">Access is enabled. Rotate the code from the global contact card to view it here.</div>
          )}
          <p className="muted" style={{ margin: 0 }}>
            Grant folder access via right-click → Portal → Share in this matter&apos;s documents.
          </p>
        </div>
      )}
    </div>
  )
}
