import type { MouseEvent } from 'react'

/** Explicit alternatives to double-click and right-click, without selecting the row. */
export function RowActions({ label, onOpen, onActions }: {
  label: string
  onOpen: () => void
  onActions: (event: MouseEvent<HTMLButtonElement>) => void
}) {
  return (
    <span className="rowActions" onClick={(e) => e.stopPropagation()} onDoubleClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
      <button type="button" className="btn rowAction" aria-label={`Open ${label}`} onClick={onOpen}>Open</button>
      <button type="button" className="btn rowAction" aria-label={`Actions for ${label}`} aria-haspopup="menu" onClick={onActions}>Actions ▾</button>
    </span>
  )
}
