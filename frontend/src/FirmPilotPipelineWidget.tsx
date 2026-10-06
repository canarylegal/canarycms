import { useEffect, useState } from 'react'
import { apiFetch } from './api'

type Pipeline = {
  enabled: boolean
  module_id?: string | null
  label?: string | null
  by_stage?: Record<string, number>
  unstaged?: number
  total?: number
}

/** Main-menu dashboard card for the Phase 3 firm-module pilot. */
export function FirmPilotPipelineWidget({ token }: { token: string }) {
  const [data, setData] = useState<Pipeline | null>(null)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const out = await apiFetch<Pipeline>('/firm-modules/active/pipeline', { token })
        if (!cancelled) setData(out)
      } catch {
        if (!cancelled) setData({ enabled: false })
      }
    })()
    return () => {
      cancelled = true
    }
  }, [token])

  if (!data?.enabled) return null
  const stages = Object.entries(data.by_stage || {})

  return (
    <div className="card" style={{ padding: 14, marginBottom: 12 }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{data.label || 'Purchase pipeline'}</div>
      <div className="muted" style={{ fontSize: 13, marginBottom: 8 }}>
        Firm module dashboard (Phase 3 stand-in) · {data.total ?? 0} matter(s) with module state
      </div>
      <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
        {stages.map(([name, count]) => (
          <div key={name} style={{ minWidth: 88 }}>
            <div style={{ fontSize: 20, fontWeight: 700 }}>{count}</div>
            <div className="muted" style={{ fontSize: 12 }}>
              {name}
            </div>
          </div>
        ))}
        {(data.unstaged ?? 0) > 0 ? (
          <div style={{ minWidth: 88 }}>
            <div style={{ fontSize: 20, fontWeight: 700 }}>{data.unstaged}</div>
            <div className="muted" style={{ fontSize: 12 }}>
              Other
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
