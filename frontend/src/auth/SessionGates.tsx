import { useState } from 'react'
import { UserSettingsPage } from '../UserSettingsPage'
import { userNeedsSecondFactorSetup } from './sessionFlags'
import type { UserPublic } from '../types'

export function PasswordChangeSessionGate({
  token,
  me,
  onLogout,
  refreshMe,
  applySessionToken,
}: {
  token: string
  me: UserPublic
  onLogout: () => void
  refreshMe: () => Promise<void>
  applySessionToken: (t: string) => void
}) {
  const days = me.password_rotation_days
  return (
    <div className="appShell">
      <header className="topbar">
        <div className="topbarMain">
          <nav className="topNav" aria-label="Password update required">
            <span className="muted" style={{ padding: '6px 10px' }}>
              Password update required
            </span>
          </nav>
        </div>
        <div className="topbarRight">
          <div className="muted">{me.email}</div>
          <button type="button" className="btn" onClick={onLogout}>
            Sign out
          </button>
        </div>
      </header>
      <main className="main main--mainMenu">
        <div className="stack" style={{ padding: 16, maxWidth: 720, margin: '0 auto' }}>
          <div className="error" role="alert">
            <p style={{ marginTop: 0 }}>
              Your organisation requires you to update your password
              {days ? ` every ${days} days` : ''}. Choose a new password below to continue using Canary.
            </p>
          </div>
          <UserSettingsPage
            token={token}
            refreshMe={refreshMe}
            applySessionToken={applySessionToken}
            passwordChangeRequiredOnly
          />
        </div>
      </main>
    </div>
  )
}

export function SecondFactorSessionGate({
  token,
  me,
  onLogout,
  onPasskeyLogin,
  refreshMe,
  applySessionToken,
  loginError,
  onClearLoginError,
}: {
  token: string
  me: UserPublic
  onLogout: () => void
  onPasskeyLogin: (email: string) => Promise<void>
  refreshMe: () => Promise<void>
  applySessionToken: (t: string) => void
  loginError: string | null
  onClearLoginError: () => void
}) {
  const needsSetup = userNeedsSecondFactorSetup(me)
  const [busy, setBusy] = useState(false)
  return (
    <div className="appShell">
      <header className="topbar">
        <div className="topbarMain">
          <nav className="topNav" aria-label="Verify sign-in">
            <span className="muted" style={{ padding: '6px 10px' }}>
              {needsSetup ? 'Security setup required' : 'Verify sign-in'}
            </span>
          </nav>
        </div>
        <div className="topbarRight">
          <div className="muted">{me.email}</div>
          <button type="button" className="btn" onClick={onLogout}>
            Sign out
          </button>
        </div>
      </header>
      <main className="main main--mainMenu">
        <div className="stack" style={{ padding: 16, maxWidth: 720, margin: '0 auto' }}>
          {!needsSetup ? (
            <div className="error" role="alert">
              <p style={{ marginTop: 0 }}>
                Your organisation requires a verified second factor at sign-in. Use{' '}
                <strong>Sign in with passkey</strong>, or sign out and sign in with your password — you will be prompted
                for your authenticator code after your password.
              </p>
            </div>
          ) : null}
          <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn primary"
              disabled={busy}
              onClick={() =>
                void (async () => {
                  if (busy) return
                  onClearLoginError()
                  setBusy(true)
                  try {
                    await onPasskeyLogin(me.email)
                  } finally {
                    setBusy(false)
                  }
                })()
              }
            >
              {busy ? 'Working…' : 'Sign in with passkey'}
            </button>
          </div>
          {loginError ? <div className="error">{loginError}</div> : null}
          {needsSetup ? (
            <UserSettingsPage
              token={token}
              refreshMe={refreshMe}
              applySessionToken={applySessionToken}
              securitySetupOnly
            />
          ) : null}
        </div>
      </main>
    </div>
  )
}

/** Main menu cases table — default column widths live in ``userUiPreferences``; grid uses pixel widths when resized. */

/** Contacts page table — default column widths live in ``userUiPreferences``. */


