import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useActionMenuKeyboard } from './useActionMenuKeyboard'
import { buildCaseContextMenuActions, scrollCaseRowIntoView, type CaseContextMenuActionKind } from './caseListKeyboard'
import type { CaseOpenDocPanel } from './case/CaseDetail'
import { isEditableKeyboardTarget, isModalBlockingKeyboard } from './keyboardUtils'
import { caseHasRevokedUserAccess, formatCaseStatusLabel } from './types'
import type { CaseOut, UserSummary } from './types'
import type { MainMenuCaseStatusFilter } from './userUiPreferences'
import { buildCaseTableRows, buildFeeEarnerLabels } from './mainMenuCaseData'

export function CasesTable({
  cases,
  serverRows = false,
  loading = false,
  hasMore = false,
  onLoadMore,
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
  serverRows?: boolean
  loading?: boolean
  hasMore?: boolean
  onLoadMore?: () => void
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
  const closeCaseActions = useCallback(() => setCaseCtx(null), [])
  useActionMenuKeyboard(caseCtxRef, Boolean(caseCtx), closeCaseActions)

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
    () => serverRows ? cases :
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
    [serverRows, cases, users, search, filterMatterTypes, filterFeeEarnerUserIds, filterCaseStatuses, sortKey, sortDir, contextMenuVariant],
  )

  const scrollRef = useRef<HTMLDivElement | null>(null)
  const sentinelRef = useRef<HTMLDivElement | null>(null)
  const pendingKeyboardId = useRef<string | null>(null)
  useEffect(() => {
    if (!keyboardEnabled || !hasMore || loading || !onLoadMore || !sentinelRef.current) return
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) onLoadMore()
    }, {root: scrollRef.current, rootMargin: '200px'})
    observer.observe(sentinelRef.current)
    return () => observer.disconnect()
  }, [keyboardEnabled, hasMore, loading, onLoadMore, rows.length])
  useEffect(() => {
    const id = pendingKeyboardId.current
    if (!id) return
    const index = rows.findIndex(row => row.id === id)
    if (index >= 0 && rows[index + 1]) {
      pendingKeyboardId.current = null
      onCaseRowFocus(rows[index + 1].id)
      scrollCaseRowIntoView(rows[index + 1].id)
    } else if (!loading) pendingKeyboardId.current = null
  }, [rows, loading, onCaseRowFocus])

  const feeEarnerLabels = useMemo(() => buildFeeEarnerLabels(users), [users])

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
      if (e.target instanceof HTMLElement && e.target.closest('button, [role="menu"]')) return

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
          const id = caseListFocusId && rowIds.includes(caseListFocusId) ? caseListFocusId : rowIds[0]
          if (!id) return
          onCaseRowFocus(id)
          openContextMenuForCase(id)
        }
        return
      }

      if (e.key === 'Enter') {
        if (!caseListFocusId || !rowIds.includes(caseListFocusId)) return
        e.preventDefault()
        onSelect(caseListFocusId)
        return
      }

      if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
      if (rowIds.length === 0) return

      e.preventDefault()
      const currentIndex = caseListFocusId ? rowIds.indexOf(caseListFocusId) : -1
      if (e.key === 'ArrowDown' && currentIndex === rowIds.length - 1 && hasMore) {
        pendingKeyboardId.current = caseListFocusId
        onLoadMore?.()
        return
      }
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
    hasMore,
    onLoadMore,
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
      <div className="casesTableScroll" ref={scrollRef} aria-busy={loading}>
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
            <div
              key={c.id}
              role="row"
              data-case-row-id={c.id}
              className={['tr', 'rowbtn', rowActive ? 'active' : '', rowInactive ? 'casesRowInactive' : '']
                .filter(Boolean)
                .join(' ')}
              style={gridTemplateColumns ? { gridTemplateColumns } : undefined}
              tabIndex={0}
              onClick={() => onCaseRowFocus(c.id)}
              onDoubleClick={() => onSelect(c.id)}
              onKeyDown={(e) => {
                if (e.target !== e.currentTarget) return
                if (e.key === 'Enter') {
                  e.preventDefault()
                  onSelect(c.id)
                }
              }}
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
              <div className="td">{c.fee_earner_user_id == null ? '—' : feeEarnerLabels.get(c.fee_earner_user_id) ?? '—'}</div>
              {showSourceColumn ? (
                <div className="td">{c.source_name ?? '—'}</div>
              ) : (
                <div className="td">
                  <span className={`caseStatusBadge caseStatusBadge--${c.status}`}>
                    {formatCaseStatusLabel(c.status)}
                  </span>
                </div>
              )}
            </div>
          )
        })}
        {!loading && rows.length === 0 ? <div className="muted" style={{ padding: 12 }}>No cases match.</div> : null}
        <div ref={sentinelRef} style={{height: 1}} aria-hidden />
        {loading ? <div className="muted" role="status" style={{padding: 12}}>Loading matters…</div> : null}
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
