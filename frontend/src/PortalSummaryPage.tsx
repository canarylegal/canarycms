import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch, type ApiError } from './api'
import { SearchInput } from './SearchInput'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import type {
  PortalSummaryBucket,
  PortalSummaryKind,
  PortalSummaryOut,
  PortalSummaryRowOut,
} from './types/portalSummary'

type Props = {
  token: string
  onSelectCase: (caseId: string) => void
}

const KIND_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'All kinds' },
  { value: 'quote', label: 'Quote' },
  { value: 'form', label: 'Form' },
  { value: 'canary_sign', label: 'Canary Sign' },
  { value: 'docusign', label: 'DocuSign' },
]

const PORTAL_COLUMNS = [
  ['kind', 'Kind'],
  ['reference', 'Reference'],
  ['client', 'Client'],
  ['title', 'Title'],
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

export function PortalSummaryPage({ token, onSelectCase }: Props) {
  const [bucket, setBucket] = useState<PortalSummaryBucket>('outstanding')
  const [kind, setKind] = useState<'' | PortalSummaryKind>('')
  const [kindOpen, setKindOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [rows, setRows] = useState<PortalSummaryRowOut[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [focusKey, setFocusKey] = useState<string | null>(null)
  const [ctx, setCtx] = useState<null | { x: number; y: number; row: PortalSummaryRowOut }>(null)
  const ctxRef = useRef<HTMLDivElement | null>(null)

  const load = useCallback(async () => {
    setBusy(true)
    setErr(null)
    try {
      const q = new URLSearchParams({ bucket })
      if (kind) q.set('kind', kind)
      const data = await apiFetch<PortalSummaryOut>(`/portal-summary?${q}`, { token })
      setRows(data.rows)
    } catch (e) {
      setErr((e as ApiError).message ?? 'Failed to load portal summary')
      setRows([])
    } finally {
      setBusy(false)
    }
  }, [token, bucket, kind])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    setFocusKey(null)
    setCtx(null)
  }, [bucket, kind, search])

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

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return rows
    return rows.filter((r) => {
      const hay = [
        r.title,
        r.case_number,
        r.client_name,
        r.matter_description,
        r.contact_or_recipients,
        r.sent_by_display_name,
        r.status,
        kindLabel(r.kind),
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
      return hay.includes(q)
    })
  }, [rows, search])

  const openMatter = useCallback(
    (r: PortalSummaryRowOut) => {
      setCtx(null)
      onSelectCase(r.case_id)
    },
    [onSelectCase],
  )

  const copyReference = useCallback(async (r: PortalSummaryRowOut) => {
    setCtx(null)
    const text = (r.case_number || '').trim()
    if (!text) return
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      // ignore clipboard failures (permissions / insecure context)
    }
  }, [])

  return (
    <div className="mainMenuShell mainMenuShell--mainMenu">
      {err ? <div className="error">{err}</div> : null}
      <div className={`mainMenuFilterBar${kindOpen ? ' mainMenuFilterBar--dropdownOpen' : ''}`}>
        <div className="row mainMenuFilterRow mainMenuFilterRow--toolbar mainMenuFilterRow--searchRight">
          <div className="mainMenuFilterRowLeft">
            <button
              type="button"
              className={`btn${bucket === 'outstanding' ? ' primary' : ''}`}
              disabled={busy}
              onClick={() => setBucket('outstanding')}
            >
              Outstanding
            </button>
            <button
              type="button"
              className={`btn${bucket === 'completed' ? ' primary' : ''}`}
              disabled={busy}
              onClick={() => setBucket('completed')}
            >
              Completed
            </button>
            <div className="tasksToolbarLayoutGroup">
              <span className="tasksToolbarLayoutLabel">Kind</span>
              <SingleSelectDropdown
                hideLabel
                label="Kind filter"
                options={KIND_OPTIONS}
                value={kind}
                disabled={busy}
                onChange={(v) => setKind(v as '' | PortalSummaryKind)}
                open={kindOpen}
                onOpenChange={setKindOpen}
              />
            </div>
            <button type="button" className="btn" disabled={busy} onClick={() => void load()}>
              Refresh
            </button>
          </div>
          <div className="mainMenuFilterRowRight">
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
                  : 'No actions match your search.'}
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
                  <div className="td">
                    <div>{r.client_name || '—'}</div>
                    {r.matter_description ? (
                      <div className="muted" style={{ fontSize: 12 }}>
                        {r.matter_description}
                      </div>
                    ) : null}
                  </div>
                  <div className="td">{r.title}</div>
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
          {ctx.row.case_number?.trim() ? (
            <div
              className="docContextItem"
              role="menuitem"
              tabIndex={0}
              onClick={() => void copyReference(ctx.row)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  void copyReference(ctx.row)
                }
              }}
            >
              Copy reference
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
