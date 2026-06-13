import { useCallback, useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useDismissOnOutsidePointer } from './useDismissOnOutsidePointer'

export type SingleSelectOption = { value: string; label: string; hint?: string }

type MenuPos = { top: number; left: number; width: number }

export function SingleSelectDropdown({
  label,
  options,
  value,
  onChange,
  open: openControlled,
  onOpenChange: onOpenChangeControlled,
  disabled,
  placeholder = '— select —',
  emptyMessage,
  hideLabel,
}: {
  label: string
  options: SingleSelectOption[]
  value: string
  onChange: (value: string) => void
  /** Omit for self-managed open state (typical for settings/forms). */
  open?: boolean
  onOpenChange?: (open: boolean) => void
  disabled?: boolean
  placeholder?: string
  emptyMessage?: string
  /** Omit visible label (e.g. compact time rows); label is still used for aria. */
  hideLabel?: boolean
}) {
  const [openInternal, setOpenInternal] = useState(false)
  const isControlled = openControlled !== undefined
  const open = isControlled ? openControlled : openInternal

  const setOpen = useCallback(
    (next: boolean) => {
      if (!isControlled) setOpenInternal(next)
      onOpenChangeControlled?.(next)
    },
    [isControlled, onOpenChangeControlled],
  )

  const wrapRef = useRef<HTMLDivElement | null>(null)
  const menuRef = useRef<HTMLDivElement | null>(null)
  const listId = useId()
  const selected = options.find((o) => o.value === value)
  const [menuPos, setMenuPos] = useState<MenuPos | null>(null)

  const close = useCallback(() => setOpen(false), [setOpen])

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

  const wrapClass = hideLabel ? 'singleSelectDropdownField' : 'field singleSelectDropdownField'

  const menu =
    open && menuPos ? (
      <div
        ref={menuRef}
        id={listId}
        className="singleSelectDropdownMenu singleSelectDropdownMenu--portal"
        role="listbox"
        aria-label={label}
        style={{
          position: 'fixed',
          top: menuPos.top,
          left: menuPos.left,
          width: menuPos.width,
        }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        {options.length === 0 && emptyMessage ? (
          <div className="singleSelectDropdownEmpty muted">{emptyMessage}</div>
        ) : (
          options.map((opt) => {
            const active = value === opt.value
            return (
              <button
                key={opt.value || `__empty_${opt.label}`}
                type="button"
                role="option"
                aria-selected={active}
                className={`singleSelectDropdownOption ${active ? 'active' : ''}`}
                onClick={() => {
                  onChange(opt.value)
                  setOpen(false)
                }}
              >
                <span className="singleSelectDropdownOptionLabel">{opt.label}</span>
                {opt.hint ? <span className="singleSelectDropdownOptionHint muted">{opt.hint}</span> : null}
              </button>
            )
          })
        )}
      </div>
    ) : null

  return (
    <div className={wrapClass}>
      {hideLabel ? null : <span>{label}</span>}
      <div className="singleSelectDropdown" ref={wrapRef}>
        <button
          type="button"
          className="singleSelectDropdownTrigger"
          disabled={disabled}
          aria-label={hideLabel ? label : undefined}
          aria-expanded={open}
          aria-haspopup="listbox"
          aria-controls={listId}
          onMouseDown={(e) => {
            if (disabled) return
            e.preventDefault()
            e.stopPropagation()
            setOpen(!open)
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
        {menu ? createPortal(menu, document.body) : null}
      </div>
    </div>
  )
}
