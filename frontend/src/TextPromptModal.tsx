import { useEffect, useState } from 'react'

type Props = {
  title: string
  hint?: string
  initial: string
  confirmLabel: string
  fieldLabel?: string
  /** HTML input type (e.g. password for re-auth prompts). */
  inputType?: 'text' | 'password'
  autoComplete?: string
  busy?: boolean
  onConfirm: (value: string) => void
  onCancel: () => void
}

/** In-app text entry instead of window.prompt (no browser URL chrome). */
export function TextPromptModal({
  title,
  hint,
  initial,
  confirmLabel,
  fieldLabel = 'Name',
  inputType = 'text',
  autoComplete,
  busy,
  onConfirm,
  onCancel,
}: Props) {
  const [val, setVal] = useState(initial)
  useEffect(() => {
    setVal(initial)
  }, [initial])

  return (
    <div
      className="modalOverlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="text-prompt-title"
      onClick={(e) => {
        if (e.target === e.currentTarget && !busy) onCancel()
      }}
    >
      <div
        className="modal card modal--scrollBody textPromptModal"
        style={{ maxWidth: 440, width: 'min(440px, 100%)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="paneHead">
          <div>
            <h2 id="text-prompt-title">{title}</h2>
            {hint ? <div className="muted">{hint}</div> : null}
          </div>
          <button type="button" className="btn" disabled={busy} onClick={onCancel}>
            Close
          </button>
        </div>
        <div className="modalBodyScroll">
          <label className="field" style={{ marginTop: 4 }}>
            <span>{fieldLabel}</span>
            <input
              className="allow-select"
              type={inputType}
              autoComplete={autoComplete}
              value={val}
              autoFocus
              disabled={busy}
              onChange={(e) => setVal(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !busy) onConfirm(val)
                if (e.key === 'Escape' && !busy) onCancel()
              }}
            />
          </label>
          <div className="row" style={{ justifyContent: 'flex-end', gap: 8 }}>
            <button type="button" className="btn" disabled={busy} onClick={onCancel}>
              Cancel
            </button>
            <button type="button" className="btn primary" disabled={busy} onClick={() => onConfirm(val)}>
              {busy ? '…' : confirmLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
