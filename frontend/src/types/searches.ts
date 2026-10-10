import type { CaseraIntegrationSettingsOut } from './casera'

export type SearchProviderOptionOut = {
  id: string
  label: string
}

export type SearchIntegrationSettingsOut = {
  provider: string
  available_providers: SearchProviderOptionOut[]
  casera?: CaseraIntegrationSettingsOut | null
}
