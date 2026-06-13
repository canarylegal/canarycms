import { useCallback, useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useDismissOnOutsidePointer } from './useDismissOnOutsidePointer'

export type MainMenuFilterOption = { value: string; label: string }

type MenuPos = { top: number; left: number; width: number }

function selectionSummary(selected: string[], options: MainMenuFilterOption[], emptyLabel = 'All'): string {
  if (selected.length === 0) return emptyLabel
  if (selected.length === 1) {
    return options.find((o) => o.value === selected[0])?.label ?? selected[0]!
  }
  return `${selected.length} selected`
}

export function MainMenuFilterCheckboxDropdown({
  label,
  options,
  selected,
  onChange,
  open,
  onOpenChange,
}: {
  label: string
  options: MainMenuFilterOption[]
  selected: string[]
  onChange: (next: string[]) => void
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const menuRef = useRef<HTMLDivElement | null>(null)
  const listId = useId()
  const [menuPos, setMenuPos] = useState<MenuPos | null>(null)
  const close = useCallback(() => onOpenChange(false), [onOpenChange])

  const containsTarget = useCallback(
    (target: Node) => Boolean(wrapRef.current?.contains(target) || menuRef.current?.contains(target)),
    [],
  )

  useDismissOnOutsidePointer(open, containsTarget, close)

  const updateMenuPos = useCallback(() => {
    const el = wrapRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    setMenuPos({
      top: rect.bottom + 4,
      left: rect.left,
      width: rect.width,
    })
  }, [])

  useLayoutEffect(() => {
    if (!open) {
      setMenuPos(null)
      return
    }
    updateMenuPos()
    window.addEventListener('resize', updateMenuPos)
    window.addEventListener('scroll', updateMenuPos, true)
    return () => {
      window.removeEventListener('resize', updateMenuPos)
      window.removeEventListener('scroll', updateMenuPos, true)
    }
  }, [open, updateMenuPos, options.length])

  function toggle(value: string) {
    onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value])
  }

  function clearSelection() {
    onOpenChange(false)
    onChange([])
  }

  const hasSelection = selected.length > 0

  const menu =
    open && menuPos ? (
      <div
        ref={menuRef}
        id={listId}
        className="mainMenuFilterSelectMenu mainMenuFilterSelectMenu--portal"
        role="listbox"
        aria-label={label}
        aria-multiselectable="true"
        style={{
          position: 'fixed',
          top: menuPos.top,
          left: menuPos.left,
          width: menuPos.width,
        }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        {options.map((opt) => {
          const checked = selected.includes(opt.value)
          return (
            <label key={opt.value} className="mainMenuFilterCheckRow" role="option" aria-selected={checked}>
              <input type="checkbox" checked={checked} onChange={() => toggle(opt.value)} />
              <span>{opt.label}</span>
            </label>
          )
        })}
      </div>
    ) : null

  return (
    <label className="field mainMenuFilterField">
      <span>{label}</span>
      <div className="mainMenuFilterSelectRow">
        <div className="mainMenuFilterSelectWrap" ref={wrapRef}>
          <button
            type="button"
            className="mainMenuFilterSelectTrigger"
            aria-expanded={open}
            aria-haspopup="listbox"
            aria-controls={listId}
            onMouseDown={(e) => {
              e.preventDefault()
              e.stopPropagation()
              onOpenChange(!open)
            }}
          >
            <span className="mainMenuFilterSelectTriggerLabel">{selectionSummary(selected, options)}</span>
            <span className="mainMenuFilterSelectChevron" aria-hidden>
              ▾
            </span>
          </button>
          {menu ? createPortal(menu, document.body) : null}
        </div>
        {hasSelection ? (
          <button
            type="button"
            className="mainMenuFilterClearBtn"
            aria-label={`Clear ${label} filter`}
            onClick={clearSelection}
          >
            ×
          </button>
        ) : null}
      </div>
    </label>
  )
}
