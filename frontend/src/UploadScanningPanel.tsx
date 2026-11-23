import { useCallback, useEffect, useState } from 'react'
import { apiFetch } from './api'

type Status = { mode: string; scanner: string; version: string | null; worker_enabled: boolean; counts: Record<string, number> }
type Item = { id: string; filename: string; state: string; reason: string | null }
export function UploadScanningPanel({ token }: { token: string }) {
  const [status, setStatus] = useState<Status | null>(null)
  const [items, setItems] = useState<Item[]>([])
  const [error, setError] = useState<string | null>(null)
  const load = useCallback(async () => {
    try {
      const [s, rows] = await Promise.all([
        apiFetch<Status>('/admin/storage/upload-scanning', { token }),
        apiFetch<Item[]>('/admin/storage/upload-scanning/quarantine', { token }),
      ])
      setStatus(s); setItems(rows); setError(null)
    } catch { setError('Could not load document security status') }
  }, [token])
  useEffect(() => { const timer = window.setTimeout(() => { void load() }, 0); return () => window.clearTimeout(timer) }, [load])
  async function retry(id: string) {
    try {
      await apiFetch(`/admin/storage/upload-scanning/${id}/retry`, { token, method: 'POST' })
      await load()
    } catch { setError('Could not retry the security check') }
  }
  async function discard(item: Item) {
    if (!window.confirm(`Permanently discard the quarantined upload “${item.filename}”?`)) return
    try {
      await apiFetch(`/admin/storage/upload-scanning/${item.id}`, { token, method: 'DELETE' })
      await load()
    } catch { setError('Could not discard this upload. Remove its attachments first if present.') }
  }
  return <section className="card">
    <h3>Document security</h3>
    {error && <p role="alert">{error}</p>}
    {status && <>
      <p>Upload scanning: {status.mode === 'required' ? 'Required' : 'Disabled'}. Configuration is managed by your server administrator.</p>
      {status.mode === 'required' && !status.worker_enabled && <p role="alert">The scanning worker is disabled. New documents will remain quarantined.</p>}
      {status.mode === 'required' && <p>Scanner: {status.scanner === 'ready' ? status.version : 'Unavailable or signatures out of date'}</p>}
      <p>Pending: {status.counts.pending ?? 0} · Blocked: {status.counts.blocked ?? 0} · Incomplete: {status.counts.error ?? 0}</p>
      <button type="button" className="btn" onClick={() => void load()}>Refresh status</button>
      {items.map((item) => <div key={item.id}>
        <span>{item.filename} — {item.state}{item.reason ? ` (${item.reason.replaceAll('_', ' ')})` : ''}</span>
        {status.mode === 'required' && item.state !== 'pending' && <button type="button" className="btn" onClick={() => void retry(item.id)}>Retry scan</button>}
        <button type="button" className="btn" onClick={() => void discard(item)}>Discard upload</button>
      </div>)}
    </>}
  </section>
}
