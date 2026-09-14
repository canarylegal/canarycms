import { useCallback, useState } from 'react'
import { apiFetch } from './api'
import { ContactMergeCompareModal } from './ContactMergeCompareModal'
import { ContactSearchPicker } from './ContactSearchPicker'
import { CopyButton } from './CopyButton'
import { useDialogs } from './DialogProvider'
import type { ContactMergeOut, ContactMergePreviewOut, ContactOut } from './types'

type Props = {
  token: string
  survivor: ContactOut
  onMerged: (survivorId: string) => void
}

export function ContactMergePanel({ token, survivor, onMerged }: Props) {
  const { alert: showAlert } = useDialogs()
  const [sourceId, setSourceId] = useState<string | null>(null)
  const [sourceContact, setSourceContact] = useState<ContactOut | null>(null)
  const [preview, setPreview] = useState<ContactMergePreviewOut | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [newCode, setNewCode] = useState<string | null>(null)
  const [sendEmail, setSendEmail] = useState(false)
  const [compareOpen, setCompareOpen] = useState(false)

  const loadPreview = useCallback(
    async (id: string) => {
      setBusy(true)
      setErr(null)
      setPreview(null)
      setNewCode(null)
      setCompareOpen(false)
      try {
        const q = new URLSearchParams({ source_contact_id: id })
        const row = await apiFetch<ContactMergePreviewOut>(
          `/contacts/${survivor.id}/merge-preview?${q}`,
          { token },
        )
        setPreview(row)
        const hasEmail = Boolean((row.survivor.email || '').trim())
        setSendEmail(Boolean(row.will_reset_client_portal && hasEmail))
      } catch (e: unknown) {
        setErr((e as { message?: string }).message ?? 'Could not load merge preview')
      } finally {
        setBusy(false)
      }
    },
    [survivor.id, token],
  )

  function openCompare() {
    if (!sourceId || !preview) return
    setCompareOpen(true)
  }

  async function confirmMerge() {
    if (!sourceId || !preview) return
    const willEmail = sendEmail && preview.will_reset_client_portal
    setBusy(true)
    setErr(null)
    try {
      const out = await apiFetch<ContactMergeOut>(`/contacts/${survivor.id}/merge`, {
        token,
        method: 'POST',
        json: { source_contact_id: sourceId, send_email: willEmail },
      })
      setCompareOpen(false)
      setSourceId(null)
      setSourceContact(null)
      setPreview(null)
      if (out.new_client_access_code) {
        setNewCode(out.new_client_access_code)
        const emailNote = out.email_sent
          ? `\n\nThe new code was also e-mailed to ${out.survivor.email}.`
          : out.email_skip_reason
            ? `\n\nE-mail was not sent: ${out.email_skip_reason}`
            : '\n\nCopy this code now and share it with the client. Both previous codes no longer work.'
        await showAlert(
          `Contacts merged.\n\nNew Canary Portal access code for ${out.survivor.name}:\n${out.new_client_access_code}${emailNote}`,
          'Merge complete',
        )
      } else {
        setNewCode(null)
        await showAlert(`Contacts merged into ${out.survivor.name}.`, 'Merge complete')
      }
      onMerged(out.survivor.id)
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Merge failed')
      setCompareOpen(false)
    } finally {
      setBusy(false)
    }
  }

  const canEmailNewCode =
    Boolean(preview?.will_reset_client_portal) && Boolean((preview?.survivor.email || '').trim())
  const willEmail = Boolean(sendEmail && preview?.will_reset_client_portal)

  return (
    <div className="stack" style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
      <h4 style={{ margin: 0 }}>Merge duplicate contact</h4>
      <p className="muted" style={{ margin: 0, lineHeight: 1.5 }}>
        If this person was accidentally created twice, choose the duplicate below. Their matter links and portal folder
        shares move onto this contact. Any active portal access codes from either contact are revoked and replaced with a
        fresh code for this surviving contact.
      </p>
      <ContactSearchPicker
        token={token}
        value={sourceId}
        disabled={busy}
        searchPlaceholder="Search for the duplicate contact…"
        idleHint="Search for the other contact record to absorb."
        filterContact={(c) => c.id !== survivor.id}
        onChange={(id, contact) => {
          setSourceId(id)
          setSourceContact(contact ?? null)
          setPreview(null)
          setNewCode(null)
          setSendEmail(false)
          setCompareOpen(false)
          if (id) void loadPreview(id)
        }}
      />
      {err ? <div className="error">{err}</div> : null}
      {preview ? (
        <div className="stack" style={{ gap: 6, fontSize: 13, lineHeight: 1.45 }}>
          <div>
            Absorbing <strong>{preview.source.name}</strong>
            {preview.source.email ? ` (${preview.source.email})` : ''} into{' '}
            <strong>{preview.survivor.name}</strong>
            {preview.survivor.email ? ` (${preview.survivor.email})` : ''}.
          </div>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            <li>
              Matter links: {preview.source_matter_links} move onto this contact ({preview.survivor_matter_links}{' '}
              already linked)
            </li>
            <li>
              Portal folder shares: {preview.source_grants} move
              {preview.survivor_grants ? ` (${preview.survivor_grants} already present)` : ''}
            </li>
            <li>
              Client portal access:{' '}
              {preview.will_reset_client_portal
                ? 'both codes revoked → new code issued'
                : 'neither contact has active portal access'}
            </li>
            <li>
              Matter exchange portal:{' '}
              {preview.will_reset_matter_portal_cases > 0
                ? `${preview.will_reset_matter_portal_cases} case code(s) reset`
                : 'none active'}
            </li>
          </ul>
          {preview.email_mismatch ? (
            <div className="error">
              E-mail addresses differ. After merge, this contact keeps {preview.survivor.email || '(no e-mail)'}.
            </div>
          ) : null}
          {preview.type_mismatch ? (
            <div className="error">
              Contact types differ ({preview.source.type} → {preview.survivor.type}). The surviving type is kept.
            </div>
          ) : null}
          {canEmailNewCode ? (
            <label className="row" style={{ alignItems: 'center', gap: 8, marginTop: 4 }}>
              <input
                type="checkbox"
                checked={sendEmail}
                disabled={busy}
                onChange={(e) => setSendEmail(e.target.checked)}
              />
              <span>Also e-mail the new portal access code to {preview.survivor.email}</span>
            </label>
          ) : preview.will_reset_client_portal ? (
            <div className="muted">
              Surviving contact has no e-mail address, so the new access code cannot be sent automatically.
            </div>
          ) : null}
          <button type="button" className="btn danger" disabled={busy || !sourceId} onClick={openCompare}>
            Review and merge…
          </button>
        </div>
      ) : sourceContact && !busy ? (
        <div className="muted">Loading preview…</div>
      ) : null}
      {newCode ? (
        <div className="stack" style={{ gap: 6 }}>
          <div>
            <strong>New portal access code</strong> (copy now — it is also available on the portal panel after refresh):
          </div>
          <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <code style={{ fontSize: 15 }}>{newCode}</code>
            <CopyButton text={newCode} />
          </div>
        </div>
      ) : null}
      {preview ? (
        <ContactMergeCompareModal
          open={compareOpen}
          preview={preview}
          willEmail={willEmail}
          busy={busy}
          onCancel={() => setCompareOpen(false)}
          onConfirm={() => void confirmMerge()}
        />
      ) : null}
    </div>
  )
}
