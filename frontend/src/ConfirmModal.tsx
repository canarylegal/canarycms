import { useEffect } from 'react'

interface Props {
  open: boolean
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  /** Optional third action (e.g. "Save and keep access"). */
  secondaryLabel?: string
  danger?: boolean
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
  onSecondary?: () => void
}

export function ConfirmModal({
  open,
  title,
  message,
  confirmLabel = 'OK',
  cancelLabel = 'Cancel',
  secondaryLabel,
  danger,
  busy,
  onConfirm,
  onCancel,
  onSecondary,
}: Props) {
  useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onCancel])

  if (!open) return null

  return (
    <div
      className="modalOverlay"
      style={{ zIndex: 100 }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirmModalTitle"
    >
      <div className="modal card confirmModal">
        <h2 id="confirmModalTitle" className="confirmModalTitle">
          {title}
        </h2>
        <p className="confirmModalMessage">{message}</p>
        <div className="confirmModalActions">
          <button
            type="button"
            className="btn confirmModalCancel"
            onClick={onCancel}
            disabled={busy}
          >
            {cancelLabel}
          </button>
          {secondaryLabel && onSecondary ? (
            <button type="button" className="btn" onClick={onSecondary} disabled={busy}>
              {secondaryLabel}
            </button>
          ) : null}
          <button
            type="button"
            className={`btn${danger ? ' danger' : ' primary'}`}
            onClick={onConfirm}
            disabled={busy}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
