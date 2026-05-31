import { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../api'
import { useDialogs } from '../DialogProvider'
import type { ContactPortalAccessCreateOut, ContactPortalAccessOut } from '../types'

type Props = {
  token: string
  globalContactId: string | null
  contactName: string
  contactEmail?: string | null
}

export function CaseContactPortalSection({ token, globalContactId, contactName, contactEmail }: Props) {
  const { askConfirm } = useDialogs()
  const [access, setAccess] = useState<ContactPortalAccessOut | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!globalContactId) {
      setAccess(null)
      return
    }
    const row = await apiFetch<ContactPortalAccessOut>(`/contacts/${globalContactId}/portal/access`, { token })
    setAccess(row)
  }, [globalContactId, token])

  useEffect(() => {
    void (async () => {
      setBusy(true)
      setErr(null)
      try {
        await load()
      } catch (e: unknown) {
        setErr((e as { message?: string }).message ?? 'Failed to load portal access')
      } finally {
        setBusy(false)
      }
    })()
  }, [load])

  if (!globalContactId) {
    return (
      <div className="stack" style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
        <h4 style={{ margin: 0 }}>Client portal</h4>
        <p className="muted" style={{ margin: 0, lineHeight: 1.5 }}>
          This matter contact is not linked to a global contact card. Link or add a global contact before granting portal
          access.
        </p>
      </div>
    )
  }

  async function grantAccess() {
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
        json: { send_email: sendEmail },
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
      <h4 style={{ margin: 0 }}>Client portal</h4>
      {err ? <div className="error">{err}</div> : null}
      {notice ? <div className="muted">{notice}</div> : null}
      {!hasAccess ? (
        <button type="button" className="btn primary" disabled={busy} onClick={() => void grantAccess()}>
          Grant portal access
        </button>
      ) : (
        <div className="stack" style={{ gap: 8 }}>
          {code ? (
            <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <span className="muted">Access code</span>
              <code style={{ letterSpacing: '0.06em' }}>{code}</code>
              <button type="button" className="btn" disabled={busy} onClick={() => void navigator.clipboard.writeText(code)}>
                Copy
              </button>
            </div>
          ) : (
            <div className="muted">Access is enabled. Rotate the code from the global contact card to view it here.</div>
          )}
          <p className="muted" style={{ margin: 0 }}>
            Grant folder access via right-click → Portal → Share in this matter&apos;s documents.
          </p>
        </div>
      )}
      {!hasAccess ? (
        <p className="muted" style={{ margin: 0, fontSize: '0.9rem' }}>
          Portal login is per global contact ({contactName}). Folder sharing is managed per matter.
        </p>
      ) : null}
    </div>
  )
}
