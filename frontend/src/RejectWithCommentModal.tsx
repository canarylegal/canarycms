import { useEffect, useState } from 'react'
import { useModalDrag } from './useModalDrag'

interface Props {
  open: boolean
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  commentLabel?: string
  commentPlaceholder?: string
  showComment?: boolean
  danger?: boolean
  busy?: boolean
  onConfirm: (comment: string) => void
  onCancel: () => void
}

export function RejectWithCommentModal({
  open,
  title,
  message,
  confirmLabel = 'Reject',
  cancelLabel = 'Cancel',
  commentLabel = 'Comment for the person who submitted this (optional)',
  commentPlaceholder = 'Reason or note…',
  showComment = true,
  danger,
  busy,
  onConfirm,
  onCancel,
}: Props) {
  const drag = useModalDrag(open)
  const [comment, setComment] = useState('')

  useEffect(() => {
    if (!open) return
    setComment('')
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onCancel])

  if (!open) return null

  const { style: dragTitleStyle, ...dragTitleRest } = drag.handleProps

  return (
    <div
      className="modalOverlay"
      style={{ zIndex: 100 }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="rejectCommentModalTitle"
    >
      <div className="modal card modalSurfaceDraggable" style={{ maxWidth: 460, padding: 20, ...drag.surfaceStyle }}>
        <h2
          id="rejectCommentModalTitle"
          className="modalDragHandle"
          {...dragTitleRest}
          style={{ ...dragTitleStyle, margin: '0 0 12px', fontSize: 18 }}
        >
          {title}
        </h2>
        <p style={{ margin: '0 0 16px', lineHeight: 1.45, whiteSpace: 'pre-wrap' }}>{message}</p>
        {showComment ? (
          <label className="field" style={{ marginBottom: 16 }}>
            <span>{commentLabel}</span>
            <textarea
              rows={3}
              value={comment}
              disabled={busy}
              placeholder={commentPlaceholder}
              onChange={(e) => setComment(e.target.value)}
              style={{ width: '100%', resize: 'vertical' }}
            />
          </label>
        ) : null}
        <div className="row" style={{ justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" className="btn" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </button>
          <button
            type="button"
            className={`btn${danger ? ' danger' : ' primary'}`}
            onClick={() => onConfirm(comment.trim())}
            disabled={busy}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
