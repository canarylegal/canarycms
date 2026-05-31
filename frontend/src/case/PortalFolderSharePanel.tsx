import { useEffect, useState } from 'react'
import { apiFetch } from '../api'
import { useDialogs } from '../DialogProvider'
import type { CasePortalFolderShareContactOut, ContactPortalGrantCreateIn } from '../types'
import { decodeFolderPathForDisplay } from './folderPathCodec'

type Props = {
  token: string
  caseId: string
  folderPath: string
  onChanged: () => void
}

export function PortalFolderSharePanel({ token, caseId, folderPath, onChanged }: Props) {
  const { askConfirm } = useDialogs()
  const [rows, setRows] = useState<CasePortalFolderShareContactOut[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const folderLabel = decodeFolderPathForDisplay(folderPath) || 'Home'

  useEffect(() => {
    let cancelled = false
    void (async () => {
      setBusy(true)
      setErr(null)
      try {
        const q = new URLSearchParams({ folder_path: folderPath })
        const data = await apiFetch<CasePortalFolderShareContactOut[]>(
          `/cases/${caseId}/portal/folder-share?${q.toString()}`,
          { token },
        )
        if (!cancelled) setRows(data)
      } catch (e: unknown) {
        if (!cancelled) setErr((e as { message?: string }).message ?? 'Failed to load contacts')
      } finally {
        if (!cancelled) setBusy(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [caseId, folderPath, token])

  async function reloadRows() {
    const q = new URLSearchParams({ folder_path: folderPath })
    setRows(await apiFetch<CasePortalFolderShareContactOut[]>(`/cases/${caseId}/portal/folder-share?${q.toString()}`, { token }))
  }

  async function toggleContact(row: CasePortalFolderShareContactOut, grant: boolean) {
    if (grant) {
      let sendEmail = false
      if (await askConfirm({
        title: 'Notify contact?',
        message: `E-mail ${row.contact_name} that documents were shared (${folderLabel})?`,
        confirmLabel: 'Send e-mail',
        cancelLabel: 'Skip',
      })) {
        sendEmail = true
      }
      setBusy(true)
      setErr(null)
      try {
        const payload: ContactPortalGrantCreateIn = {
          case_id: caseId,
          folder_path: folderPath,
          label: folderLabel === 'Home' ? null : folderLabel,
          can_download: true,
          can_upload: true,
          send_email: sendEmail,
        }
        await apiFetch(`/contacts/${row.contact_id}/portal/grants`, { token, method: 'POST', json: payload })
        await reloadRows()
        onChanged()
      } catch (e: unknown) {
        setErr((e as { message?: string }).message ?? 'Could not grant access')
      } finally {
        setBusy(false)
      }
      return
    }

    if (!row.grant_id) return
    const ok = await askConfirm({
      title: 'Revoke folder access?',
      message: `${row.contact_name} will lose portal access to this folder.`,
      danger: true,
      confirmLabel: 'Revoke',
    })
    if (!ok) return
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/contacts/${row.contact_id}/portal/grants/${row.grant_id}`, { token, method: 'DELETE' })
      await reloadRows()
      onChanged()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not revoke access')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card caseDocEditEmbed stack" style={{ gap: 12 }}>
      <div>
        <h3 style={{ margin: '0 0 6px' }}>Share folder via portal</h3>
        <p className="muted" style={{ margin: 0 }}>
          Grant or revoke portal access to <strong>{folderLabel}</strong> for contacts on this matter who already have
          portal login.
        </p>
      </div>
      {err ? <div className="error">{err}</div> : null}
      {busy && rows.length === 0 ? <div className="muted">Loading contacts…</div> : null}
      {!busy && rows.length === 0 ? (
        <div className="muted">No matter contacts with portal access. Grant portal access from the contact card first.</div>
      ) : (
        <div className="stack" style={{ gap: 8 }}>
          {rows.map((row) => (
            <label key={row.contact_id} className="row" style={{ gap: 10, alignItems: 'center', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={row.has_grant}
                disabled={busy}
                onChange={(e) => void toggleContact(row, e.target.checked)}
              />
              <span>{row.contact_name}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  )
}
