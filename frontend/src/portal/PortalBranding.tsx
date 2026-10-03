import type { CSSProperties, ReactNode } from 'react'
import { useLayoutEffect } from 'react'
import { apiUrl } from '../api'
import { CANARY_ICON_32_SRC } from '../AppBrand'

export type PortalBrandingConfig = {
  firm_name: string
  portal_title: string
  portal_logo_url: string | null
  /** When false, logo is hidden even if uploaded. */
  portal_logo_enabled?: boolean
  /** `#RRGGBB` or null for product default chrome. */
  portal_background_color?: string | null
  /** Public portal background image URL, or null. */
  portal_background_url?: string | null
  /** `#RRGGBB` chrome text on the page background, or null for product default. */
  portal_font_color?: string | null
  /** When false, custom canvas is login-screen only; signed-in uses product default. */
  portal_background_on_signed_in?: boolean
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
  const showLogo = config.portal_logo_enabled !== false
  const logoSrc = showLogo && config.portal_logo_url ? apiUrl(config.portal_logo_url) : null
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

function escapeCssUrl(url: string): string {
  return url.replace(/\\/g, '\\\\').replace(/"/g, '\\"')
}

export function PortalLayout({
  config,
  subtitle,
  wide = true,
  /** When false, ignore firm custom colour/image/font and use product chrome. */
  useCustomCanvas = true,
  headerActions,
  children,
}: {
  config: PortalBrandingConfig
  subtitle?: string | null
  wide?: boolean
  useCustomCanvas?: boolean
  headerActions?: ReactNode
  children: ReactNode
}) {
  const bg = useCustomCanvas ? (config.portal_background_color || '').trim() || null : null
  // Solid colour takes priority. Image only when no custom solid colour is set
  // (otherwise an uploaded photo covers the admin-chosen colour).
  const bgImageUrl =
    useCustomCanvas && !bg ? (config.portal_background_url || '').trim() || null : null
  const bgImageCss = bgImageUrl ? `url("${escapeCssUrl(apiUrl(bgImageUrl))}")` : null
  const ink = useCustomCanvas ? (config.portal_font_color || '').trim() || null : null

  // Narrow (login) title sits on the white card — fall back to dark ink.
  // Wide (signed-in) title sits on the page chrome — fall back to light ink.
  const inkFallback = wide ? '#f8fafc' : '#0f172a'
  const subtitleFallback = wide ? 'rgba(248, 250, 252, 0.78)' : '#64748b'
  const effectiveInk = ink || inkFallback

  // useLayoutEffect: clear/set root canvas vars before paint so login branding
  // does not flash when switching to the signed-in (default chrome) view.
  useLayoutEffect(() => {
    const root = document.documentElement
    root.setAttribute('data-portal-canvas', '1')
    if (bg) root.style.setProperty('--portal-bg', bg)
    else root.style.removeProperty('--portal-bg')
    if (bgImageCss) root.style.setProperty('--portal-bg-image', bgImageCss)
    else root.style.setProperty('--portal-bg-image', 'none')
    root.style.setProperty('--portal-brand-ink', effectiveInk)
    return () => {
      root.removeAttribute('data-portal-canvas')
      root.style.removeProperty('--portal-bg')
      root.style.removeProperty('--portal-bg-image')
      root.style.removeProperty('--portal-brand-ink')
    }
  }, [bg, bgImageCss, effectiveInk])

  const shellVars = {
    ['--portal-bg' as string]: bg || 'var(--local-chrome)',
    ['--portal-bg-image' as string]: bgImageCss || 'none',
    ['--portal-brand-ink' as string]: effectiveInk,
  } as CSSProperties

  // Injected rules beat stylesheet `!important` defaults for html/body/shell.
  const forcedCss = `
html[data-portal-canvas],
html[data-portal-canvas] body,
html[data-portal-canvas] .portalShell {
  background-color: ${bg || 'var(--local-chrome)'} !important;
  background-image: ${bgImageCss || 'none'} !important;
  background-size: cover !important;
  background-position: center center !important;
  background-repeat: no-repeat !important;
  background-attachment: fixed !important;
}
html[data-portal-canvas] .portalBrandTitle {
  color: ${effectiveInk} !important;
}
html[data-portal-canvas] .portalBrandSubtitle,
html[data-portal-canvas] .portalBrandSubtitle.muted {
  color: ${ink ? effectiveInk : subtitleFallback} !important;
  opacity: ${ink ? '0.78' : '1'} !important;
}
html[data-portal-canvas] .portalPoweredByLink {
  color: ${effectiveInk} !important;
  opacity: 0.78;
}
html[data-portal-canvas] .portalPoweredByLink:hover {
  opacity: 0.95;
}
html[data-portal-canvas] .portalSignOutBtn {
  color: ${effectiveInk} !important;
  border-color: color-mix(in srgb, ${effectiveInk} 28%, transparent) !important;
  background: color-mix(in srgb, ${effectiveInk} 12%, transparent) !important;
}
`.trim()

  return (
    <div className="portalShell" style={shellVars}>
      <style>{forcedCss}</style>
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
