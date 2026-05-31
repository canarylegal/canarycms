import { useEffect, useId, useRef } from 'react'

export type SingleSelectOption = { value: string; label: string; hint?: string }

export function SingleSelectDropdown({
  label,
  options,
  value,
  onChange,
  open,
  onOpenChange,
  disabled,
  placeholder = '— select —',
  emptyMessage,
}: {
  label: string
  options: SingleSelectOption[]
  value: string
  onChange: (value: string) => void
  open: boolean
  onOpenChange: (open: boolean) => void
  disabled?: boolean
  placeholder?: string
  emptyMessage?: string
}) {
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const listId = useId()
  const selected = options.find((o) => o.value === value)

  useEffect(() => {
    if (!open) return
    function handleMouseDown(e: MouseEvent) {
      if (wrapRef.current?.contains(e.target as Node)) return
      onOpenChange(false)
    }
    document.addEventListener('mousedown', handleMouseDown)
    return () => document.removeEventListener('mousedown', handleMouseDown)
  }, [open, onOpenChange])

  return (
    <label className="field singleSelectDropdownField">
      <span>{label}</span>
      <div className="singleSelectDropdown" ref={wrapRef}>
        <button
          type="button"
          className="singleSelectDropdownTrigger select"
          disabled={disabled}
          aria-expanded={open}
          aria-haspopup="listbox"
          aria-controls={listId}
          onClick={() => {
            if (disabled) return
            onOpenChange(!open)
          }}
        >
          <span className="singleSelectDropdownTriggerMain">
            <span className="singleSelectDropdownTriggerLabel">{selected?.label ?? placeholder}</span>
            {selected?.hint ? <span className="singleSelectDropdownTriggerHint muted">{selected.hint}</span> : null}
          </span>
          <span className="singleSelectDropdownChevron" aria-hidden>
            ▾
          </span>
        </button>
        {open ? (
          <div
            id={listId}
            className="singleSelectDropdownMenu"
            role="listbox"
            aria-label={label}
            onMouseDown={(e) => e.stopPropagation()}
          >
            {options.length === 0 && emptyMessage ? (
              <div className="singleSelectDropdownEmpty muted">{emptyMessage}</div>
            ) : (
              options.map((opt) => {
                const active = value === opt.value
                return (
                  <button
                    key={opt.value}
                    type="button"
                    role="option"
                    aria-selected={active}
                    className={`singleSelectDropdownOption ${active ? 'active' : ''}`}
                    onClick={() => {
                      onChange(opt.value)
                      onOpenChange(false)
                    }}
                  >
                    <span className="singleSelectDropdownOptionLabel">{opt.label}</span>
                    {opt.hint ? <span className="singleSelectDropdownOptionHint muted">{opt.hint}</span> : null}
                  </button>
                )
              })
            )}
          </div>
        ) : null}
      </div>
    </label>
  )
}
