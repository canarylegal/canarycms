import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { fetchContactSearch } from './apiSearch'
import { scrollPanelClassName } from './dropdownSizing'
import { SearchInput } from './SearchInput'
import { useDebouncedValue } from './useDebouncedValue'
import type { ContactOut } from './types'

const CONTACT_SEARCH_LIMIT = 25

type Props = {
  token: string
  value: string | null
  onChange: (contactId: string | null, contact?: ContactOut) => void
  disabled?: boolean
  organisationOnly?: boolean
  searchPlaceholder?: string
  idleHint?: string
  listMaxHeight?: number
  /** Extra filter applied client-side after server results (e.g. exclude ids). */
  filterContact?: (c: ContactOut) => boolean
  renderActions?: (contact: ContactOut) => ReactNode
}

export function ContactSearchPicker({
  token,
  value,
  onChange,
  disabled = false,
  organisationOnly = false,
  searchPlaceholder = 'Search global contacts…',
  idleHint = 'Type in the search box to find global contacts.',
  listMaxHeight,
  filterContact,
  renderActions,
}: Props) {
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebouncedValue(search.trim(), 300)
  const [rawMatches, setRawMatches] = useState<ContactOut[]>([])
  const [busy, setBusy] = useState(false)

  const matches = useMemo(
    () => (filterContact ? rawMatches.filter(filterContact) : rawMatches),
    [rawMatches, filterContact],
  )

  useEffect(() => {
    if (!token || !debouncedSearch) {
      setRawMatches([])
      setBusy(false)
      return
    }
    let cancelled = false
    setBusy(true)
    void fetchContactSearch(token, {
      q: debouncedSearch,
      limit: CONTACT_SEARCH_LIMIT,
      type: organisationOnly ? 'organisation' : undefined,
    })
      .then((rows) => {
        if (!cancelled) setRawMatches(rows)
      })
      .catch(() => {
        if (!cancelled) setRawMatches([])
      })
      .finally(() => {
        if (!cancelled) setBusy(false)
      })
    return () => {
      cancelled = true
    }
  }, [token, debouncedSearch, organisationOnly])

  return (
    <div className="stack" style={{ gap: 8 }}>
      <SearchInput
        placeholder={searchPlaceholder}
        value={search}
        disabled={disabled}
        onChange={(e) => {
          const next = e.target.value
          setSearch(next)
          if (!next.trim() && value) onChange(null)
        }}
        onClear={() => {
          setSearch('')
          if (value) onChange(null)
        }}
        aria-label="Search global contacts"
      />
      <div
        className={scrollPanelClassName(
          'list scrollPanel',
          search.trim() && !busy && matches.length > 0 ? matches.length : 0,
        )}
        style={listMaxHeight != null ? { maxHeight: listMaxHeight } : undefined}
      >
        {!search.trim() ? (
          <div className="muted">{idleHint}</div>
        ) : busy ? (
          <div className="muted">Searching…</div>
        ) : matches.length === 0 ? (
          <div className="muted">No global contacts match your search.</div>
        ) : (
          matches.map((c) => (
            <div key={c.id} className="listCard row" style={{ justifyContent: 'space-between' }}>
              <div>
                <div className="listTitle">
                  {c.name} <span className="muted">· {c.type}</span>
                </div>
                <div className="muted">{c.email ?? c.phone ?? '—'}</div>
              </div>
              <div className="row" style={{ gap: 6, alignItems: 'center', flexShrink: 0 }}>
                {renderActions?.(c)}
                <button
                  type="button"
                  className={`btn ${value === c.id ? 'primary' : ''}`}
                  disabled={disabled}
                  onClick={() => onChange(c.id, c)}
                >
                  {value === c.id ? 'Selected' : 'Select'}
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
