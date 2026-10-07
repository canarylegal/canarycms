import { useEffect, useState, type ComponentType } from 'react'
import { apiFetch } from '../api'
import type { FirmModuleManifest } from './firmModuleTypes'
import { loadFirmModuleBundle } from './loadFirmModuleBundle'

type WidgetProps = {
  token: string
  apiFetch: typeof apiFetch
}

/**
 * Published dashboard-widget slot: loads the firm package DashboardWidget.
 */
export function FirmModuleDashboardSlot({ token }: { token: string }) {
  const [Widget, setWidget] = useState<ComponentType<WidgetProps> | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const m = await apiFetch<FirmModuleManifest>('/firm-modules/active', { token })
        if (cancelled) return
        if (!m.enabled || m.slots?.dashboard_widget === false || !m.ui?.bundle_url) {
          setReady(true)
          return
        }
        const bundle = await loadFirmModuleBundle(m.ui.bundle_url)
        if (cancelled) return
        const exportName = m.ui.exports?.dashboard_widget || 'DashboardWidget'
        const Comp = bundle?.[exportName as keyof typeof bundle] as ComponentType<WidgetProps> | undefined
        if (Comp) setWidget(() => Comp)
      } catch {
        /* slot stays empty */
      } finally {
        if (!cancelled) setReady(true)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [token])

  if (!ready || !Widget) return null
  return <Widget token={token} apiFetch={apiFetch} />
}
