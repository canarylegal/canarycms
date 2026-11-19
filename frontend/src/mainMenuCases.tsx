import { memo, useMemo, useState, type ReactNode } from 'react'
import { MainMenuFilterCheckboxDropdown } from './MainMenuFilterCheckboxDropdown'
import { SearchInput } from './SearchInput'
import type { CaseOpenDocPanel } from './case/CaseDetail'
import type { CaseOut, UserSummary } from './types'
import type { MainMenuCaseStatusFilter } from './userUiPreferences'
import { CasesTable } from './CasesTable'
import { matterTypeLabel } from './mainMenuCaseData'

// Preserve existing imports while the panel, table and data helpers evolve separately.
export { CasesTable } from './CasesTable'
export { matterTypeLabel, feeEarnerLabel, caseMatchesMainMenuSearch, filterMainMenuCases, buildCaseTableRows } from './mainMenuCaseData'

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



