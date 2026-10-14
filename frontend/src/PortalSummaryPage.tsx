import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch, type ApiError } from './api'
import { useDialogs } from './DialogProvider'
import { MainMenuFilterCheckboxDropdown } from './MainMenuFilterCheckboxDropdown'
import { useNotifications } from './NotificationsProvider'
import { SearchInput } from './SearchInput'
import type { UserSummary } from './types/auth'
import type {
  PortalSummaryBucket,
  PortalSummaryKind,
  PortalSummaryOut,
  PortalSummaryRowOut,
} from './types/portalSummary'

type Props = {
  token: string
  users: UserSummary[]
  filterKinds: string[]
  filterSenderUserIds: string[]
  filterFeeEarnerUserIds: string[]
  onFilterKindsChange: (value: string[]) => void
  onFilterSenderIdsChange: (value: string[]) => void
  onFilterFeeEarnerIdsChange: (value: string[]) => void
  onPersistFilters: (kinds: string[], senderUserIds: string[], feeEarnerUserIds: string[]) => void
  onSelectCase: (caseId: string) => void
}

const TYPE_FILTER_OPTIONS: { value: string; label: string }[] = [
  { value: 'quote', label: 'Quote' },
  { value: 'form', label: 'Form' },
  { value: 'canary_sign', label: 'Canary Sign' },
  { value: 'docusign', label: 'DocuSign' },
]

const PORTAL_COLUMNS = [
  ['kind', 'Type'],
  ['reference', 'Reference'],
  ['title', 'Description'],
  ['recipients', 'Recipients'],
  ['status', 'Status'],
  ['sent', 'Sent'],
] as const

function kindLabel(kind: PortalSummaryKind): string {
  switch (kind) {
    case 'quote':
      return 'Quote'
    case 'form':
      return 'Form'
    case 'canary_sign':
      return 'Canary Sign'
    case 'docusign':
      return 'DocuSign'
  }
}

function kindBadgeClass(kind: PortalSummaryKind): string {
  switch (kind) {
    case 'quote':
      return 'portalActionBadge portalActionBadge--kindQuote'
    case 'form':
      return 'portalActionBadge portalActionBadge--kindForm'
    case 'canary_sign':
      return 'portalActionBadge portalActionBadge--kindSign'
    case 'docusign':
      return 'portalActionBadge portalActionBadge--kindSign'
  }
}

function rowKey(r: PortalSummaryRowOut): string {
  return `${r.kind}:${r.id}`
}

function formatWhen(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

function canResend(r: PortalSummaryRowOut, bucket: PortalSummaryBucket): boolean {
  if (bucket !== 'outstanding') return false
  if (r.kind === 'quote' && !r.file_id) return false
  return true
}

/** Forms and Canary Sign have staff void endpoints; quotes/DocuSign do not (yet). */
function canVoid(r: PortalSummaryRowOut, bucket: PortalSummaryBucket): boolean {
  if (bucket !== 'outstanding') return false
  return r.kind === 'form' || r.kind === 'canary_sign'
}

export function PortalSummaryPage({
  token,
  users,
  filterKinds,
  filterSenderUserIds,
  filterFeeEarnerUserIds,
  onFilterKindsChange,
  onFilterSenderIdsChange,
  onFilterFeeEarnerIdsChange,
  onPersistFilters,
  onSelectCase,
}: Props) {
  const { askConfirm } = useDialogs()
  const { push: pushNotification } = useNotifications()
  const [bucket, setBucket] = useState<PortalSummaryBucket>('outstanding')
  const [filterOpen, setFilterOpen] = useState(false)
  const [openFilterField, setOpenFilterField] = useState<'type' | 'sender' | 'feeEarner' | null>(null)
  const [search, setSearch] = useState('')
  const [rows, setRows] = useState<PortalSummaryRowOut[]>([])
  const [busy, setBusy] = useState(false)
  const [actionBusy, setActionBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [focusKey, setFocusKey] = useState<string | null>(null)
  const [ctx, setCtx] = useState<null | { x: number; y: number; row: PortalSummaryRowOut }>(null)
  const ctxRef = useRef<HTMLDivElement | null>(null)

  const load = useCallback(async () => {
    setBusy(true)
    setErr(null)
    try {
      const q = new URLSearchParams({ bucket })
      const data = await apiFetch<PortalSummaryOut>(`/portal-summary?${q}`, { token })
      setRows(data.rows)
    } catch (e) {
      setErr((e as ApiError).message ?? 'Failed to load portal summary')
      setRows([])
    } finally {
      setBusy(false)
    }
  }, [token, bucket])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    setFocusKey(null)
    setCtx(null)
  }, [bucket, search, filterKinds, filterSenderUserIds, filterFeeEarnerUserIds])

  useEffect(() => {
    if (!ctx) return
    function onMouseDown(e: MouseEvent) {
      const t = e.target as Node
      if (ctxRef.current?.contains(t)) return
      setCtx(null)
    }
    document.addEventListener('mousedown', onMouseDown)
    return () => document.removeEventListener('mousedown', onMouseDown)
  }, [ctx])

  const userNameById = useMemo(() => {
    const map = new Map<string, string>()
    for (const u of users) {
      map.set(u.id, u.display_name || u.email)
    }
    return map
  }, [users])

  const senderOptions = useMemo(() => {
    const byId = new Map<string, string>()
    for (const r of rows) {
      if (!r.sent_by_user_id) continue
      const label =
        r.sent_by_display_name || userNameById.get(r.sent_by_user_id) || r.sent_by_user_id
      if (!byId.has(r.sent_by_user_id)) byId.set(r.sent_by_user_id, label)
    }
    for (const id of filterSenderUserIds) {
      if (byId.has(id)) continue
      byId.set(id, userNameById.get(id) || id)
    }
    return Array.from(byId.entries())
      .sort((a, b) => a[1].localeCompare(b[1]))
      .map(([value, label]) => ({ value, label }))
  }, [rows, filterSenderUserIds, userNameById])

  const feeEarnerOptions = useMemo(() => {
    const byId = new Map<string, string>()
    for (const u of users) {
      if (u.can_be_fee_earner === false) continue
      if (!byId.has(u.id)) byId.set(u.id, u.display_name || u.email)
    }
    for (const r of rows) {
      if (!r.fee_earner_user_id) continue
      const label =
        r.fee_earner_display_name || userNameById.get(r.fee_earner_user_id) || r.fee_earner_user_id
      if (!byId.has(r.fee_earner_user_id)) byId.set(r.fee_earner_user_id, label)
    }
    for (const id of filterFeeEarnerUserIds) {
      if (byId.has(id)) continue
      byId.set(id, userNameById.get(id) || id)
    }
    return Array.from(byId.entries())
      .sort((a, b) => a[1].localeCompare(b[1]))
      .map(([value, label]) => ({ value, label }))
  }, [users, rows, filterFeeEarnerUserIds, userNameById])

  const activeFilterCount =
    filterKinds.length + filterSenderUserIds.length + filterFeeEarnerUserIds.length

  const toggleFilterOpen = () => {
    setFilterOpen((open) => {
      const next = !open
      if (!next) {
        setOpenFilterField(null)
        onPersistFilters(filterKinds, filterSenderUserIds, filterFeeEarnerUserIds)
      }
      return next
    })
  }

  const clearAllFilters = () => {
    setOpenFilterField(null)
    onFilterKindsChange([])
    onFilterSenderIdsChange([])
    onFilterFeeEarnerIdsChange([])
    onPersistFilters([], [], [])
  }

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return rows.filter((r) => {
      if (filterKinds.length > 0 && !filterKinds.includes(r.kind)) return false
      if (
        filterSenderUserIds.length > 0 &&
        (!r.sent_by_user_id || !filterSenderUserIds.includes(r.sent_by_user_id))
      ) {
        return false
      }
      if (
        filterFeeEarnerUserIds.length > 0 &&
        (!r.fee_earner_user_id || !filterFeeEarnerUserIds.includes(r.fee_earner_user_id))
      ) {
        return false
      }
      if (!q) return true
      const hay = [
        r.title,
        r.case_number,
        r.client_name,
        r.matter_description,
        r.contact_or_recipients,
        r.sent_by_display_name,
        r.fee_earner_display_name,
        r.status,
        kindLabel(r.kind),
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
      return hay.includes(q)
    })
  }, [rows, search, filterKinds, filterSenderUserIds, filterFeeEarnerUserIds])

  const openMatter = useCallback(
    (r: PortalSummaryRowOut) => {
      setCtx(null)
      onSelectCase(r.case_id)
    },
    [onSelectCase],
  )

  const resend = useCallback(
    async (r: PortalSummaryRowOut) => {
      setCtx(null)
      if (!canResend(r, bucket)) return
      const ok = await askConfirm({
        title: 'Resend portal link?',
        message:
          'The recipient will receive another e-mail with a link to open this item in the portal (where appropriate).',
        confirmLabel: 'Resend',
      })
      if (!ok) return
      setActionBusy(true)
      setErr(null)
      try {
        if (r.kind === 'quote') {
          const out = await apiFetch<{ email_sent?: boolean; email_skip_reason?: string | null }>(
            `/cases/${r.case_id}/files/${r.file_id}/quote-portal/resend`,
            { token, method: 'POST' },
          )
          if (out.email_sent === false) {
            pushNotification(out.email_skip_reason || 'Still available, but the notification e-mail was not sent.')
          } else {
            pushNotification('Quote link resent.')
          }
        } else if (r.kind === 'form') {
          const out = await apiFetch<{ email_sent?: boolean; email_skip_reason?: string | null }>(
            `/cases/${r.case_id}/portal/forms/submissions/${r.id}/resend`,
            { token, method: 'POST' },
          )
          if (out.email_sent === false) {
            pushNotification(out.email_skip_reason || 'Still available, but the notification e-mail was not sent.')
          } else {
            pushNotification('Form link resent.')
          }
        } else if (r.kind === 'canary_sign') {
          await apiFetch(`/cases/${r.case_id}/canary-sign/requests/${r.id}/remind`, {
            token,
            method: 'POST',
            json: {},
          })
          pushNotification('Signing reminder sent.')
        } else {
          await apiFetch(`/cases/${r.case_id}/docusign/requests/${r.id}/resend`, {
            token,
            method: 'POST',
          })
          pushNotification('DocuSign link resent.')
        }
        await load()
      } catch (e) {
        setErr((e as ApiError).message ?? 'Could not resend')
      } finally {
        setActionBusy(false)
      }
    },
    [askConfirm, bucket, load, pushNotification, token],
  )

  const voidItem = useCallback(
    async (r: PortalSummaryRowOut) => {
      setCtx(null)
      if (!canVoid(r, bucket)) return
      const ok = await askConfirm({
        title: r.kind === 'form' ? 'Void pending form?' : 'Void signing request?',
        message:
          r.kind === 'form'
            ? 'The client will no longer be able to submit it.'
            : 'Recipients will no longer be able to sign this document.',
        danger: true,
        confirmLabel: 'Void',
      })
      if (!ok) return
      setActionBusy(true)
      setErr(null)
      try {
        if (r.kind === 'form') {
          await apiFetch(`/cases/${r.case_id}/portal/forms/submissions/${r.id}/void`, {
            token,
            method: 'POST',
          })
          pushNotification('Form voided.')
        } else if (r.kind === 'canary_sign') {
          await apiFetch(`/cases/${r.case_id}/canary-sign/requests/${r.id}/void`, {
            token,
            method: 'POST',
            json: { reason: null },
          })
          pushNotification('Signing request voided.')
        }
        await load()
      } catch (e) {
        setErr((e as ApiError).message ?? 'Could not void')
      } finally {
        setActionBusy(false)
      }
    },
    [askConfirm, bucket, load, pushNotification, token],
  )

  return (
    <div className="mainMenuShell mainMenuShell--mainMenu">
      {err ? <div className="error">{err}</div> : null}
      <div className={`mainMenuFilterBar${filterOpen ? ' mainMenuFilterBar--dropdownOpen' : ''}`}>
        <div className="row mainMenuFilterRow mainMenuFilterRow--toolbar mainMenuFilterRow--searchRight">
          <div className="mainMenuFilterRowLeft">
            <button
              type="button"
              className={`btn${bucket === 'outstanding' ? ' btn--selected' : ''}`}
              disabled={busy || actionBusy}
              onClick={() => setBucket('outstanding')}
            >
              Outstanding
            </button>
            <button
              type="button"
              className={`btn${bucket === 'completed' ? ' btn--selected' : ''}`}
              disabled={busy || actionBusy}
              onClick={() => setBucket('completed')}
            >
              Completed
            </button>
            <button type="button" className="btn" disabled={busy || actionBusy} onClick={() => void load()}>
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
                aria-controls="portal-summary-filter-menu"
                id="portal-summary-filter-button"
                disabled={busy || actionBusy}
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
                id="portal-summary-filter-menu"
                className={`caseToolbarDropdown mainMenuFilterDropdown${filterOpen ? '' : ' mainMenuFilterDropdown--hidden'}`}
                role="group"
                aria-labelledby="portal-summary-filter-button"
                aria-hidden={!filterOpen}
                onMouseDown={(e) => e.stopPropagation()}
              >
                <div className="stack mainMenuFilterDropdownBody">
                  <MainMenuFilterCheckboxDropdown
                    label="Type"
                    options={TYPE_FILTER_OPTIONS}
                    selected={filterKinds}
                    onChange={onFilterKindsChange}
                    open={openFilterField === 'type'}
                    onOpenChange={(open) => setOpenFilterField(open ? 'type' : null)}
                  />
                  <MainMenuFilterCheckboxDropdown
                    label="Sender"
                    options={senderOptions}
                    selected={filterSenderUserIds}
                    onChange={onFilterSenderIdsChange}
                    open={openFilterField === 'sender'}
                    onOpenChange={(open) => setOpenFilterField(open ? 'sender' : null)}
                  />
                  <MainMenuFilterCheckboxDropdown
                    label="Fee earner"
                    options={feeEarnerOptions}
                    selected={filterFeeEarnerUserIds}
                    onChange={onFilterFeeEarnerIdsChange}
                    open={openFilterField === 'feeEarner'}
                    onOpenChange={(open) => setOpenFilterField(open ? 'feeEarner' : null)}
                  />
                </div>
              </div>
            </div>
            <SearchInput
              placeholder="Search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onClear={() => setSearch('')}
              className="mainMenuSearchInput"
              aria-label="Search portal actions"
            />
          </div>
        </div>
      </div>

      <div className="card casesTableCard" style={{ padding: 0, overflow: 'hidden' }}>
        <div className="casesTableScroll portalSummaryTableScroll">
          <div className="table">
            <div className="tr th">
              {PORTAL_COLUMNS.map(([k, label]) => (
                <div key={k} className="thCell">
                  <span className="thbtn" style={{ cursor: 'default' }}>
                    {label}
                  </span>
                </div>
              ))}
            </div>
            {busy && rows.length === 0 ? <div className="muted" style={{ padding: 12 }}>Loading…</div> : null}
            {!busy && filtered.length === 0 ? (
              <div className="muted" style={{ padding: 12 }}>
                {rows.length === 0
                  ? bucket === 'outstanding'
                    ? 'No outstanding portal actions.'
                    : 'No completed portal actions.'
                  : 'No actions match your filters.'}
              </div>
            ) : null}
            {filtered.map((r) => {
              const key = rowKey(r)
              const active = focusKey === key
              return (
                <button
                  key={key}
                  type="button"
                  className={`tr rowbtn${active ? ' active' : ''}`}
                  aria-selected={active}
                  onClick={() => setFocusKey(key)}
                  onDoubleClick={() => openMatter(r)}
                  onContextMenu={(e) => {
                    e.preventDefault()
                    e.stopPropagation()
                    setFocusKey(key)
                    setCtx({ x: e.clientX, y: e.clientY, row: r })
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      openMatter(r)
                    }
                  }}
                >
                  <div className="td">
                    <span className={kindBadgeClass(r.kind)}>{kindLabel(r.kind)}</span>
                  </div>
                  <div className="td">{r.case_number || '—'}</div>
                  <div className="td" title={r.title || undefined}>
                    {r.title}
                  </div>
                  <div className="td">{r.contact_or_recipients || '—'}</div>
                  <div className="td">{r.status}</div>
                  <div className="td">{formatWhen(r.created_at)}</div>
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {ctx ? (
        <div
          ref={ctxRef}
          className="docContextMenu"
          style={{ left: ctx.x, top: ctx.y, zIndex: 30 }}
          onMouseDown={(e) => e.stopPropagation()}
        >
          <div
            className="docContextItem"
            role="menuitem"
            tabIndex={0}
            onClick={() => openMatter(ctx.row)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                openMatter(ctx.row)
              }
            }}
          >
            Open matter
          </div>
          {canResend(ctx.row, bucket) ? (
            <div
              className="docContextItem"
              role="menuitem"
              tabIndex={0}
              onClick={() => void resend(ctx.row)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  void resend(ctx.row)
                }
              }}
            >
              Resend
            </div>
          ) : null}
          {canVoid(ctx.row, bucket) ? (
            <div
              className="docContextItem"
              role="menuitem"
              tabIndex={0}
              onClick={() => void voidItem(ctx.row)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  void voidItem(ctx.row)
                }
              }}
            >
              Void
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
