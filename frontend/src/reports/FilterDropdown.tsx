import { useCallback, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { dropdownMenuClassName } from '../dropdownSizing'
import { useDismissOnOutsidePointer } from '../useDismissOnOutsidePointer'

export function FilterDropdown({
  id,
  label,
  summary,
  disabled,
  openId,
  setOpenId,
  children,
  footer,
  fitContentItemCount,
}: {
  id: string
  label: string
  summary: string
  disabled?: boolean
  openId: string | null
  setOpenId: (v: string | null) => void
  children: ReactNode
  footer?: ReactNode
  /** When the panel body is a simple list, pass its length for smart no-scroll sizing. */
  fitContentItemCount?: number
}) {
  const open = openId === id
  const wrapRef = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const [panelPos, setPanelPos] = useState<{ top: number; left: number; width: number } | null>(null)
  const close = useCallback(() => setOpenId(null), [setOpenId])

  const containsTarget = useCallback(
    (target: Node) => Boolean(wrapRef.current?.contains(target) || panelRef.current?.contains(target)),
    [],
  )

  useDismissOnOutsidePointer(open, containsTarget, close)

  const updatePanelPos = useCallback(() => {
    const el = wrapRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    setPanelPos({
      top: rect.bottom + 4,
      left: rect.left,
      width: Math.max(rect.width, 260),
    })
  }, [])

  useLayoutEffect(() => {
    if (!open) {
      setPanelPos(null)
      return
    }
    updatePanelPos()
    window.addEventListener('resize', updatePanelPos)
    window.addEventListener('scroll', updatePanelPos, true)
    return () => {
      window.removeEventListener('resize', updatePanelPos)
      window.removeEventListener('scroll', updatePanelPos, true)
    }
  }, [open, updatePanelPos])

  const panel =
    open && panelPos ? (
      <div
        ref={panelRef}
        className="reportsDdPanel reportsDdPanel--portal"
        role="dialog"
        aria-label={label}
        style={{
          position: 'fixed',
          top: panelPos.top,
          left: panelPos.left,
          width: panelPos.width,
        }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div
          className={dropdownMenuClassName(
            'reportsDdPanelBody',
            fitContentItemCount ?? Number.POSITIVE_INFINITY,
          )}
        >
          {children}
        </div>
        {footer ? <div className="reportsDdPanelFooter">{footer}</div> : null}
      </div>
    ) : null

  return (
    <div className="reportsDd" ref={wrapRef}>
      <button
        type="button"
        className="reportsDdTrigger"
        aria-expanded={open}
        aria-haspopup="dialog"
        disabled={disabled}
        onMouseDown={(e) => {
          if (disabled) return
          e.preventDefault()
          e.stopPropagation()
          setOpenId(open ? null : id)
        }}
      >
        <span className="reportsDdTriggerLabel">{label}</span>
        <span className="reportsDdTriggerSummary">{summary}</span>
      </button>
      {panel ? createPortal(panel, document.body) : null}
    </div>
  )
}
