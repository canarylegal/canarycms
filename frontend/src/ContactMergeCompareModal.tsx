import { useEffect } from 'react'
import {
  buildContactCompareFields,
  contactMergeImpactLines,
} from './contactMergeCompare'
import type { ContactMergePreviewOut } from './types'

type Props = {
  open: boolean
  preview: ContactMergePreviewOut
  willEmail: boolean
  busy?: boolean
  onCancel: () => void
  onConfirm: () => void
}

export function ContactMergeCompareModal({
  open,
  preview,
  willEmail,
  busy,
  onCancel,
  onConfirm,
}: Props) {
  useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && !busy) onCancel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, busy, onCancel])

  if (!open) return null

  const fields = buildContactCompareFields(preview.survivor, preview.source)
  const impact = contactMergeImpactLines(preview, { willEmail })
  const confirmLabel = willEmail ? 'Merge, reset codes, and e-mail' : 'Merge and reset portal codes'

  return (
    <div
      className="modalOverlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="contactMergeCompareTitle"
    >
      <div className="modal card contactMergeCompareModal">
        <div className="paneHead">
          <div>
            <h2 id="contactMergeCompareTitle">Review merge</h2>
            <div className="muted">Compare both contacts, then confirm. This cannot be undone.</div>
          </div>
          <button type="button" className="btn" disabled={busy} onClick={onCancel}>
            Close
          </button>
        </div>

        <div className="stack modalBodyScroll contactMergeCompareBody">
          <div className="contactMergeCompareGrid" role="table" aria-label="Contact comparison">
            <div className="contactMergeCompareRow contactMergeCompareHeader" role="row">
              <div role="columnheader" className="contactMergeCompareLabel">
                Field
              </div>
              <div role="columnheader">
                Keep
                <div className="muted contactMergeCompareSub">{preview.survivor.name}</div>
              </div>
              <div role="columnheader">
                Absorb (deleted)
                <div className="muted contactMergeCompareSub">{preview.source.name}</div>
              </div>
            </div>
            {fields.map((row) => (
              <div
                key={row.key}
                className={`contactMergeCompareRow${row.mismatch ? ' contactMergeCompareRow--mismatch' : ''}`}
                role="row"
              >
                <div role="cell" className="contactMergeCompareLabel">
                  {row.label}
                </div>
                <div role="cell">{row.keep}</div>
                <div role="cell">{row.absorb}</div>
              </div>
            ))}
          </div>

          <div className="stack" style={{ gap: 6 }}>
            <h3 className="contactMergeCompareImpactTitle">What will happen</h3>
            <ul className="contactMergeCompareImpactList">
              {impact.map((line) => (
                <li key={line}>{line}</li>
              ))}
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
          </div>
        </div>

        <div className="confirmModalActions contactMergeCompareActions">
          <button type="button" className="btn confirmModalCancel" disabled={busy} onClick={onCancel}>
            Don&apos;t merge
          </button>
          <button type="button" className="btn danger" disabled={busy} onClick={onConfirm}>
            {busy ? 'Merging…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
