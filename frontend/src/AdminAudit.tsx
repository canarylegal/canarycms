import { useCallback, useEffect, useMemo, useState } from 'react'
import { actorLabel } from './auditDisplay'
import { apiFetch } from './api'
import { MatterSearchPicker } from './MatterSearchPicker'
import type { AdminAuditEvent, AdminUserPublic } from './types'
import { useColumnWidths } from './useColumnWidths'

const AUDIT_COLUMN_LABELS = ['When', 'User', 'Matter', 'Activity', 'Action'] as const
const AUDIT_COLUMN_FALLBACK = [168, 176, 192, 360, 200]

function formatTs(s: string) {
  const d = new Date(s)
  if (Number.isNaN(d.getTime())) return s
  return d.toLocaleString()
}

function matterLabel(e: AdminAuditEvent): string {
  if (e.case_number) {
    const title = e.case_title?.trim()
    return title ? `${e.case_number} — ${title}` : e.case_number
  }
  const cid = e.case_id ?? (typeof e.meta?.case_id === 'string' ? e.meta.case_id : null)
  return cid ?? '—'
}

type Props = {
  token: string
  embedded?: boolean
}

export function AdminAudit({ token, embedded }: Props) {
  const [events, setEvents] = useState<AdminAuditEvent[]>([])
  const [users, setUsers] = useState<AdminUserPublic[]>([])
  const [action, setAction] = useState('')
  const [actorUserId, setActorUserId] = useState('')
  const [caseId, setCaseId] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const { gridTemplateColumns, startResize } = useColumnWidths(AUDIT_COLUMN_LABELS.length, {
    fallbackWidths: AUDIT_COLUMN_FALLBACK,
    min: 72,
  })

  const rowGridStyle = gridTemplateColumns ? { gridTemplateColumns } : undefined

  const usersById = useMemo(() => new Map(users.map((u) => [u.id, u])), [users])

  const loadFilters = useCallback(async () => {
    try {
      const userRows = await apiFetch<AdminUserPublic[]>('/admin/users', { token })
      setUsers(userRows)
    } catch {
      /* filters are optional */
    }
  }, [token])

  const load = useCallback(
    async (overrides?: { action?: string; actorUserId?: string; caseId?: string }) => {
      setBusy(true)
      setErr(null)
      try {
        const qs = new URLSearchParams()
        const actionVal = overrides?.action ?? action
        const actorVal = overrides?.actorUserId ?? actorUserId
        const caseVal = overrides?.caseId ?? caseId
        if (actionVal.trim()) qs.set('action', actionVal.trim())
        if (actorVal) qs.set('actor_user_id', actorVal)
        if (caseVal) qs.set('case_id', caseVal)
        qs.set('limit', '100')
        const data = await apiFetch<AdminAuditEvent[]>(`/admin/audit-events?${qs.toString()}`, { token })
        setEvents(data)
      } catch (e: unknown) {
        const msg =
          e && typeof e === 'object' && 'message' in e
            ? String((e as { message?: string }).message)
            : 'Failed to load audit events'
        setErr(msg)
      } finally {
        setBusy(false)
      }
    },
    [action, actorUserId, caseId, token],
  )

  useEffect(() => {
    void loadFilters()
    void load()
    // Initial load only; filter changes call load() explicitly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  function applyFilters(next?: { action?: string; actorUserId?: string; caseId?: string }) {
    void load(next)
  }

  return (
    <div className="auditPage stack">
      <div className="paneHead">
        {embedded ? <h3 style={{ margin: 0 }}>Audit</h3> : <h2>Admin · Audit</h2>}
        <button type="button" className="btn" disabled={busy} onClick={() => void load()}>
          Refresh
        </button>
      </div>

      <div className="auditToolbar card">
        <div className="auditToolbarFields">
          <label className="auditToolbarField">
            <span className="auditToolbarLabel">User</span>
            <select
              value={actorUserId}
              onChange={(e) => {
                const v = e.target.value
                setActorUserId(v)
                applyFilters({ actorUserId: v })
              }}
            >
              <option value="">All users</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.display_name} ({u.initials})
                </option>
              ))}
            </select>
          </label>
          <div className="auditToolbarField auditToolbarField--matter">
            <span className="auditToolbarLabel">Matter</span>
            <MatterSearchPicker
              token={token}
              value={caseId}
              onChange={(v) => {
                setCaseId(v)
                applyFilters({ caseId: v })
              }}
              disabled={busy}
              listMaxHeight={160}
              idleHint="All matters — search to filter by one matter."
              changeLabel="Clear"
            />
          </div>
          <label className="auditToolbarField auditToolbarField--action">
            <span className="auditToolbarLabel">Action</span>
            <input
              placeholder="e.g. case.file.rename"
              value={action}
              onChange={(e) => setAction(e.target.value)}
            />
          </label>
        </div>
        <div className="auditToolbarActions">
          <button type="button" className="btn primary" disabled={busy} onClick={() => applyFilters()}>
            Apply
          </button>
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={() => {
              setAction('')
              setActorUserId('')
              setCaseId('')
              applyFilters({ action: '', actorUserId: '', caseId: '' })
            }}
          >
            Clear
          </button>
        </div>
      </div>

      {err ? <div className="error">{err}</div> : null}

      <div className="casesTableCard auditTableCard">
        <div className="casesTableScroll auditTableScroll">
          <div className="table auditTable">
            <div className="tr th auditTableHead" style={rowGridStyle}>
              {AUDIT_COLUMN_LABELS.map((label, colIndex) => (
                <div key={label} className="thCell">
                  <span className="auditThLabel">{label}</span>
                  {colIndex < AUDIT_COLUMN_LABELS.length - 1 ? (
                    <div
                      className="colResizeHandle"
                      role="separator"
                      aria-orientation="vertical"
                      aria-label={`Resize ${label} column`}
                      onMouseDown={(e) => {
                        e.preventDefault()
                        startResize(
                          colIndex,
                          e.clientX,
                          e.currentTarget.closest('.tr.th') as HTMLElement | null,
                        )
                      }}
                    />
                  ) : null}
                </div>
              ))}
            </div>
            {busy && events.length === 0 ? (
              <div className="tr auditTableRow auditTableRow--message">
                <div className="td muted">Loading…</div>
              </div>
            ) : null}
            {!busy && events.length === 0 ? (
              <div className="tr auditTableRow auditTableRow--message">
                <div className="td muted">No events match these filters.</div>
              </div>
            ) : null}
            {events.map((e) => (
              <div key={e.id} className="tr auditTableRow" style={rowGridStyle}>
                <div className="td auditColWhen muted">{formatTs(e.created_at)}</div>
                <div className="td auditColUser">{actorLabel(e, usersById)}</div>
                <div className="td auditColMatter muted">{matterLabel(e)}</div>
                <div className="td auditColSummary">
                  <div>{e.summary}</div>
                  {e.meta && Object.keys(e.meta).length > 0 ? (
                    <details className="auditMetaDetails">
                      <summary>Details</summary>
                      <pre className="auditMetaPre">{JSON.stringify(e.meta, null, 2)}</pre>
                    </details>
                  ) : null}
                </div>
                <div className="td auditColAction">
                  <code className="auditActionCode">{e.action}</code>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
