/** Published firm-module host types (Phase 4). */

import type { ComponentType } from 'react'
import type { apiFetch } from '../api'

export type FirmModuleSlots = {
  matter_panel?: boolean
  dashboard_widget?: boolean
  matter_actions?: boolean
  portal_section?: boolean
  admin_page?: boolean
}

export type FirmModuleUiMeta = {
  bundle_url?: string | null
  exports?: Record<string, string>
}

export type FirmModuleManifest = {
  enabled: boolean
  module_id?: string | null
  label?: string | null
  panel_label?: string | null
  slots?: FirmModuleSlots
  ui?: FirmModuleUiMeta | null
  attr_fields?: { key: string; label: string; type?: string }[]
}

export type FirmModuleBundle = {
  MatterPanel?: ComponentType<{
    caseId: string
    token: string
    onBack: () => void
    apiFetch: typeof apiFetch
  }>
  DashboardWidget?: ComponentType<{
    token: string
    apiFetch: typeof apiFetch
  }>
  MatterActions?: ComponentType<{
    caseId: string
    token: string
    apiFetch: typeof apiFetch
  }>
  PortalSection?: ComponentType<{
    caseId: string
    token: string
    apiFetch: typeof apiFetch
  }>
  AdminPage?: ComponentType<{
    token: string
    apiFetch: typeof apiFetch
  }>
}
