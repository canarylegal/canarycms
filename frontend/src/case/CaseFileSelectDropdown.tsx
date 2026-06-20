import { useCallback, useId, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { SearchInput } from '../SearchInput'
import { dropdownMenuClassName } from '../dropdownSizing'
import { useDismissOnOutsidePointer } from '../useDismissOnOutsidePointer'
import type { FileSummary } from '../types'
import { quotePortalDeliveryHint } from '../quotePortalFile'
import { DocMimeIcon } from './DocCells'

type MenuPos = { top: number; left: number; width: number }

function fileSearchHaystack(f: FileSummary): string {
  return `${f.original_filename} ${f.folder_path ?? ''}`.toLowerCase()
}

function fileOptionHint(f: FileSummary): string | undefined {
  const folder = f.folder_path?.trim()
  const portalHint = f.quote_portal_delivery
    ? quotePortalDeliveryHint(f.quote_portal_delivery)
    : f.is_portal_quote
      ? 'Quotable'
      : undefined
  if (folder && portalHint) return `${folder} · ${portalHint}`
  if (folder) return folder
  return portalHint
}

export function CaseFileSelectDropdown({
  label,
  files,
  value,
  onChange,
  disabled,
  placeholder = 'Select document…',
  emptyMessage = 'No matching documents.',
}: {
  label: string
  files: FileSummary[]
  value: string
  onChange: (fileId: string) => void
  disabled?: boolean
  placeholder?: string
  emptyMessage?: string
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [menuPos, setMenuPos] = useState<MenuPos | null>(null)
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const menuRef = useRef<HTMLDivElement | null>(null)
  const listId = useId()

  const selected = useMemo(() => files.find((f) => f.id === value) ?? null, [files, value])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    const rows = q ? files.filter((f) => fileSearchHaystack(f).includes(q)) : files
    return [...rows].sort((a, b) =>
      a.original_filename.localeCompare(b.original_filename, undefined, { sensitivity: 'base' }),
    )
  }, [files, search])

  const close = useCallback(() => {
    setOpen(false)
    setSearch('')
  }, [])

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
  }, [open, updateMenuPos, filtered.length])

  const menu =
    open && menuPos ? (
      <div
        ref={menuRef}
        id={listId}
        className={dropdownMenuClassName(
          'caseFileSelectMenu singleSelectDropdownMenu singleSelectDropdownMenu--portal',
          filtered.length,
        )}
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
        <div className="caseFileSelectSearch">
          <SearchInput
            autoFocus
            placeholder="Search documents…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onClear={() => setSearch('')}
            disabled={disabled}
            aria-label={`Search ${label.toLowerCase()}`}
          />
        </div>
        <div className="caseFileSelectList">
          {filtered.length === 0 ? (
            <div className="singleSelectDropdownEmpty muted">{emptyMessage}</div>
          ) : (
            filtered.map((f) => {
              const active = value === f.id
              const hint = fileOptionHint(f)
              return (
                <button
                  key={f.id}
                  type="button"
                  role="option"
                  aria-selected={active}
                  className={`caseFileSelectOption singleSelectDropdownOption ${active ? 'active' : ''}`}
                  onClick={() => {
                    onChange(f.id)
                    close()
                  }}
                >
                  <span className="caseFileSelectOptionIcon" aria-hidden>
                    <DocMimeIcon mime={f.mime_type} filename={f.original_filename} />
                  </span>
                  <span className="caseFileSelectOptionBody">
                    <span className="singleSelectDropdownOptionLabel">{f.original_filename}</span>
                    {hint ? <span className="singleSelectDropdownOptionHint muted">{hint}</span> : null}
                  </span>
                </button>
              )
            })
          )}
        </div>
      </div>
    ) : null

  const selectedHint = selected ? fileOptionHint(selected) : undefined

  return (
    <div className="field caseFileSelectField">
      <span>{label}</span>
      <div className="singleSelectDropdown caseFileSelect" ref={wrapRef}>
        <button
          type="button"
          className="singleSelectDropdownTrigger caseFileSelectTrigger"
          disabled={disabled}
          aria-expanded={open}
          aria-haspopup="listbox"
          aria-controls={listId}
          onMouseDown={(e) => {
            if (disabled) return
            e.preventDefault()
            e.stopPropagation()
            setOpen((prev) => !prev)
          }}
        >
          {selected ? (
            <span className="caseFileSelectTriggerIcon" aria-hidden>
              <DocMimeIcon mime={selected.mime_type} filename={selected.original_filename} />
            </span>
          ) : null}
          <span className="singleSelectDropdownTriggerMain">
            <span className="singleSelectDropdownTriggerLabel">{selected?.original_filename ?? placeholder}</span>
            {selectedHint ? <span className="singleSelectDropdownTriggerHint muted">{selectedHint}</span> : null}
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
