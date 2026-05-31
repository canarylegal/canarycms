import { useEffect, useState } from 'react'
import { useModalDrag } from './useModalDrag'
import { poundsToPence } from './FeeScaleEditor'

type Props = {
  bandSetName: string
  busy?: boolean
  onConfirm: (values: { min_value_pence: number; max_value_pence: number | null; amount_pence: number }) => void
  onCancel: () => void
}

/** Styled modal for adding a property-value band row (replaces chained window.prompt). */
export function FeeScaleBandRowModal({ bandSetName, busy, onConfirm, onCancel }: Props) {
  const [minStr, setMinStr] = useState('0')
  const [maxStr, setMaxStr] = useState('')
  const [feeStr, setFeeStr] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const drag = useModalDrag(true)
  const { style: dragTitleStyle, ...dragTitleRest } = drag.handleProps

  useEffect(() => {
    setMinStr('0')
    setMaxStr('')
    setFeeStr('')
    setErr(null)
  }, [bandSetName])

  function submit() {
    const minP = poundsToPence(minStr)
    const feeP = poundsToPence(feeStr)
    if (minP == null) {
      setErr('Enter a valid minimum property value.')
      return
    }
    if (feeP == null) {
      setErr('Enter a valid fee amount.')
      return
    }
    let maxP: number | null = null
    if (maxStr.trim()) {
      maxP = poundsToPence(maxStr)
      if (maxP == null) {
        setErr('Enter a valid maximum property value, or leave it blank for no upper limit.')
        return
      }
      if (maxP < minP) {
        setErr('Maximum must be greater than or equal to minimum.')
        return
      }
    }
    setErr(null)
    onConfirm({ min_value_pence: minP, max_value_pence: maxP, amount_pence: feeP })
  }

  return (
    <div
      className="modalOverlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="fee-band-row-title"
      onClick={(e) => {
        if (e.target === e.currentTarget && !busy) onCancel()
      }}
    >
      <div
        className="modal card textPromptModal modalSurfaceDraggable"
        style={{ maxWidth: 440, width: 'min(440px, 100%)', ...drag.surfaceStyle }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2
          id="fee-band-row-title"
          className="modalDragHandle"
          {...dragTitleRest}
          style={{ ...dragTitleStyle, margin: 0, fontSize: 18 }}
        >
          Add band
        </h2>
        <p className="muted" style={{ marginTop: 8, marginBottom: 0, fontSize: 13 }}>
          Band set: <strong>{bandSetName}</strong>
        </p>
        <div className="stack" style={{ marginTop: 12, gap: 10 }}>
          <label className="field">
            <span>Minimum property value (£)</span>
            <input
              className="allow-select"
              value={minStr}
              autoFocus
              disabled={busy}
              onChange={(e) => setMinStr(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Maximum property value (£)</span>
            <input
              className="allow-select"
              value={maxStr}
              disabled={busy}
              placeholder="No upper limit"
              onChange={(e) => setMaxStr(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Fee amount (£)</span>
            <input
              className="allow-select"
              value={feeStr}
              disabled={busy}
              onChange={(e) => setFeeStr(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !busy) submit()
                if (e.key === 'Escape' && !busy) onCancel()
              }}
            />
          </label>
        </div>
        {err ? <div className="error" style={{ marginTop: 10 }}>{err}</div> : null}
        <div className="row" style={{ justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
          <button type="button" className="btn" disabled={busy} onClick={onCancel}>
            Cancel
          </button>
          <button type="button" className="btn primary" disabled={busy} onClick={submit}>
            {busy ? '…' : 'Add band'}
          </button>
        </div>
      </div>
    </div>
  )
}
