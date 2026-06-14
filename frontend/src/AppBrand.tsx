/** Brand assets in ``frontend/public/`` (served at site root). */
export const CANARY_LOGO_SRC = '/logo.png'
export const CANARY_ICON_32_SRC = '/icons/icon32.png'
export const CANARY_ICON_64_SRC = '/icons/icon64.png'
export const CANARY_ICON_128_SRC = '/icons/icon128.png'

type MarkProps = {
  className?: string
  size?: 'toolbar' | 'login'
}

/** Circular Canary app icon from ``public/icons/``. */
export function CanaryMark({ className, size = 'toolbar' }: MarkProps) {
  return (
    <img
      src={size === 'login' ? CANARY_ICON_128_SRC : CANARY_ICON_32_SRC}
      srcSet={
        size === 'login'
          ? `${CANARY_ICON_128_SRC} 1x, /icons/icon256.png 2x`
          : `${CANARY_ICON_32_SRC} 1x, ${CANARY_ICON_64_SRC} 2x`
      }
      alt=""
      className={className}
      aria-hidden
      width={size === 'login' ? 48 : 28}
      height={size === 'login' ? 48 : 28}
      decoding="async"
    />
  )
}

type Props = {
  onClick?: () => void
  compact?: boolean
}

/** Top-bar brand lockup (mark + wordmark). */
export function AppBrand({ onClick, compact = false }: Props) {
  const inner = (
    <>
      <CanaryMark className="appBrandMark" />
      {compact ? null : <span className="appBrandName">Canary</span>}
    </>
  )

  if (onClick) {
    return (
      <button type="button" className="appBrand appBrand--button" onClick={onClick} aria-label="Canary — Main menu">
        {inner}
      </button>
    )
  }

  return (
    <div className="appBrand" aria-label="Canary">
      {inner}
    </div>
  )
}
