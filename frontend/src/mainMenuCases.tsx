import { memo, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { MainMenuFilterCheckboxDropdown } from './MainMenuFilterCheckboxDropdown'
import { SearchInput } from './SearchInput'
import { buildCaseContextMenuActions, scrollCaseRowIntoView, type CaseContextMenuActionKind } from './caseListKeyboard'
import type { CaseOpenDocPanel } from './case/CaseDetail'
import { isEditableKeyboardTarget, isModalBlockingKeyboard } from './keyboardUtils'
import { caseHasRevokedUserAccess, formatCaseStatusLabel } from './types'
import type { CaseOut, UserSummary } from './types'
import { type MainMenuCaseStatusFilter } from './userUiPreferences'

export function matterTypeLabel(c: CaseOut): string {
  const parts = [c.matter_head_type_name, c.matter_sub_type_name].filter(Boolean)
  return parts.length ? parts.join(' · ') : '—'
}

export function feeEarnerLabel(c: CaseOut, users: UserSummary[]) {
  const u = users.find((x) => x.id === c.fee_earner_user_id)
  return u?.display_name ?? '—'
}

export function caseMatchesMainMenuSearch(c: CaseOut, users: UserSummary[], search: string): boolean {
  const s = search.trim().toLowerCase()
  if (!s) return true
  const fe = feeEarnerLabel(c, users)
  const parts = [
    c.case_number,
    c.client_name ?? '',
    c.matter_description ?? '',
    formatCaseStatusLabel(c.status),
    fe,
    c.source_name ?? '',
  ]
  return parts.join(' ').toLowerCase().includes(s)
}

export function filterMainMenuCases(
  cases: CaseOut[],
  matterTypes: string[],
  feeEarnerUserIds: string[],
  caseStatuses: MainMenuCaseStatusFilter[],
): CaseOut[] {
  let result = cases
  if (matterTypes.length > 0) {
    result = result.filter((c) => matterTypes.includes(matterTypeLabel(c)))
  }
  if (feeEarnerUserIds.length > 0) {
    result = result.filter((c) => c.fee_earner_user_id && feeEarnerUserIds.includes(c.fee_earner_user_id))
  }
  if (caseStatuses.length > 0) {
    result = result.filter((c) => caseStatuses.includes(c.status as MainMenuCaseStatusFilter))
  }
  return result
}

export function buildCaseTableRows(
  cases: CaseOut[],
  users: UserSummary[],
  search: string,
  filters: {
    matterTypes: string[]
    feeEarnerUserIds: string[]
    caseStatuses: MainMenuCaseStatusFilter[]
    excludeQuoteMatters?: boolean
    quotesOnlyMatters?: boolean
  },
  sortKey: 'reference' | 'client' | 'matter' | 'feeEarner' | 'status' | 'source' | 'created',
  sortDir: 'asc' | 'desc',
): CaseOut[] {
  const s = search.trim()
  const pool = filters.quotesOnlyMatters
    ? cases.filter((c) => c.status === 'quote' || c.status === 'quote_closed')
    : filters.excludeQuoteMatters
      ? cases.filter((c) => c.status !== 'quote' && c.status !== 'quote_closed')
      : cases
  const filtered = s
    ? pool.filter((c) => caseMatchesMainMenuSearch(c, users, search))
    : filterMainMenuCases(pool, filters.matterTypes, filters.feeEarnerUserIds, filters.caseStatuses)
  const dir = sortDir === 'asc' ? 1 : -1
  return [...filtered].sort((a, b) => {
    const av =
      sortKey === 'reference'
        ? a.case_number
        : sortKey === 'client'
          ? a.client_name ?? ''
          : sortKey === 'matter'
            ? a.matter_description ?? ''
            : sortKey === 'feeEarner'
              ? feeEarnerLabel(a, users)
              : sortKey === 'status'
                ? a.status
                : sortKey === 'source'
                  ? a.source_name ?? ''
                : sortKey === 'created'
                  ? a.created_at
                  : ''
    const bv =
      sortKey === 'reference'
        ? b.case_number
        : sortKey === 'client'
          ? b.client_name ?? ''
          : sortKey === 'matter'
            ? b.matter_description ?? ''
            : sortKey === 'feeEarner'
              ? feeEarnerLabel(b, users)
              : sortKey === 'status'
                ? b.status
                : sortKey === 'source'
                  ? b.source_name ?? ''
                : sortKey === 'created'
                  ? b.created_at
                  : ''
    return String(av).localeCompare(String(bv)) * dir
  })
}

export function CasesTable({
  cases,
  users,
  search,
  filterMatterTypes,
  filterFeeEarnerUserIds,
  filterCaseStatuses,
  caseListFocusId,
  onCaseRowFocus,
  onSelect,
  sortKey,
  sortDir,
  onSort,
  gridTemplateColumns,
  startColumnResize,
  showSourceColumn = false,
  contextMenuVariant = 'main',
  onQuoteConvert,
  onQuoteClose,
  keyboardEnabled = true,
}: {
  cases: CaseOut[]
  users: UserSummary[]
  search: string
  filterMatterTypes: string[]
  filterFeeEarnerUserIds: string[]
  filterCaseStatuses: MainMenuCaseStatusFilter[]
  caseListFocusId: string | null
  onCaseRowFocus: (id: string | null) => void
  onSelect: (id: string, opts?: { docPanel?: CaseOpenDocPanel }) => void
  sortKey: 'reference' | 'client' | 'matter' | 'feeEarner' | 'status' | 'source' | 'created'
  sortDir: 'asc' | 'desc'
  onSort: (k: 'reference' | 'client' | 'matter' | 'feeEarner' | 'status' | 'source' | 'created') => void
  gridTemplateColumns?: string
  startColumnResize: (colIndex: number, startClientX: number, measureRow?: HTMLElement | null) => void
  showSourceColumn?: boolean
  contextMenuVariant?: 'main' | 'quotes'
  onQuoteConvert?: (caseId: string) => void
  onQuoteClose?: (caseId: string) => void
  keyboardEnabled?: boolean
}) {
  const [caseCtx, setCaseCtx] = useState<null | { id: string; x: number; y: number; focusIndex: number }>(null)
  const caseCtxRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!caseCtx) return
    function handleMouseDown(e: MouseEvent) {
      const t = e.target as Node
      if (caseCtxRef.current?.contains(t)) return
      setCaseCtx(null)
    }
    document.addEventListener('mousedown', handleMouseDown)
    return () => document.removeEventListener('mousedown', handleMouseDown)
  }, [caseCtx])

  const rows = useMemo(
    () =>
      buildCaseTableRows(
        cases,
        users,
        search,
        {
          matterTypes: filterMatterTypes,
          feeEarnerUserIds: filterFeeEarnerUserIds,
          caseStatuses: filterCaseStatuses,
          excludeQuoteMatters: contextMenuVariant === 'main',
          quotesOnlyMatters: contextMenuVariant === 'quotes',
        },
        sortKey,
        sortDir,
      ),
    [cases, users, search, filterMatterTypes, filterFeeEarnerUserIds, filterCaseStatuses, sortKey, sortDir, contextMenuVariant],
  )

  const rowIds = useMemo(() => rows.map((r) => r.id), [rows])

  const contextMenuLabel = (action: CaseContextMenuActionKind): string => {
    switch (action) {
      case 'open':
        return 'Open'
      case 'accounts':
        return 'Accounts'
      case 'convert':
        return 'Convert'
      case 'close':
        return 'Close'
    }
  }

  const activateContextAction = useCallback(
    (action: CaseContextMenuActionKind, id: string) => {
      switch (action) {
        case 'open':
          onSelect(id)
          break
        case 'accounts':
          onSelect(id, { docPanel: 'accounts' })
          break
        case 'convert':
          onQuoteConvert?.(id)
          break
        case 'close':
          onQuoteClose?.(id)
          break
      }
    },
    [onQuoteClose, onQuoteConvert, onSelect],
  )

  const openContextMenuForCase = useCallback((id: string) => {
    const el = document.querySelector(`[data-case-row-id="${CSS.escape(id)}"]`) as HTMLElement | null
    const rect = el?.getBoundingClientRect()
    setCaseCtx({
      id,
      x: rect ? rect.left + 16 : 200,
      y: rect ? rect.top + Math.min(rect.height, 32) : 200,
      focusIndex: 0,
    })
  }, [])

  useEffect(() => {
    if (!keyboardEnabled) return

    function onKeyDown(e: KeyboardEvent) {
      if (isEditableKeyboardTarget(e.target) || isModalBlockingKeyboard()) return

      if (caseCtx) {
        const ctxCase = cases.find((c) => c.id === caseCtx.id)
        const actions = buildCaseContextMenuActions(contextMenuVariant, ctxCase?.status)
        if (actions.length === 0) return

        if (e.key === 'Escape') {
          e.preventDefault()
          setCaseCtx(null)
          return
        }
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault()
          const action = actions[caseCtx.focusIndex] ?? actions[0]
          activateContextAction(action, caseCtx.id)
          setCaseCtx(null)
          return
        }
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          e.preventDefault()
          const delta = e.key === 'ArrowDown' ? 1 : -1
          setCaseCtx((prev) => {
            if (!prev) return prev
            const nextIndex = (prev.focusIndex + delta + actions.length) % actions.length
            return { ...prev, focusIndex: nextIndex }
          })
          return
        }
        return
      }

      if (e.shiftKey) {
        if (e.key === 'Enter') {
          if (rowIds.length === 0) return
          e.preventDefault()
          const id = caseListFocusId ?? rowIds[0]
          if (!id) return
          onCaseRowFocus(id)
          openContextMenuForCase(id)
        }
        return
      }

      if (e.key === 'Enter') {
        if (!caseListFocusId) return
        e.preventDefault()
        onSelect(caseListFocusId)
        return
      }

      if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
      if (rowIds.length === 0) return

      e.preventDefault()
      const currentIndex = caseListFocusId ? rowIds.indexOf(caseListFocusId) : -1
      let nextIndex: number
      if (currentIndex < 0) {
        nextIndex = e.key === 'ArrowDown' ? 0 : rowIds.length - 1
      } else {
        nextIndex = e.key === 'ArrowDown' ? Math.min(currentIndex + 1, rowIds.length - 1) : Math.max(currentIndex - 1, 0)
      }
      const nextId = rowIds[nextIndex]
      if (!nextId) return
      onCaseRowFocus(nextId)
      scrollCaseRowIntoView(nextId)
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [
    activateContextAction,
    caseCtx,
    caseListFocusId,
    cases,
    contextMenuVariant,
    keyboardEnabled,
    onCaseRowFocus,
    onSelect,
    openContextMenuForCase,
    rowIds,
  ])

  const columns = useMemo(() => {
    const base = [
      ['reference', 'Reference'],
      ['client', 'Client name'],
      ['matter', 'Description'],
      ['feeEarner', 'Fee earner'],
    ] as const
    if (showSourceColumn) {
      return [...base, ['source', 'Source']] as const
    }
    return [...base, ['status', 'Status']] as const
  }, [showSourceColumn])

  const lastColIndex = columns.length - 1
  const ctxCase = caseCtx ? cases.find((c) => c.id === caseCtx.id) : null

  return (
    <div className="card casesTableCard" style={{ padding: 0, overflow: 'hidden' }}>
      <div className="casesTableScroll">
        <div className="table">
        <div className="tr th" style={gridTemplateColumns ? { gridTemplateColumns } : undefined}>
          {columns.map(([k, label], colIndex) => (
            <div key={k} className="thCell">
              <button type="button" className="thbtn" onClick={() => onSort(k)}>
                {label}
              </button>
              {colIndex < lastColIndex ? (
                <div
                  className="colResizeHandle"
                  role="separator"
                  aria-orientation="vertical"
                  aria-label={`Resize ${label} column`}
                  onMouseDown={(e) => {
                    e.preventDefault()
                    startColumnResize(colIndex, e.clientX, e.currentTarget.closest('.tr.th') as HTMLElement | null)
                  }}
                />
              ) : null}
            </div>
          ))}
        </div>
        {rows.map((c) => {
          const rowActive = caseListFocusId === c.id
          const rowInactive = c.status === 'closed' || c.status === 'archived'
          return (
            <button
              key={c.id}
              type="button"
              data-case-row-id={c.id}
              className={['tr', 'rowbtn', rowActive ? 'active' : '', rowInactive ? 'casesRowInactive' : '']
                .filter(Boolean)
                .join(' ')}
              style={gridTemplateColumns ? { gridTemplateColumns } : undefined}
              onClick={() => onCaseRowFocus(c.id)}
              onDoubleClick={() => onSelect(c.id)}
              onContextMenu={(e) => {
                e.preventDefault()
                onCaseRowFocus(c.id)
                setCaseCtx({ id: c.id, x: e.clientX, y: e.clientY, focusIndex: 0 })
              }}
            >
              <div className="td mono" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                {caseHasRevokedUserAccess(c) ? (
                  <span title="Access restricted for some users" aria-hidden style={{ opacity: 0.85 }}>
                    🔒
                  </span>
                ) : null}
                {c.case_number}
              </div>
              <div className="td">{c.client_name ?? '—'}</div>
              <div className="td">{c.matter_description}</div>
              <div className="td">{feeEarnerLabel(c, users)}</div>
              {showSourceColumn ? (
                <div className="td">{c.source_name ?? '—'}</div>
              ) : (
                <div className="td">
                  <span className={`caseStatusBadge caseStatusBadge--${c.status}`}>
                    {formatCaseStatusLabel(c.status)}
                  </span>
                </div>
              )}
            </button>
          )
        })}
        {rows.length === 0 ? <div className="muted" style={{ padding: 12 }}>No cases match.</div> : null}
        </div>
      </div>
      {caseCtx ? (
        <div
          ref={caseCtxRef}
          className="docContextMenu"
          role="menu"
          style={{ left: caseCtx.x, top: caseCtx.y, zIndex: 30 }}
          onMouseDown={(e) => e.stopPropagation()}
        >
          {buildCaseContextMenuActions(contextMenuVariant, ctxCase?.status).map((action, index) => (
            <div
              key={action}
              className={`docContextItem${caseCtx.focusIndex === index ? ' docContextItem--focused' : ''}`}
              role="menuitem"
              tabIndex={-1}
              onMouseEnter={() => setCaseCtx((prev) => (prev ? { ...prev, focusIndex: index } : prev))}
              onClick={() => {
                const id = caseCtx.id
                setCaseCtx(null)
                activateContextAction(action, id)
              }}
            >
              {contextMenuLabel(action)}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}

export const MAIN_MENU_STATUS_FILTER_OPTIONS: { value: MainMenuCaseStatusFilter; label: string }[] = [
  { value: 'open', label: 'Active' },
  { value: 'post_completion', label: 'Post-completion' },
  { value: 'closed', label: 'Closed' },
  { value: 'archived', label: 'Archived' },
]

export const QUOTES_MENU_STATUS_FILTER_OPTIONS: { value: MainMenuCaseStatusFilter; label: string }[] = [
  { value: 'quote', label: 'Quote' },
  { value: 'quote_closed', label: 'Closed' },
]

export const MainMenuCasesPanel = memo(function MainMenuCasesPanel({
  cases,
  casesErr,
  users,
  filterMatterTypes,
  filterFeeEarnerUserIds,
  filterCaseStatuses,
  onFilterMatterTypesChange,
  onFilterFeeEarnerIdsChange,
  onFilterCaseStatusesChange,
  onPersistFilters,
  gridTemplateColumns,
  startColumnResize,
  caseListFocusId,
  onCaseRowFocus,
  onSelectCase,
  sortKey,
  sortDir,
  onSort,
  onOpenNewMatter,
  onRefreshCases,
  createButtonLabel = 'New matter',
  onCreateClick,
  toolbarMiddle,
  showSourceColumn = false,
  contextMenuVariant = 'main',
  onQuoteConvert,
  onQuoteClose,
  keyboardActive = false,
}: {
  cases: CaseOut[]
  casesErr: string | null
  users: UserSummary[]
  filterMatterTypes: string[]
  filterFeeEarnerUserIds: string[]
  filterCaseStatuses: MainMenuCaseStatusFilter[]
  onFilterMatterTypesChange: (value: string[]) => void
  onFilterFeeEarnerIdsChange: (value: string[]) => void
  onFilterCaseStatusesChange: (value: MainMenuCaseStatusFilter[]) => void
  onPersistFilters: (
    matterTypes: string[],
    feeEarnerUserIds: string[],
    caseStatuses: MainMenuCaseStatusFilter[],
  ) => void
  gridTemplateColumns?: string
  startColumnResize: (colIndex: number, startClientX: number, measureRow?: HTMLElement | null) => void
  caseListFocusId: string | null
  onCaseRowFocus: (id: string | null) => void
  onSelectCase: (id: string, opts?: { docPanel?: CaseOpenDocPanel }) => void
  sortKey: 'reference' | 'client' | 'matter' | 'feeEarner' | 'status' | 'source' | 'created'
  sortDir: 'asc' | 'desc'
  onSort: (k: 'reference' | 'client' | 'matter' | 'feeEarner' | 'status' | 'source' | 'created') => void
  onOpenNewMatter: () => void
  onRefreshCases: () => void
  createButtonLabel?: string
  onCreateClick?: () => void
  toolbarMiddle?: ReactNode
  showSourceColumn?: boolean
  contextMenuVariant?: 'main' | 'quotes'
  onQuoteConvert?: (caseId: string) => void
  onQuoteClose?: (caseId: string) => void
  keyboardActive?: boolean
}) {
  const [caseSearch, setCaseSearch] = useState('')
  const [filterOpen, setFilterOpen] = useState(false)
  const [openFilterField, setOpenFilterField] = useState<'matterType' | 'feeEarner' | 'status' | null>(null)

  const matterTypeOptions = useMemo(() => {
    const set = new Set<string>()
    for (const c of cases) {
      set.add(matterTypeLabel(c))
    }
    return Array.from(set)
      .sort((a, b) => a.localeCompare(b))
      .map((label) => ({ value: label, label }))
  }, [cases])

  const feeEarnerOptions = useMemo(() => {
    const byId = new Map<string, UserSummary>()
    for (const u of users) {
      if (u.can_be_fee_earner === false) continue
      if (!byId.has(u.id)) byId.set(u.id, u)
    }
    return Array.from(byId.values())
      .sort((a, b) => a.display_name.localeCompare(b.display_name))
      .map((u) => ({ value: u.id, label: u.display_name }))
  }, [users])

  const activeFilterCount =
    filterMatterTypes.length + filterFeeEarnerUserIds.length + filterCaseStatuses.length

  const statusFilterOptions =
    contextMenuVariant === 'quotes' ? QUOTES_MENU_STATUS_FILTER_OPTIONS : MAIN_MENU_STATUS_FILTER_OPTIONS

  const toggleFilterOpen = () => {
    setFilterOpen((open) => {
      const next = !open
      if (!next) {
        setOpenFilterField(null)
        onPersistFilters(filterMatterTypes, filterFeeEarnerUserIds, filterCaseStatuses)
      }
      return next
    })
  }

  const clearAllFilters = () => {
    setOpenFilterField(null)
    onFilterMatterTypesChange([])
    onFilterFeeEarnerIdsChange([])
    onFilterCaseStatusesChange([])
    onPersistFilters([], [], [])
  }

  return (
    <div className="mainMenuShell mainMenuShell--mainMenu">
      {casesErr ? <div className="error">{casesErr}</div> : null}
      <div className={`mainMenuFilterBar${filterOpen ? ' mainMenuFilterBar--dropdownOpen' : ''}`}>
        <div className="row mainMenuFilterRow mainMenuFilterRow--toolbar mainMenuFilterRow--searchRight">
          <div className="mainMenuFilterRowLeft">
            <button type="button" className="btn primary toolbarLeadBtn" onClick={onCreateClick ?? onOpenNewMatter}>
              {createButtonLabel}
            </button>
            {toolbarMiddle}
            <button type="button" className="btn" onClick={onRefreshCases}>
              Refresh
            </button>
          </div>
          <div className="mainMenuFilterRowRight">
            <div className="caseToolbarDropdownWrap mainMenuFilterToolbarGroup">
              <button
                type="button"
                className="btn mainMenuFilterBtn"
                aria-expanded={filterOpen}
                aria-haspopup="true"
                aria-controls="main-menu-filter-menu"
                id="main-menu-filter-button"
                onClick={toggleFilterOpen}
              >
                <span className="mainMenuFilterBtnInner">
                  <svg
                    className="mainMenuFilterBtnIcon"
                    width={16}
                    height={16}
                    viewBox="0 0 24 24"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                    aria-hidden
                  >
                    <polygon
                      points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      fill="none"
                    />
                  </svg>
                  <span>Filter</span>
                  <span className="mainMenuFilterBtnCount">({activeFilterCount})</span>
                </span>
              </button>
              {activeFilterCount > 0 ? (
                <button
                  type="button"
                  className="mainMenuFilterClearBtn mainMenuFilterClearBtn--toolbar"
                  aria-label="Clear all filters"
                  onClick={clearAllFilters}
                >
                  ×
                </button>
              ) : null}
              <div
                id="main-menu-filter-menu"
                className={`caseToolbarDropdown mainMenuFilterDropdown${filterOpen ? '' : ' mainMenuFilterDropdown--hidden'}`}
                role="group"
                aria-labelledby="main-menu-filter-button"
                aria-hidden={!filterOpen}
                onMouseDown={(e) => e.stopPropagation()}
              >
                <div className="stack mainMenuFilterDropdownBody">
                  <MainMenuFilterCheckboxDropdown
                    label="Matter type"
                    options={matterTypeOptions}
                    selected={filterMatterTypes}
                    onChange={onFilterMatterTypesChange}
                    open={openFilterField === 'matterType'}
                    onOpenChange={(open) => setOpenFilterField(open ? 'matterType' : null)}
                  />
                  <MainMenuFilterCheckboxDropdown
                    label="Fee earner"
                    options={feeEarnerOptions}
                    selected={filterFeeEarnerUserIds}
                    onChange={onFilterFeeEarnerIdsChange}
                    open={openFilterField === 'feeEarner'}
                    onOpenChange={(open) => setOpenFilterField(open ? 'feeEarner' : null)}
                  />
                  <MainMenuFilterCheckboxDropdown
                    label="Status"
                    options={statusFilterOptions}
                    selected={filterCaseStatuses}
                    onChange={(next) => onFilterCaseStatusesChange(next as MainMenuCaseStatusFilter[])}
                    open={openFilterField === 'status'}
                    onOpenChange={(open) => setOpenFilterField(open ? 'status' : null)}
                  />
                </div>
              </div>
            </div>
            <SearchInput
              placeholder="Search"
              value={caseSearch}
              onChange={(e) => setCaseSearch(e.target.value)}
              onClear={() => setCaseSearch('')}
              className="mainMenuSearchInput"
              aria-label="Search cases"
            />
          </div>
        </div>
      </div>
      {null}
      <CasesTable
        cases={cases}
        users={users}
        search={caseSearch}
        filterMatterTypes={filterMatterTypes}
        filterFeeEarnerUserIds={filterFeeEarnerUserIds}
        filterCaseStatuses={filterCaseStatuses}
        gridTemplateColumns={gridTemplateColumns}
        startColumnResize={startColumnResize}
        showSourceColumn={showSourceColumn}
        caseListFocusId={caseListFocusId}
        onCaseRowFocus={onCaseRowFocus}
        onSelect={onSelectCase}
        sortKey={sortKey}
        sortDir={sortDir}
        onSort={onSort}
        contextMenuVariant={contextMenuVariant}
        onQuoteConvert={onQuoteConvert}
        onQuoteClose={onQuoteClose}
        keyboardEnabled={keyboardActive && !filterOpen && openFilterField === null}
      />
    </div>
  )
})



