import { useState } from 'react'
import { CANARY_LOGO_SRC, CanaryMark } from './AppBrand'

/** Full wordmark from ``public/logo.png``; falls back to icon + text if missing. */
export function AppLogo() {
  const [failed, setFailed] = useState(false)

  if (failed) {
    return (
      <div className="loginBrandLockup" aria-label="Canary">
        <CanaryMark className="appBrandMark appBrandMark--login" size="login" />
        <span className="brand loginBrandName">Canary</span>
      </div>
    )
  }

  return (
    <img
      src={CANARY_LOGO_SRC}
      alt="Canary Case Management"
      className="appLogo appLogo--login"
      onError={() => setFailed(true)}
      decoding="async"
    />
  )
}
