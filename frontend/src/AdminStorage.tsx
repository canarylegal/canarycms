import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from './api'
import type { ApiError } from './api'
import type { AdminStorageOut } from './types'

const DEPLOYMENT_COLORS: Record<string, string> = {
  files: '#3b82f6',
  application: '#6366f1',
  database: '#8b5cf6',
  calendars: '#10b981',
  docker_images: '#0ea5e9',
  docker_dangling: '#64748b',
  docker_build_cache: '#475569',
  unused: 'rgba(148, 163, 184, 0.35)',
}

function componentColor(key: string): string {
  if (DEPLOYMENT_COLORS[key]) return DEPLOYMENT_COLORS[key]!
  if (key.startsWith('volume_')) return '#8b5cf6'
  if (key.startsWith('container_')) return '#f59e0b'
  if (key === 'docker_dangling') return '#64748b'
  if (key === 'docker_build_cache') return '#475569'
  return '#94a3b8'
}

const FILE_CATEGORY_COLORS: Record<string, string> = {
  case_document: '#60a5fa',
  precedent: '#a78bfa',
  firm_letterhead: '#fbbf24',
  system: '#94a3b8',
}

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}

function bytesToGbInput(bytes: number | null | undefined): string {
  if (bytes == null || bytes <= 0) return ''
  return String(Math.round((bytes / 1024 ** 3) * 100) / 100)
}

function gbInputToBytes(raw: string): number | null {
  const trimmed = raw.trim()
  if (!trimmed) return null
  const gb = parseFloat(trimmed)
  if (Number.isNaN(gb) || gb <= 0) return null
  return Math.round(gb * 1024 ** 3)
}

function buildConicGradient(
  slices: { key: string; bytes: number }[],
  totalForPie: number,
  colors: Record<string, string>,
): string {
  if (totalForPie <= 0 || slices.length === 0) {
    return `conic-gradient(${DEPLOYMENT_COLORS.unused} 0deg 360deg)`
  }
  let cursor = 0
  const stops: string[] = []
  for (const slice of slices) {
    if (slice.bytes <= 0) continue
    const pct = slice.bytes / totalForPie
    const start = cursor * 360
    cursor += pct
    const end = cursor * 360
    const color = colors[slice.key] ?? componentColor(slice.key)
    stops.push(`${color} ${start.toFixed(2)}deg ${end.toFixed(2)}deg`)
  }
  if (stops.length === 0) {
    return `conic-gradient(${DEPLOYMENT_COLORS.unused} 0deg 360deg)`
  }
  return `conic-gradient(${stops.join(', ')})`
}

export function AdminStorage({ token }: { token: string }) {
  const [data, setData] = useState<AdminStorageOut | null>(null)
  const [limitGb, setLimitGb] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [ok, setOk] = useState<string | null>(null)

  const load = useCallback(async () => {
    setErr(null)
    try {
      const out = await apiFetch<AdminStorageOut>('/admin/storage', { token })
      setData(out)
      setLimitGb(bytesToGbInput(out.storage_limit_bytes))
    } catch (e) {
      setData(null)
      setErr((e as ApiError).message ?? 'Failed to load storage usage')
    }
  }, [token])

  useEffect(() => {
    void load()
  }, [load])

  const pie = useMemo(() => {
    if (!data) return null
    const used = data.deployment_total_bytes
    const limit = data.storage_limit_bytes
    const capacity = limit && limit > used ? limit : used
    const unused = limit && limit > used ? limit - used : 0
    const componentSlices = data.deployment_components
      .filter((c) => c.detected && c.bytes_used > 0)
      .map((c) => ({ key: c.key, bytes: c.bytes_used, label: c.label }))
    const slices =
      unused > 0
        ? [...componentSlices, { key: 'unused', bytes: unused, label: 'Unused quota' }]
        : componentSlices
    const totalForPie = capacity > 0 ? capacity : used
    return {
      gradient: buildConicGradient(slices, totalForPie, DEPLOYMENT_COLORS),
      slices: componentSlices,
      unused,
      used,
      capacity: limit ?? null,
    }
  }, [data])

  const fileOverhead = data ? Math.max(0, data.files_on_disk_bytes - data.tracked_total_bytes) : 0

  async function saveLimit() {
    const bytes = gbInputToBytes(limitGb)
    if (limitGb.trim() && bytes == null) {
      setErr('Enter a valid storage limit in GB, or leave blank for no limit.')
      return
    }
    setBusy(true)
    setErr(null)
    setOk(null)
    try {
      const out = await apiFetch<AdminStorageOut>('/admin/storage/settings', {
        token,
        method: 'PATCH',
        json: { storage_limit_bytes: bytes },
      })
      setData(out)
      setLimitGb(bytesToGbInput(out.storage_limit_bytes))
      setOk(bytes ? 'Storage limit saved.' : 'Storage limit cleared.')
    } catch (e) {
      setErr((e as ApiError).message ?? 'Failed to save storage limit')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card adminStorageCard">
      <h3 style={{ marginTop: 0 }}>Storage</h3>
      <p className="muted" style={{ lineHeight: 1.55 }}>
        Full on-disk footprint of this Canary deployment: bind-mounted project directory, all Compose Docker volumes,
        container images, per-container writable layers (including ONLYOFFICE cache), orphaned build layers from past
        rebuilds, and Docker build cache on this host. Refresh may take a minute while directories and Docker are
        scanned.
      </p>

      {err ? <div className="error">{err}</div> : null}
      {ok ? <div className="muted">{ok}</div> : null}

      {data && pie ? (
        <>
          <div className="adminStorageLayout">
            <div className="adminStoragePieWrap">
              <div className="adminStoragePie" style={{ background: pie.gradient }} aria-hidden />
              <div className="adminStoragePieCenter">
                <div className="adminStoragePieCenterValue">{formatBytes(pie.used)}</div>
                <div className="adminStoragePieCenterLabel">deployment total</div>
                {pie.capacity ? (
                  <div className="adminStoragePieCenterSub muted">of {formatBytes(pie.capacity)} limit</div>
                ) : null}
              </div>
            </div>

            <div className="adminStorageLegend">
              {pie.slices.map((slice) => (
                <div key={slice.key} className="adminStorageLegendRow">
                  <span
                    className="adminStorageLegendSwatch"
                    style={{ background: componentColor(slice.key) }}
                    aria-hidden
                  />
                  <span className="adminStorageLegendLabel">{slice.label}</span>
                  <span className="adminStorageLegendValue muted">{formatBytes(slice.bytes)}</span>
                </div>
              ))}
              {pie.unused > 0 ? (
                <div className="adminStorageLegendRow">
                  <span className="adminStorageLegendSwatch" style={{ background: DEPLOYMENT_COLORS.unused }} aria-hidden />
                  <span className="adminStorageLegendLabel">Unused quota</span>
                  <span className="adminStorageLegendValue muted">{formatBytes(pie.unused)}</span>
                </div>
              ) : null}
              <div className="adminStorageLegendTotal">
                <span>In active use</span>
                <strong>{formatBytes(data.deployment_active_bytes)}</strong>
              </div>
              {data.deployment_artifacts_bytes > 0 ? (
                <div className="adminStorageLegendTotal">
                  <span>Build artifacts (reclaimable)</span>
                  <strong>{formatBytes(data.deployment_artifacts_bytes)}</strong>
                </div>
              ) : null}
              <div className="adminStorageLegendTotal">
                <span>Everything (grand total)</span>
                <strong>{formatBytes(data.deployment_total_bytes)}</strong>
              </div>
              {data.host_disk_detected && data.host_disk_total_bytes != null ? (
                <p className="muted adminStorageDiskNote">
                  Files mount filesystem: {formatBytes(data.host_disk_free_bytes ?? 0)} free of{' '}
                  {formatBytes(data.host_disk_total_bytes)} total (whole disk/partition, not only Canary).
                </p>
              ) : null}
              {data.measurement_note ? (
                <p className="muted adminStorageDiskNote">{data.measurement_note}</p>
              ) : null}
              {data.database_logical_bytes != null &&
              data.database_bytes != null &&
              data.database_bytes > data.database_logical_bytes ? (
                <p className="muted adminStorageDiskNote">
                  PostgreSQL volume on disk ({formatBytes(data.database_bytes)}) is larger than the logical database
                  size ({formatBytes(data.database_logical_bytes)}).
                </p>
              ) : null}
              {!data.docker_detected ? (
                <p className="muted adminStorageDiskNote">
                  Docker could not be queried — mount <code>/var/run/docker.sock</code> into the backend for complete
                  totals.
                </p>
              ) : null}
            </div>
          </div>

          {data.categories.some((c) => c.bytes_used > 0) ? (
            <div className="adminStorageFileBreakdown">
              <div className="adminStorageFileBreakdownTitle">Stored files breakdown (database records)</div>
              <p className="muted adminStorageFileBreakdownIntro">
                On disk: {formatBytes(data.files_on_disk_bytes)}
                {fileOverhead > 0
                  ? ` — includes ${formatBytes(fileOverhead)} not attributed to individual file records (for example ONLYOFFICE backups).`
                  : '.'}
              </p>
              <div className="adminStorageLegend">
                {data.categories
                  .filter((c) => c.bytes_used > 0)
                  .map((c) => (
                    <div key={c.category} className="adminStorageLegendRow adminStorageLegendRow--nested">
                      <span
                        className="adminStorageLegendSwatch"
                        style={{ background: FILE_CATEGORY_COLORS[c.category] ?? '#94a3b8' }}
                        aria-hidden
                      />
                      <span className="adminStorageLegendLabel">{c.label}</span>
                      <span className="adminStorageLegendValue muted">{formatBytes(c.bytes_used)}</span>
                    </div>
                  ))}
              </div>
            </div>
          ) : null}
        </>
      ) : (
        <p className="muted">{data ? 'No storage data yet.' : 'Loading…'}</p>
      )}

      <div className="adminStorageLimitForm">
        <label className="field" style={{ maxWidth: 280 }}>
          <span>Storage limit (GB)</span>
          <input
            type="text"
            inputMode="decimal"
            placeholder="No limit"
            value={limitGb}
            onChange={(e) => setLimitGb(e.target.value)}
          />
        </label>
        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
          <button type="button" className="btn primary" disabled={busy} onClick={() => void saveLimit()}>
            {busy ? 'Saving…' : 'Save limit'}
          </button>
          <button type="button" className="btn" disabled={busy} onClick={() => void load()}>
            Refresh
          </button>
        </div>
      </div>
    </div>
  )
}
