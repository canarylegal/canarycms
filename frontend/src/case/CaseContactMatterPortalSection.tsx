import { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../api'
import { CopyButton } from '../CopyButton'
import { useDialogs } from '../DialogProvider'
import type { MatterPortalAccessCreateOut, MatterPortalAccessOut } from '../types'
import { PORTAL_ALERTS_NOT_CONFIGURED_MSG } from '../types'

type Props = {
  token: string
  caseId: string
  portalEnabled: boolean
  globalContactId: string | null
  contactName: string
  contactEmail?: string | null
}

export function CaseContactMatterPortalSection({
  token,
  caseId,
  portalEnabled,
  globalContactId,
  contactName,
  contactEmail,
}: Props) {
  const { askConfirm } = useDialogs()
  const [access, setAccess] = useState<MatterPortalAccessOut | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [revealedCode, setRevealedCode] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!globalContactId) {
      setAccess(null)
      return
    }
    const row = await apiFetch<MatterPortalAccessOut>(
      `/cases/${caseId}/contacts/${globalContactId}/matter-portal/access`,
      { token },
    )
    setAccess(row)
  }, [caseId, globalContactId, token])

  useEffect(() => {
    void (async () => {
      setBusy(true)
      setErr(null)
      try {
        await load()
      } catch (e: unknown) {
        setErr((e as { message?: string }).message ?? 'Failed to load matter portal access')
      } finally {
        setBusy(false)
      }
    })()
  }, [load])

  if (!globalContactId) {
    return (
      <div className="stack" style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
        <h4 style={{ margin: 0 }}>Matter document exchange</h4>
        <p className="muted" style={{ margin: 0, lineHeight: 1.5 }}>
          Link this matter contact to a global contact card before issuing a matter access code.
        </p>
      </div>
    )
  }

  async function askSendEmail(): Promise<boolean> {
    const email = (contactEmail || '').trim()
    if (!email) return false
    return askConfirm({
      title: 'Send access e-mail?',
      message: `Send the matter access code and portal link to ${email}?`,
      confirmLabel: 'Send e-mail',
      cancelLabel: 'Skip',
    })
  }

  async function grantAccess() {
    if (!portalEnabled) {
      setErr('Enable the portal on this matter (Edit details) before granting exchange access.')
      return
    }
    setBusy(true)
    setErr(null)
    setNotice(null)
    try {
      const sendEmail = await askSendEmail()
      const out = await apiFetch<MatterPortalAccessCreateOut>(
        `/cases/${caseId}/contacts/${globalContactId}/matter-portal/access`,
        { token, method: 'POST', json: { send_email: sendEmail } },
      )
      setRevealedCode(out.access_code)
      if (sendEmail) {
        setNotice(
          out.email_sent
            ? `Access e-mail sent to ${contactEmail}.`
            : out.email_skip_reason ?? PORTAL_ALERTS_NOT_CONFIGURED_MSG,
        )
      }
      await load()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not grant matter portal access')
    } finally {
      setBusy(false)
    }
  }

  async function rotateAccess() {
    setBusy(true)
    setErr(null)
    setNotice(null)
    try {
      const sendEmail = await askSendEmail()
      const out = await apiFetch<MatterPortalAccessCreateOut>(
        `/cases/${caseId}/contacts/${globalContactId}/matter-portal/access/rotate`,
        { token, method: 'POST', json: { send_email: sendEmail } },
      )
      setRevealedCode(out.access_code)
      if (sendEmail) {
        setNotice(
          out.email_sent
            ? `New access e-mail sent to ${contactEmail}.`
            : out.email_skip_reason ?? PORTAL_ALERTS_NOT_CONFIGURED_MSG,
        )
      }
      await load()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not rotate access code')
    } finally {
      setBusy(false)
    }
  }

  async function revokeAccess() {
    const ok = await askConfirm({
      title: 'Revoke matter portal access?',
      message: `${contactName} will no longer be able to sign in to this matter’s shared folders with their access code.`,
      danger: true,
      confirmLabel: 'Revoke',
    })
    if (!ok) return
    setBusy(true)
    setErr(null)
    setNotice(null)
    try {
      await apiFetch(`/cases/${caseId}/contacts/${globalContactId}/matter-portal/access`, {
        token,
        method: 'DELETE',
      })
      setRevealedCode(null)
      await load()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not revoke access')
    } finally {
      setBusy(false)
    }
  }

  const code = revealedCode || access?.access_code || null
  const hasAccess = Boolean(access?.has_access)

  return (
    <div className="stack" style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
      <h4 style={{ margin: 0 }}>Matter document exchange</h4>
      <p className="muted" style={{ margin: 0, lineHeight: 1.5 }}>
        Issue a matter-specific access code so this contact can download shared folders on the portal. Share folders from
        Documents → right-click folder → Portal → Share.
      </p>
      {err ? <div className="error">{err}</div> : null}
      {notice ? <div className="notice">{notice}</div> : null}
      {busy && !access ? <div className="muted">Loading…</div> : null}
      {hasAccess && code ? (
        <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <code style={{ fontSize: 14 }}>{code}</code>
          <CopyButton text={code} label="Copy code" />
        </div>
      ) : null}
      <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
        {!hasAccess ? (
          <button type="button" className="btn primary" disabled={busy || !portalEnabled} onClick={() => void grantAccess()}>
            {busy ? 'Working…' : 'Enable matter portal access'}
          </button>
        ) : (
          <>
            <button type="button" className="btn" disabled={busy} onClick={() => void rotateAccess()}>
              Rotate code
            </button>
            <button type="button" className="btn" disabled={busy} onClick={() => void revokeAccess()}>
              Revoke
            </button>
          </>
        )}
      </div>
    </div>
  )
}
