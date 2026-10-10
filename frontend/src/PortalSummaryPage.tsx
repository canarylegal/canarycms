import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch, type ApiError } from './api'
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

const KIND_OPTIONS: { value: '' | PortalSummaryKind; label: string }[] = [
  { value: '', label: 'All kinds' },
  { value: 'quote', label: 'Quote' },
  { value: 'form', label: 'Form' },
  { value: 'canary_sign', label: 'Canary Sign' },
  { value: 'docusign', label: 'DocuSign' },
]

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

function formatWhen(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

export function PortalSummaryPage({ token, onSelectCase }: Props) {
  const [bucket, setBucket] = useState<PortalSummaryBucket>('outstanding')
  const [kind, setKind] = useState<'' | PortalSummaryKind>('')
  const [search, setSearch] = useState('')
  const [rows, setRows] = useState<PortalSummaryRowOut[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

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

  return (
    <div className="mainMenuShell mainMenuShell--mainMenu">
      <div className="paneHead" style={{ marginBottom: 12 }}>
        <h1 style={{ margin: 0, fontSize: 22 }}>Portal</h1>
        <div className="muted" style={{ marginTop: 4 }}>
          Outstanding client actions across matters (quotes, forms, signing). Shared folders are not listed
          here.
        </div>
      </div>

      {err ? <div className="error">{err}</div> : null}

      <div className="mainMenuFilterBar">
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
            <select
              className="input"
              aria-label="Kind filter"
              value={kind}
              disabled={busy}
              onChange={(e) => setKind(e.target.value as '' | PortalSummaryKind)}
            >
              {KIND_OPTIONS.map((o) => (
                <option key={o.value || '__all'} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            <button type="button" className="btn" disabled={busy} onClick={() => void load()}>
              Refresh
            </button>
          </div>
          <div className="mainMenuFilterRowRight">
            <input
              className="input mainMenuSearchInput"
              type="search"
              placeholder="Search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="Search portal actions"
            />
          </div>
        </div>
      </div>

      <div className="card casesTableCard" style={{ padding: 0, overflow: 'hidden' }}>
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
        {filtered.length > 0 ? (
          <table className="casesTable">
            <thead>
              <tr>
                <th>Kind</th>
                <th>Reference</th>
                <th>Client</th>
                <th>Title</th>
                <th>Recipients</th>
                <th>Status</th>
                <th>Sent</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr
                  key={`${r.kind}:${r.id}`}
                  className="casesTableRow"
                  tabIndex={0}
                  onClick={() => onSelectCase(r.case_id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      onSelectCase(r.case_id)
                    }
                  }}
                >
                  <td>
                    <span className={kindBadgeClass(r.kind)}>{kindLabel(r.kind)}</span>
                  </td>
                  <td>{r.case_number || '—'}</td>
                  <td>
                    <div>{r.client_name || '—'}</div>
                    {r.matter_description ? (
                      <div className="muted" style={{ fontSize: 12 }}>
                        {r.matter_description}
                      </div>
                    ) : null}
                  </td>
                  <td>{r.title}</td>
                  <td>{r.contact_or_recipients || '—'}</td>
                  <td>{r.status}</td>
                  <td>{formatWhen(r.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </div>
    </div>
  )
}
