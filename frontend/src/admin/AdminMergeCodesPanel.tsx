import { useEffect, useMemo, useState } from 'react'
import { apiFetch, apiUrl, applyAuthHeaders } from '../api'
import type { ApiError } from '../api'
import type { MergeCodeCatalogImportResult, MergeCodeCatalogOut } from '../types'

type Props = {
  token: string
  onError: (message: string | null) => void
}

export function AdminMergeCodesPanel({ token, onError }: Props) {
  const [mergePanelOpen, setMergePanelOpen] = useState(false)
  const [mergeRows, setMergeRows] = useState<MergeCodeCatalogOut[]>([])
  const [mergeLoading, setMergeLoading] = useState(false)
  const [mergeSaving, setMergeSaving] = useState(false)
  const [mergeFilter, setMergeFilter] = useState('')
  const [mergeImportKey, setMergeImportKey] = useState(0)
  const [mergeMsg, setMergeMsg] = useState<string | null>(null)

  const mergeFiltered = useMemo(() => {
    const q = mergeFilter.trim().toLowerCase()
    if (!q) return mergeRows
    return mergeRows.filter(
      (r) => r.code.toLowerCase().includes(q) || r.description.toLowerCase().includes(q),
    )
  }, [mergeRows, mergeFilter])

  async function loadMergeCatalog() {
    setMergeLoading(true)
    setMergeMsg(null)
    try {
      const rows = await apiFetch<MergeCodeCatalogOut[]>('/admin/merge-codes', { token })
      setMergeRows(rows)
    } catch (e2: unknown) {
      onError((e2 as ApiError)?.message ?? 'Could not load merge codes')
    } finally {
      setMergeLoading(false)
    }
  }

  async function saveMergeCatalog() {
    setMergeSaving(true)
    setMergeMsg(null)
    onError(null)
    try {
      const rows = await apiFetch<MergeCodeCatalogOut[]>('/admin/merge-codes', {
        token,
        method: 'PATCH',
        json: { items: mergeRows.map((r) => ({ code: r.code, description: r.description })) },
      })
      setMergeRows(rows)
      setMergeMsg(`Saved ${rows.length} codes.`)
    } catch (e2: unknown) {
      onError((e2 as ApiError)?.message ?? 'Save merge codes failed')
    } finally {
      setMergeSaving(false)
    }
  }

  async function exportMergeCatalog() {
    setMergeMsg(null)
    try {
      const auth = String(token ?? '').trim()
      if (!auth) throw new Error('You are not signed in. Refresh the page and log in again.')
      const xh = new Headers()
      applyAuthHeaders(xh, auth)
      const res = await fetch(apiUrl('/admin/merge-codes/export.xlsx'), { headers: xh })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        const msg = typeof body?.detail === 'string' ? body.detail : `Export failed (${res.status})`
        throw new Error(msg)
      }
      const blob = await res.blob()
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = 'canary-merge-codes.xlsx'
      a.click()
      URL.revokeObjectURL(a.href)
      setMergeMsg('Download started.')
    } catch (e2: unknown) {
      onError((e2 as Error)?.message ?? 'Export failed')
    }
  }

  async function importMergeCatalogFile(f: File) {
    setMergeSaving(true)
    setMergeMsg(null)
    onError(null)
    try {
      const fd = new FormData()
      fd.append('upload', f)
      const body = await apiFetch<MergeCodeCatalogImportResult>('/admin/merge-codes/import', {
        token,
        method: 'POST',
        body: fd,
      })
      setMergeMsg(
        `Import: updated ${body.updated ?? 0} row(s); ${body.skipped_unknown ?? 0} unknown code(s) skipped.`,
      )
      await loadMergeCatalog()
      setMergeImportKey((k) => k + 1)
    } catch (e2: unknown) {
      onError((e2 as Error)?.message ?? 'Import failed')
    } finally {
      setMergeSaving(false)
    }
  }

  useEffect(() => {
    if (mergePanelOpen) void loadMergeCatalog()
  }, [mergePanelOpen, token])

  return (
    <div className="card" style={{ padding: 12 }}>
      <div
        className="row"
        style={{
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          marginBottom: mergePanelOpen ? 8 : 0,
          gap: 12,
        }}
      >
        <div className="stack" style={{ gap: 10, flex: 1, minWidth: 0 }}>
          <span className="muted" style={{ fontSize: 13 }}>
            Merge codes — stored in the database; edit descriptions here or round-trip via Excel. Codes themselves
            come from Canary releases (sync on startup).
          </span>
          <div
            style={{
              fontSize: 13,
              padding: '10px 12px',
              border: '1px solid var(--border)',
              borderRadius: 6,
              background: 'var(--panel)',
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: 6 }}>Formatting modifiers</div>
            <p className="muted" style={{ margin: '0 0 8px', fontSize: 12 }}>
              Optional prefix before a code in Word templates. Plain <code>[CODE]</code> merges without extra
              formatting.
            </p>
            <table
              className="allow-select"
              style={{ width: '100%', maxWidth: 420, borderCollapse: 'collapse', fontSize: 12 }}
            >
              <thead>
                <tr>
                  <th
                    style={{
                      textAlign: 'left',
                      padding: '4px 8px 4px 0',
                      borderBottom: '1px solid var(--border)',
                      fontWeight: 600,
                      width: '28%',
                    }}
                  >
                    Modifier
                  </th>
                  <th
                    style={{
                      textAlign: 'left',
                      padding: '4px 0',
                      borderBottom: '1px solid var(--border)',
                      fontWeight: 600,
                    }}
                  >
                    Effect on merged value
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style={{ padding: '4px 8px 4px 0', fontFamily: 'monospace', verticalAlign: 'top' }}>
                    <code>b:</code>
                  </td>
                  <td style={{ padding: '4px 0', verticalAlign: 'top' }}>Bold</td>
                </tr>
                <tr>
                  <td style={{ padding: '4px 8px 4px 0', fontFamily: 'monospace', verticalAlign: 'top' }}>
                    <code>i:</code>
                  </td>
                  <td style={{ padding: '4px 0', verticalAlign: 'top' }}>Italic</td>
                </tr>
                <tr>
                  <td style={{ padding: '4px 8px 4px 0', fontFamily: 'monospace', verticalAlign: 'top' }}>
                    <code>u:</code>
                  </td>
                  <td style={{ padding: '4px 0', verticalAlign: 'top' }}>Underline</td>
                </tr>
              </tbody>
            </table>
            <p className="muted" style={{ margin: '8px 0 0', fontSize: 12 }}>
              Combine modifiers in any order, e.g. <code>[bi:LAST_NAME]</code> (bold + italic) or{' '}
              <code>[biu:MATTER_DESCRIPTION]</code> (all three). Example:{' '}
              <code>Re: [b:MATTER_DESCRIPTION]</code>
            </p>
          </div>
        </div>
        <button
          type="button"
          className="btn"
          style={{ fontSize: 12, flexShrink: 0 }}
          onClick={() => {
            setMergePanelOpen((v) => !v)
            if (mergePanelOpen) setMergeMsg(null)
          }}
        >
          {mergePanelOpen ? 'Hide' : 'View/Edit'}
        </button>
      </div>
      {mergePanelOpen ? (
        <div className="stack" style={{ gap: 10 }}>
          <div className="mergeCatalogToolbar">
            <span className="mergeCatalogToolbarLabel muted">Filter</span>
            <div className="mergeCatalogToolbarControls">
              <input
                className="mergeCatalogToolbarInput"
                value={mergeFilter}
                onChange={(e) => setMergeFilter(e.target.value)}
                placeholder="Code or description…"
                disabled={mergeLoading || mergeSaving}
              />
              <div className="mergeCatalogToolbarActions">
                <button
                  type="button"
                  className="btn primary"
                  disabled={mergeLoading || mergeSaving || mergeRows.length === 0}
                  onClick={() => void saveMergeCatalog()}
                >
                  Save descriptions
                </button>
                <button
                  type="button"
                  className="btn"
                  disabled={mergeLoading || mergeSaving}
                  onClick={() => void exportMergeCatalog()}
                >
                  Export Excel
                </button>
                <label className="btn" style={{ cursor: mergeSaving ? 'not-allowed' : 'pointer' }}>
                  Import Excel…
                  <input
                    key={mergeImportKey}
                    type="file"
                    accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    disabled={mergeSaving}
                    style={{ display: 'none' }}
                    onChange={(ev) => {
                      const f = ev.target.files?.[0]
                      ev.target.value = ''
                      if (f) void importMergeCatalogFile(f)
                    }}
                  />
                </label>
                <button
                  type="button"
                  className="btn"
                  disabled={mergeLoading}
                  onClick={() => void loadMergeCatalog()}
                >
                  Reload
                </button>
              </div>
            </div>
          </div>
          {mergeMsg ? <div className="muted" style={{ fontSize: 13 }}>{mergeMsg}</div> : null}
          {mergeLoading ? (
            <div className="muted">Loading merge codes…</div>
          ) : (
            <div
              style={{
                maxHeight: 420,
                overflow: 'auto',
                border: '1px solid var(--border)',
                borderRadius: 6,
                background: 'var(--panel)',
              }}
            >
              <table
                className="allow-select"
                style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}
              >
                <thead style={{ position: 'sticky', top: 0, background: 'var(--panel2)', zIndex: 1 }}>
                  <tr>
                    <th
                      style={{
                        textAlign: 'left',
                        padding: '8px',
                        borderBottom: '1px solid var(--border)',
                        width: '22%',
                        color: 'var(--text)',
                        fontWeight: 600,
                      }}
                    >
                      Code
                    </th>
                    <th
                      style={{
                        textAlign: 'left',
                        padding: '8px',
                        borderBottom: '1px solid var(--border)',
                        color: 'var(--text)',
                        fontWeight: 600,
                      }}
                    >
                      Description (editable)
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {mergeFiltered.map((r) => (
                    <tr key={r.code}>
                      <td
                        style={{
                          padding: '6px 8px',
                          fontFamily: 'monospace',
                          color: 'var(--text)',
                          verticalAlign: 'top',
                          borderBottom: '1px solid var(--border)',
                        }}
                      >
                        {r.code}
                      </td>
                      <td style={{ padding: '4px 8px', borderBottom: '1px solid var(--border)' }}>
                        <textarea
                          value={r.description}
                          rows={2}
                          disabled={mergeSaving}
                          style={{ width: '100%', resize: 'vertical', fontFamily: 'inherit', fontSize: 13 }}
                          onChange={(e) => {
                            const v = e.target.value
                            setMergeRows((prev) => prev.map((x) => (x.code === r.code ? { ...x, description: v } : x)))
                          }}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {mergeFiltered.length === 0 && mergeRows.length > 0 ? (
                <div className="muted" style={{ padding: 12 }}>
                  No rows match the filter.
                </div>
              ) : null}
              {!mergeLoading && mergeRows.length === 0 ? (
                <div className="muted" style={{ padding: 12 }}>
                  No catalog rows yet — ensure the backend has run a migration and restarted so merge codes sync from the
                  server defaults.
                </div>
              ) : null}
            </div>
          )}
        </div>
      ) : null}
    </div>
  )
}
