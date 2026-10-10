import { useEffect, useState, type ComponentType } from 'react'
import { apiFetch } from '../api'
import type { CommercialModuleBundle, CommercialModuleManifest } from './commercialModuleTypes'
import { loadCommercialModuleBundle } from './loadCommercialModuleBundle'

async function loadExport<K extends keyof CommercialModuleBundle>(
  token: string,
  slotKey: string,
  defaultExport: K,
): Promise<ComponentType<any> | null> {
  const m = await apiFetch<CommercialModuleManifest>('/commercial-modules/active', { token })
  if (!m.enabled || !m.ui?.bundle_url) return null
  if (m.slots && m.slots[slotKey as keyof typeof m.slots] === false) return null
  const bundle = await loadCommercialModuleBundle(m.ui.bundle_url)
  const exportName = (m.ui.exports?.[slotKey] || defaultExport) as keyof CommercialModuleBundle
  return (bundle?.[exportName] as ComponentType<any> | undefined) ?? null
}

export function CommercialAdminIntegrationsSlot({ token }: { token: string }) {
  const [Comp, setComp] = useState<ComponentType<{ token: string; apiFetch: typeof apiFetch }> | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    void loadExport(token, 'admin_integrations', 'AdminIntegrations')
      .then((c) => {
        if (!cancelled) {
          if (!c) setErr('Commercial Integrations UI not attached')
          else setComp(() => c)
        }
      })
      .catch(() => {
        if (!cancelled) setErr('Could not load commercial Integrations UI')
      })
    return () => {
      cancelled = true
    }
  }, [token])

  if (err) return <div className="error">{err}</div>
  if (!Comp) return <div className="muted">Loading integrations…</div>
  return <Comp token={token} apiFetch={apiFetch} />
}

export function CommercialMatterSearchesSlot(props: {
  caseId: string
  token: string
  busy: boolean
  setBusy: (v: boolean) => void
  setActionErr: (v: string | null) => void
  backToDocuments: () => void
  onPlaced: () => void
  onRefresh?: () => void
  onOpenSearchFile?: (fileId: string) => void
}) {
  const [Comp, setComp] = useState<ComponentType<typeof props & { apiFetch: typeof apiFetch }> | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    void loadExport(props.token, 'matter_searches', 'MatterSearchesPanel')
      .then((c) => {
        if (!cancelled) {
          if (!c) setErr('Commercial Searches UI not attached')
          else setComp(() => c)
        }
      })
      .catch(() => {
        if (!cancelled) setErr('Could not load Searches UI')
      })
    return () => {
      cancelled = true
    }
  }, [props.token])

  if (err) {
    return (
      <div className="stack" style={{ padding: 12 }}>
        <div className="error">{err}</div>
        <button type="button" className="btn" onClick={props.backToDocuments}>
          Back
        </button>
      </div>
    )
  }
  if (!Comp) return <div className="muted" style={{ padding: 12 }}>Loading Searches…</div>
  return <Comp {...props} apiFetch={apiFetch} />
}

export function CommercialMatterLandRegistrySlot(props: {
  caseId: string
  token: string
  busy: boolean
  setBusy: (v: boolean) => void
  setActionErr: (v: string | null) => void
  backToDocuments: () => void
  onRefresh?: () => void
  onOpenFile?: (fileId: string) => void
}) {
  const [Comp, setComp] = useState<ComponentType<typeof props & { apiFetch: typeof apiFetch }> | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    void loadExport(props.token, 'matter_land_registry', 'MatterLandRegistryPanel')
      .then((c) => {
        if (!cancelled) {
          if (!c) setErr('Commercial Land Registry UI not attached')
          else setComp(() => c)
        }
      })
      .catch(() => {
        if (!cancelled) setErr('Could not load Land Registry UI')
      })
    return () => {
      cancelled = true
    }
  }, [props.token])

  if (err) {
    return (
      <div className="stack" style={{ padding: 12 }}>
        <div className="error">{err}</div>
        <button type="button" className="btn" onClick={props.backToDocuments}>
          Back
        </button>
      </div>
    )
  }
  if (!Comp) return <div className="muted" style={{ padding: 12 }}>Loading Land Registry…</div>
  return <Comp {...props} apiFetch={apiFetch} />
}

export function CommercialAppDocusignSlot({
  token,
  onSelectCase,
}: {
  token: string
  onSelectCase: (caseId: string) => void
}) {
  const [Comp, setComp] = useState<
    ComponentType<{ token: string; apiFetch: typeof apiFetch; onSelectCase: (caseId: string) => void }> | null
  >(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    void loadExport(token, 'app_docusign', 'DocusignPage')
      .then((c) => {
        if (!cancelled) {
          if (!c) setErr('Commercial DocuSign UI not attached')
          else setComp(() => c)
        }
      })
      .catch(() => {
        if (!cancelled) setErr('Could not load DocuSign UI')
      })
    return () => {
      cancelled = true
    }
  }, [token])

  if (err) return <div className="error">{err}</div>
  if (!Comp) return <div className="muted">Loading DocuSign…</div>
  return <Comp token={token} apiFetch={apiFetch} onSelectCase={onSelectCase} />
}

export function CommercialSendDocusignModalSlot(props: {
  token: string
  caseId: string
  fileId: string
  fileName: string
  caseContacts: unknown[]
  existing?: unknown
  amendFromId?: string | null
  open: boolean
  onClose: () => void
  onSent?: () => void
}) {
  const [Comp, setComp] = useState<ComponentType<typeof props & { apiFetch: typeof apiFetch }> | null>(null)

  useEffect(() => {
    if (!props.open) return
    let cancelled = false
    void loadExport(props.token, 'modal_send_docusign', 'SendDocusignModal')
      .then((c) => {
        if (!cancelled && c) setComp(() => c)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [props.token, props.open])

  if (!props.open) return null
  if (!Comp) return null
  return <Comp {...props} apiFetch={apiFetch} />
}
