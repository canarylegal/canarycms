import type { CSSProperties, ReactNode } from 'react'
import { useEffect } from 'react'
import { apiUrl } from '../api'
import { CANARY_ICON_32_SRC } from '../AppBrand'

export type PortalBrandingConfig = {
  firm_name: string
  portal_title: string
  portal_logo_url: string | null
  /** `#RRGGBB` or null for product default chrome. */
  portal_background_color?: string | null
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
  headerActions,
  children,
}: {
  config: PortalBrandingConfig
  subtitle?: string | null
  wide?: boolean
  headerActions?: ReactNode
  children: ReactNode
}) {
  const bg = (config.portal_background_color || '').trim() || null

  useEffect(() => {
    const root = document.documentElement
    if (bg) {
      root.style.setProperty('--portal-bg', bg)
    } else {
      root.style.removeProperty('--portal-bg')
    }
    return () => {
      root.style.removeProperty('--portal-bg')
    }
  }, [bg])

  const shellStyle = (bg ? ({ ['--portal-bg' as string]: bg } as CSSProperties) : undefined)

  return (
    <div className="portalShell" style={shellStyle}>
      <div className={`portalLayout${wide ? ' portalLayout--wide' : ' portalLayout--narrow'}`}>
        {wide ? (
          <>
            <div className="portalWideTop">
              <PortalBrandHeader config={config} subtitle={subtitle} />
              {headerActions ? <div className="portalWideTopActions">{headerActions}</div> : null}
            </div>
            <div className="portalCard card portalCardWide">{children}</div>
          </>
        ) : (
          <div className="portalCard card">
            <PortalBrandHeader config={config} subtitle={subtitle} />
            {children}
          </div>
        )}
      </div>
      <PortalPoweredBy config={config} />
    </div>
  )
}
