/** Published commercial-module host types (Level C). */

import type { ComponentType } from 'react'
import type { apiFetch } from '../api'

export type CommercialModuleSlots = {
  admin_integrations?: boolean
  matter_searches?: boolean
  matter_land_registry?: boolean
  app_docusign?: boolean
  modal_send_docusign?: boolean
}

export type CommercialModuleUiMeta = {
  bundle_url?: string | null
  exports?: Record<string, string>
}

export type CommercialModuleManifest = {
  enabled: boolean
  module_id?: string | null
  label?: string | null
  products?: string[]
  slots?: CommercialModuleSlots
  ui?: CommercialModuleUiMeta | null
}

export type CommercialModuleBundle = {
  AdminIntegrations?: ComponentType<{
    token: string
    apiFetch: typeof apiFetch
  }>
  MatterSearchesPanel?: ComponentType<{
    caseId: string
    token: string
    apiFetch: typeof apiFetch
    busy: boolean
    setBusy: (v: boolean) => void
    setActionErr: (v: string | null) => void
    backToDocuments: () => void
    onPlaced: () => void
    onRefresh?: () => void
    onOpenSearchFile?: (fileId: string) => void
  }>
  MatterLandRegistryPanel?: ComponentType<{
    caseId: string
    token: string
    apiFetch: typeof apiFetch
    busy: boolean
    setBusy: (v: boolean) => void
    setActionErr: (v: string | null) => void
    backToDocuments: () => void
    onRefresh?: () => void
    onOpenFile?: (fileId: string) => void
  }>
  DocusignPage?: ComponentType<{
    token: string
    apiFetch: typeof apiFetch
    onSelectCase: (caseId: string) => void
  }>
  SendDocusignModal?: ComponentType<{
    token: string
    apiFetch: typeof apiFetch
    caseId: string
    fileId: string
    fileName: string
    caseContacts: unknown[]
    existing?: unknown
    amendFromId?: string | null
    open: boolean
    onClose: () => void
    onSent?: () => void
  }>
}
