import { useEffect, useState, type ComponentType } from 'react'
import { apiFetch } from '../api'
import type { FirmModuleManifest } from './firmModuleTypes'
import { loadFirmModuleBundle } from './loadFirmModuleBundle'

type PanelProps = {
  caseId: string
  token: string
  onBack: () => void
  apiFetch: typeof apiFetch
}

/**
 * Published matter-panel slot: loads the firm package UI bundle and mounts MatterPanel.
 */
export function FirmModulePanelSlot({
  caseId,
  token,
  onBack,
}: {
  caseId: string
  token: string
  onBack: () => void
}) {
  const [Panel, setPanel] = useState<ComponentType<PanelProps> | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const m = await apiFetch<FirmModuleManifest>('/firm-modules/active', { token })
        if (cancelled) return
        if (!m.enabled || !m.ui?.bundle_url) {
          setErr('No firm module UI attached')
          return
        }
        const bundle = await loadFirmModuleBundle(m.ui.bundle_url)
        if (cancelled) return
        const exportName = m.ui.exports?.matter_panel || 'MatterPanel'
        const Comp = bundle?.[exportName as keyof typeof bundle] as ComponentType<PanelProps> | undefined
        if (!Comp) {
          setErr('Firm UI bundle missing MatterPanel export')
          return
        }
        setPanel(() => Comp)
      } catch {
        if (!cancelled) setErr('Could not load firm module UI')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [token])

  if (err) {
    return (
      <div className="stack" style={{ padding: 12 }}>
        <div className="error">{err}</div>
        <button type="button" className="btn" onClick={onBack}>
          Back
        </button>
      </div>
    )
  }
  if (!Panel) {
    return <div className="muted" style={{ padding: 12 }}>Loading firm module…</div>
  }
  return <Panel caseId={caseId} token={token} onBack={onBack} apiFetch={apiFetch} />
}
