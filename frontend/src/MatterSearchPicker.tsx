import { useEffect, useState } from 'react'
import { fetchCaseById, fetchCaseSearch } from './apiSearch'
import { SearchInput } from './SearchInput'
import { matterPickerSummary } from './matterSearch'
import { useDebouncedValue } from './useDebouncedValue'
import type { CaseOut } from './types'

const MATTER_PICKER_LIMIT = 50

type Props = {
  token: string
  value: string
  onChange: (caseId: string) => void
  disabled?: boolean
  autoFocus?: boolean
  listMaxHeight?: number
  searchPlaceholder?: string
  idleHint?: string
  changeLabel?: string
  /** Optional matter status filter (e.g. `quote` in quote wizard). */
  status?: string
}

export function MatterSearchPicker({
  token,
  value,
  onChange,
  disabled = false,
  autoFocus = false,
  listMaxHeight = 220,
  searchPlaceholder = 'Search matters (reference, client, description, status)…',
  idleHint = 'Type to search matters (reference, client, description, status).',
  changeLabel = 'Change',
  status,
}: Props) {
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebouncedValue(search.trim(), 300)
  const [matches, setMatches] = useState<CaseOut[]>([])
  const [searchBusy, setSearchBusy] = useState(false)
  const [selectedCase, setSelectedCase] = useState<CaseOut | null>(null)

  useEffect(() => {
    if (!value || !token) {
      setSelectedCase(null)
      return
    }
    let cancelled = false
    void fetchCaseById(token, value).then((row) => {
      if (!cancelled) setSelectedCase(row)
    })
    return () => {
      cancelled = true
    }
  }, [value, token])

  useEffect(() => {
    if (!token || !debouncedSearch) {
      setMatches([])
      setSearchBusy(false)
      return
    }
    let cancelled = false
    setSearchBusy(true)
    void fetchCaseSearch(token, { q: debouncedSearch, limit: MATTER_PICKER_LIMIT, status })
      .then((rows) => {
        if (!cancelled) setMatches(rows)
      })
      .catch(() => {
        if (!cancelled) setMatches([])
      })
      .finally(() => {
        if (!cancelled) setSearchBusy(false)
      })
    return () => {
      cancelled = true
    }
  }, [token, debouncedSearch, status])

  const selectedLines = selectedCase ? matterPickerSummary(selectedCase) : null

  if (value && selectedLines) {
    return (
      <div className="calendarMatterPicker">
        <div className="calendarMatterPickerSelected">
          <div className="calendarMatterPickerSelectedText">
            <div className="calendarMatterPickerSelectedPrimary">{selectedLines.primary}</div>
            {selectedLines.secondary ? (
              <div className="calendarMatterPickerSelectedSecondary muted">{selectedLines.secondary}</div>
            ) : null}
          </div>
          <button
            type="button"
            className="btn"
            disabled={disabled}
            onClick={() => {
              setSearch('')
              onChange('')
            }}
          >
            {changeLabel}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="calendarMatterPicker">
      <SearchInput
        className="calendarMatterPickerSearch"
        placeholder={searchPlaceholder}
        value={search}
        autoFocus={autoFocus}
        disabled={disabled}
        onChange={(e) => {
          setSearch(e.target.value)
          if (value) onChange('')
        }}
        onClear={() => {
          setSearch('')
          if (value) onChange('')
        }}
        aria-label="Search matters"
        autoComplete="off"
      />
      {!search.trim() ? (
        <p className="muted calendarMatterPickerHint" style={{ margin: 0 }}>
          {idleHint}
        </p>
      ) : searchBusy ? (
        <p className="muted calendarMatterPickerHint" style={{ margin: 0 }}>
          Searching…
        </p>
      ) : matches.length === 0 ? (
        <p className="muted calendarMatterPickerHint" style={{ margin: 0 }}>
          No matters match your search.
        </p>
      ) : (
        <>
          <ul
            className="calendarMatterPickerList"
            role="listbox"
            aria-label="Matching matters"
            style={{ maxHeight: listMaxHeight }}
          >
            {matches.map((c) => {
              const lines = matterPickerSummary(c)
              return (
                <li key={c.id} role="none">
                  <button
                    type="button"
                    disabled={disabled}
                    role="option"
                    aria-selected={value === c.id}
                    onClick={() => {
                      onChange(c.id)
                      setSearch('')
                    }}
                  >
                    <span className="calendarMatterPickerRowPrimary">{lines.primary}</span>
                    {lines.secondary ? (
                      <span className="calendarMatterPickerRowSecondary muted">{lines.secondary}</span>
                    ) : null}
                  </button>
                </li>
              )
            })}
          </ul>
          {matches.length >= MATTER_PICKER_LIMIT ? (
            <p className="muted calendarMatterPickerHint" style={{ margin: 0 }}>
              Showing the first matches — refine your search if needed.
            </p>
          ) : null}
        </>
      )}
    </div>
  )
}

/** Load a single matter label when only the id is known (e.g. calendar selected row). */
export function useCaseSummary(token: string, caseId: string): ReturnType<typeof matterPickerSummary> | null {
  const [summary, setSummary] = useState<ReturnType<typeof matterPickerSummary> | null>(null)
  useEffect(() => {
    if (!caseId || !token) {
      setSummary(null)
      return
    }
    let cancelled = false
    void fetchCaseById(token, caseId).then((row) => {
      if (!cancelled) setSummary(row ? matterPickerSummary(row) : null)
    })
    return () => {
      cancelled = true
    }
  }, [caseId, token])
  return summary
}
