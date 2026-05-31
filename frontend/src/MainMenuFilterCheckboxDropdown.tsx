import { useEffect, useId, useRef } from 'react'

export type MainMenuFilterOption = { value: string; label: string }

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
  const listId = useId()

  useEffect(() => {
    if (!open) return
    function handleMouseDown(e: MouseEvent) {
      if (wrapRef.current?.contains(e.target as Node)) return
      onOpenChange(false)
    }
    document.addEventListener('mousedown', handleMouseDown)
    return () => document.removeEventListener('mousedown', handleMouseDown)
  }, [open, onOpenChange])

  function toggle(value: string) {
    onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value])
  }

  function clearSelection() {
    onOpenChange(false)
    onChange([])
  }

  const hasSelection = selected.length > 0

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
            onClick={() => onOpenChange(!open)}
          >
            <span className="mainMenuFilterSelectTriggerLabel">{selectionSummary(selected, options)}</span>
            <span className="mainMenuFilterSelectChevron" aria-hidden>
              ▾
            </span>
          </button>
          {open ? (
            <div
              id={listId}
              className="mainMenuFilterSelectMenu"
              role="listbox"
              aria-label={label}
              aria-multiselectable="true"
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
          ) : null}
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
