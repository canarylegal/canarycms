import { useEffect, useState, type ComponentType } from 'react'
import { apiFetch } from '../api'
import type { FirmModuleManifest } from './firmModuleTypes'
import { loadFirmModuleBundle } from './loadFirmModuleBundle'

/**
 * Not-yet-proven slot hosts. They mount only when the firm bundle exports the component
 * and the manifest declares the slot. Pilot does not enable these yet.
 *
 * Pattern matches FirmModulePanelSlot (component held in state, not returned from a hook)
 * so react-hooks/static-components stays quiet.
 */

type CaseSlotProps = {
  caseId: string
  token: string
  apiFetch: typeof apiFetch
}

type AdminSlotProps = {
  token: string
  apiFetch: typeof apiFetch
}

async function resolveExport<P>(
  token: string,
  slotKey: 'matter_actions' | 'portal_section' | 'admin_page',
  defaultExportName: string,
): Promise<ComponentType<P> | null> {
  const m = await apiFetch<FirmModuleManifest>('/firm-modules/active', { token })
  if (!m.enabled || !m.slots?.[slotKey] || !m.ui?.bundle_url) return null
  const bundle = await loadFirmModuleBundle(m.ui.bundle_url)
  const exportName = m.ui.exports?.[slotKey] || defaultExportName
  return (bundle?.[exportName as keyof typeof bundle] as ComponentType<P> | undefined) ?? null
}

export function FirmModuleMatterActionsSlot({ caseId, token }: { caseId: string; token: string }) {
  const [Comp, setComp] = useState<ComponentType<CaseSlotProps> | null>(null)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const found = await resolveExport<CaseSlotProps>(token, 'matter_actions', 'MatterActions')
        if (!cancelled && found) setComp(() => found)
      } catch {
        /* ignore */
      }
    })()
    return () => {
      cancelled = true
    }
  }, [token])

  if (!Comp) return null
  return <Comp caseId={caseId} token={token} apiFetch={apiFetch} />
}

export function FirmModulePortalSectionSlot({ caseId, token }: { caseId: string; token: string }) {
  const [Comp, setComp] = useState<ComponentType<CaseSlotProps> | null>(null)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const found = await resolveExport<CaseSlotProps>(token, 'portal_section', 'PortalSection')
        if (!cancelled && found) setComp(() => found)
      } catch {
        /* ignore */
      }
    })()
    return () => {
      cancelled = true
    }
  }, [token])

  if (!Comp) return null
  return <Comp caseId={caseId} token={token} apiFetch={apiFetch} />
}

export function FirmModuleAdminPageSlot({ token }: { token: string }) {
  const [Comp, setComp] = useState<ComponentType<AdminSlotProps> | null>(null)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const found = await resolveExport<AdminSlotProps>(token, 'admin_page', 'AdminPage')
        if (!cancelled && found) setComp(() => found)
      } catch {
        /* ignore */
      }
    })()
    return () => {
      cancelled = true
    }
  }, [token])

  if (!Comp) return null
  return <Comp token={token} apiFetch={apiFetch} />
}
