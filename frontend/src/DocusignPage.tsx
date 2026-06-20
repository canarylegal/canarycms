import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch } from './api'
import { DOCUSIGN_TABLE_GRID } from './columnGridDefaults'
import { useDialogs } from './DialogProvider'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import type { DocusignMenuRowOut } from './types'

type StatusFilter = '' | 'pending' | 'completed' | 'declined' | 'voided' | 'expired' | 'error'

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: '', label: 'All statuses' },
  { value: 'pending', label: 'Pending' },
  { value: 'completed', label: 'Completed' },
  { value: 'declined', label: 'Declined' },
  { value: 'voided', label: 'Voided' },
  { value: 'expired', label: 'Expired' },
  { value: 'error', label: 'Error' },
]

const DOCUSIGN_COLUMNS = [
  ['sent', 'Sent'],
  ['status', 'Status'],
  ['document', 'Document'],
  ['recipients', 'Recipients'],
  ['client', 'Client'],
  ['reference', 'Reference'],
  ['sentBy', 'Sent by'],
] as const

const rowGridStyle = { gridTemplateColumns: DOCUSIGN_TABLE_GRID }

function formatDate(iso: string | null | undefined) {
  if (!iso) return '—'
  const d = new Date(iso)
  return isNaN(d.getTime()) ? iso : d.toLocaleString()
}

function statusLabel(status: string): string {
  switch (status) {
    case 'pending':
      return 'Awaiting signature'
    case 'completed':
      return 'Completed'
    case 'declined':
      return 'Declined'
    case 'voided':
      return 'Voided'
    case 'expired':
      return 'Expired'
    case 'error':
      return 'Error'
    default:
      return status
  }
}

function documentLabel(row: DocusignMenuRowOut): string {
  const subject = (row.envelope_subject || '').trim()
  const file = (row.source_filename || '').trim()
  if (subject && file && subject !== file) return `${subject} (${file})`
  return subject || file || '—'
}

export function DocusignPage({
  token,
  onSelectCase,
}: {
  token: string
  onSelectCase: (caseId: string) => void
}) {
  const { askConfirm } = useDialogs()
  const [rows, setRows] = useState<DocusignMenuRowOut[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('')
  const [statusFilterOpen, setStatusFilterOpen] = useState(false)
  const [focusRowId, setFocusRowId] = useState<string | null>(null)
  const [ctx, setCtx] = useState<null | { x: number; y: number; row: DocusignMenuRowOut }>(null)
  const ctxRef = useRef<HTMLDivElement | null>(null)

  const load = useCallback(async () => {
    setBusy(true)
    setErr(null)
    try {
      const q = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : ''
      const data = await apiFetch<DocusignMenuRowOut[]>(`/docusign/requests${q}`, { token })
      setRows(data)
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Failed to load DocuSign envelopes')
    } finally {
      setBusy(false)
    }
  }, [token, statusFilter])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (!ctx) return
    function handleMouseDown(e: MouseEvent) {
      const t = e.target as Node
      if (ctxRef.current?.contains(t)) return
      setCtx(null)
    }
    document.addEventListener('mousedown', handleMouseDown)
    return () => document.removeEventListener('mousedown', handleMouseDown)
  }, [ctx])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return rows
    return rows.filter((r) => {
      const hay = [
        r.envelope_subject,
        r.source_filename,
        r.case_number,
        r.client_name,
        r.matter_description,
        r.recipients_summary,
        r.sent_by_display_name,
        r.status,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
      return hay.includes(q)
    })
  }, [rows, search])

  async function syncPending() {
    setBusy(true)
    setErr(null)
    setNotice(null)
    try {
      const res = await apiFetch<{ synced: number }>('/docusign/requests/sync-pending', { token, method: 'POST' })
      setNotice(res.synced > 0 ? `Updated ${res.synced} pending envelope${res.synced === 1 ? '' : 's'}.` : 'No pending envelopes to update.')
      await load()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not sync with DocuSign')
    } finally {
      setBusy(false)
    }
  }

  async function resendLink(row: DocusignMenuRowOut) {
    setBusy(true)
    setErr(null)
    setNotice(null)
    try {
      await apiFetch(`/cases/${row.case_id}/docusign/requests/${row.id}/resend`, { token, method: 'POST' })
      setNotice('Signing link resent.')
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Resend failed')
    } finally {
      setBusy(false)
    }
  }

  async function voidEnvelope(row: DocusignMenuRowOut) {
    const ok = await askConfirm({
      title: 'Void DocuSign envelope',
      message: 'Void this envelope? Recipients will no longer be able to sign.',
      danger: true,
      confirmLabel: 'Void',
    })
    if (!ok) return
    setBusy(true)
    setErr(null)
    setNotice(null)
    try {
      await apiFetch(`/cases/${row.case_id}/docusign/requests/${row.id}/void`, {
        token,
        method: 'POST',
        json: { reason: 'Voided from DocuSign page' },
      })
      setNotice('Envelope voided.')
      await load()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Void failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mainMenuShell mainMenuShell--mainMenu">
      <div className="paneHead" style={{ marginBottom: 12 }}>
        <h1 style={{ margin: 0, fontSize: 22 }}>DocuSign</h1>
      </div>

      {err ? <div className="error">{err}</div> : null}
      {notice ? <div className="notice">{notice}</div> : null}

      <div className={`mainMenuFilterBar${statusFilterOpen ? ' mainMenuFilterBar--dropdownOpen' : ''}`}>
        <div className="row mainMenuFilterRow mainMenuFilterRow--toolbar mainMenuFilterRow--searchRight">
          <div className="mainMenuFilterRowLeft">
            <button type="button" className="btn" disabled={busy} onClick={() => void load()}>
              Refresh
            </button>
            <button type="button" className="btn" disabled={busy} onClick={() => void syncPending()}>
              Sync pending
            </button>
            <SingleSelectDropdown
              hideLabel
              label="Status filter"
              options={STATUS_OPTIONS}
              value={statusFilter}
              onChange={(v) => setStatusFilter(v as StatusFilter)}
              open={statusFilterOpen}
              onOpenChange={setStatusFilterOpen}
            />
          </div>
          <div className="mainMenuFilterRowRight">
            <input
              className="input mainMenuSearchInput"
              type="search"
              placeholder="Search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="Search DocuSign envelopes"
            />
          </div>
        </div>
      </div>

      <div className="card casesTableCard" style={{ padding: 0, overflow: 'hidden' }}>
        {busy && rows.length === 0 ? <div className="muted" style={{ padding: 12 }}>Loading…</div> : null}
        {!busy && filtered.length === 0 ? (
          <div className="muted" style={{ padding: 12 }}>
            {rows.length === 0 ? 'No DocuSign envelopes yet.' : 'No envelopes match your search.'}
          </div>
        ) : (
          <div className="casesTableScroll docusignTableScroll">
            <div className="table">
              <div className="tr th" style={rowGridStyle}>
                {DOCUSIGN_COLUMNS.map(([key, label]) => (
                  <div key={key} className="thCell">
                    <span className="thbtn">{label}</span>
                  </div>
                ))}
              </div>
              {filtered.map((row) => {
                const sent = formatDate(row.created_at)
                const status = statusLabel(row.status)
                const document = documentLabel(row)
                const recipients = row.recipients_summary || '—'
                const client = row.client_name || '—'
                const reference = row.case_number
                const sentBy = row.sent_by_display_name || '—'
                return (
                  <button
                    key={row.id}
                    type="button"
                    className={`tr rowbtn${focusRowId === row.id ? ' active' : ''}`}
                    style={rowGridStyle}
                    onClick={() => setFocusRowId(row.id)}
                    onDoubleClick={() => onSelectCase(row.case_id)}
                    onContextMenu={(e) => {
                      e.preventDefault()
                      setCtx({ x: e.clientX, y: e.clientY, row })
                    }}
                  >
                    <div className="td" title={sent}>
                      {sent}
                    </div>
                    <div className="td" title={row.status_detail ? `${status} — ${row.status_detail}` : status}>
                      {status}
                    </div>
                    <div className="td" title={document}>
                      {document}
                    </div>
                    <div className="td" title={recipients}>
                      {recipients}
                    </div>
                    <div className="td" title={client}>
                      {client}
                    </div>
                    <div className="td mono" title={reference}>
                      {reference}
                    </div>
                    <div className="td" title={sentBy}>
                      {sentBy}
                    </div>
                  </button>
                )
              })}
            </div>
          </div>
        )}
      </div>

      {ctx ? (
        <div
          ref={ctxRef}
          className="docContextMenu"
          style={{ position: 'fixed', top: ctx.y, left: ctx.x, zIndex: 5000 }}
        >
          <div
            className="docContextItem"
            onClick={() => {
              setCtx(null)
              onSelectCase(ctx.row.case_id)
            }}
          >
            Open matter
          </div>
          {ctx.row.status === 'pending' ? (
            <>
              <div
                className="docContextItem"
                onClick={() => {
                  const row = ctx.row
                  setCtx(null)
                  void resendLink(row)
                }}
              >
                Resend signing link
              </div>
              <div
                className="docContextItem"
                onClick={() => {
                  const row = ctx.row
                  setCtx(null)
                  void voidEnvelope(row)
                }}
              >
                Void envelope
              </div>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
