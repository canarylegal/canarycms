import type { ReactNode } from 'react'
import { apiUrl } from '../api'
import { CANARY_ICON_32_SRC } from '../AppBrand'

export type PortalBrandingConfig = {
  firm_name: string
  portal_title: string
  portal_logo_url: string | null
  powered_by_label: string
  powered_by_url: string
}

export function PortalBrandHeader({
  config,
  subtitle,
}: {
  config: PortalBrandingConfig
  subtitle?: string | null
}) {
  const logoSrc = config.portal_logo_url ? apiUrl(config.portal_logo_url) : null
  return (
    <header className="portalBrandHeader">
      {logoSrc ? (
        <img className="portalBrandLogo" src={logoSrc} alt="" decoding="async" />
      ) : null}
      <h1 className="portalBrandTitle">{config.portal_title}</h1>
      {subtitle ? <p className="portalBrandSubtitle muted">{subtitle}</p> : null}
    </header>
  )
}

export function PortalPoweredBy({ config }: { config: PortalBrandingConfig }) {
  return (
    <footer className="portalPoweredBy">
      <a
        className="portalPoweredByLink"
        href={config.powered_by_url}
        target="_blank"
        rel="noopener noreferrer"
      >
        <img className="portalPoweredByMark" src={CANARY_ICON_32_SRC} alt="" aria-hidden decoding="async" />
        <span>{config.powered_by_label}</span>
      </a>
    </footer>
  )
}

export function PortalLayout({
  config,
  subtitle,
  wide = true,
  children,
}: {
  config: PortalBrandingConfig
  subtitle?: string | null
  wide?: boolean
  children: ReactNode
}) {
  return (
    <div className="portalShell">
      <div className="portalLayout">
        <div className={`portalCard card${wide ? ' portalCardWide' : ''}`}>
          <PortalBrandHeader config={config} subtitle={subtitle} />
          {children}
        </div>
        <PortalPoweredBy config={config} />
      </div>
    </div>
  )
}
