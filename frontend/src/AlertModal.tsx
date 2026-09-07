import { useEffect } from 'react'

interface Props {
  open: boolean
  title: string
  message: string
  onClose: () => void
}

export function AlertModal({ open, title, message, onClose }: Props) {
  useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      className="modalOverlay"
      style={{ zIndex: 101 }}
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="alertModalTitle"
    >
      <div className="modal card confirmModal">
        <h2 id="alertModalTitle" className="confirmModalTitle">
          {title}
        </h2>
        <p className="confirmModalMessage">{message}</p>
        <div className="confirmModalActions">
          <button type="button" className="btn primary" onClick={onClose}>
            OK
          </button>
        </div>
      </div>
    </div>
  )
}
