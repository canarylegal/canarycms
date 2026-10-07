import { useEffect, useState, type ComponentType } from 'react'
import { apiFetch } from '../api'
import type { FirmModuleManifest } from './firmModuleTypes'
import { loadFirmModuleBundle } from './loadFirmModuleBundle'

/**
 * Not-yet-proven slot hosts. They mount only when the firm bundle exports the component
 * and the manifest declares the slot. Pilot does not enable these yet.
 */

function useFirmExport<P>(
  token: string,
  slotKey: 'matter_actions' | 'portal_section' | 'admin_page',
  defaultExportName: string,
): ComponentType<P> | null {
  const [Comp, setComp] = useState<ComponentType<P> | null>(null)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const m = await apiFetch<FirmModuleManifest>('/firm-modules/active', { token })
        if (cancelled) return
        if (!m.enabled || !m.slots?.[slotKey] || !m.ui?.bundle_url) return
        const bundle = await loadFirmModuleBundle(m.ui.bundle_url)
        if (cancelled) return
        const exportName = m.ui.exports?.[slotKey] || defaultExportName
        const found = bundle?.[exportName as keyof typeof bundle] as ComponentType<P> | undefined
        if (found) setComp(() => found)
      } catch {
        /* ignore */
      }
    })()
    return () => {
      cancelled = true
    }
  }, [token, slotKey, defaultExportName])

  return Comp
}

export function FirmModuleMatterActionsSlot({ caseId, token }: { caseId: string; token: string }) {
  const Comp = useFirmExport<{ caseId: string; token: string; apiFetch: typeof apiFetch }>(
    token,
    'matter_actions',
    'MatterActions',
  )
  if (!Comp) return null
  return <Comp caseId={caseId} token={token} apiFetch={apiFetch} />
}

export function FirmModulePortalSectionSlot({ caseId, token }: { caseId: string; token: string }) {
  const Comp = useFirmExport<{ caseId: string; token: string; apiFetch: typeof apiFetch }>(
    token,
    'portal_section',
    'PortalSection',
  )
  if (!Comp) return null
  return <Comp caseId={caseId} token={token} apiFetch={apiFetch} />
}

export function FirmModuleAdminPageSlot({ token }: { token: string }) {
  const Comp = useFirmExport<{ token: string; apiFetch: typeof apiFetch }>(token, 'admin_page', 'AdminPage')
  if (!Comp) return null
  return <Comp token={token} apiFetch={apiFetch} />
}
