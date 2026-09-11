import { useState, type FormEvent } from 'react'
import { apiFetch, type ApiError } from '../api'
import { AppLogo } from '../AppLogo'
import type { ForgotPasswordResponse } from '../types'

export function ResetPasswordForm({ token, onDone }: { token: string; onDone: () => void }) {
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [ok, setOk] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (busy) return
    setErr(null)
    if (password.length < 12) {
      setErr('Password must be at least 12 characters.')
      return
    }
    if (password !== confirm) {
      setErr('Password and confirmation do not match.')
      return
    }
    setBusy(true)
    try {
      await apiFetch<null>('/auth/reset-password', {
        method: 'POST',
        json: { token, new_password: password },
      })
      setOk(true)
    } catch (e: unknown) {
      setErr((e as ApiError).message ?? 'Could not reset password')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="loginScreen">
      <div className="loginBrandRow">
        <AppLogo />
      </div>
      <div className="card" style={{ maxWidth: 520, margin: '24px auto 0' }}>
        {ok ? (
          <div className="stack" style={{ marginTop: 16, gap: 12 }}>
            <p className="muted" style={{ marginTop: 0 }}>
              Your password has been updated. Sign in with your new password.
            </p>
            <button type="button" className="btn primary" onClick={onDone}>
              Back to sign in
            </button>
          </div>
        ) : (
          <>
            <p className="muted">Choose a new password for your account.</p>
            <form className="stack" style={{ marginTop: 16 }} onSubmit={(e) => void handleSubmit(e)}>
              <label className="field">
                <span>New password</span>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="new-password"
                  autoFocus
                />
              </label>
              <label className="field">
                <span>Confirm new password</span>
                <input
                  type="password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  autoComplete="new-password"
                />
              </label>
              <div className="muted" style={{ fontSize: 13 }}>
                At least 12 characters.
              </div>
              {err ? <div className="error">{err}</div> : null}
              <button type="submit" className="btn primary" disabled={busy}>
                {busy ? 'Saving…' : 'Update password'}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  )
}

export function LoginForm({
  onLogin,
  onPasskeyLogin,
  error,
  onClearError,
}: {
  onLogin: (email: string, password: string, totp?: string) => Promise<'success' | 'needs_2fa' | 'error'>
  onPasskeyLogin: (email: string) => Promise<void>
  error: string | null
  onClearError: () => void
}) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [capsLockOn, setCapsLockOn] = useState(false)
  const [faCode, setFaCode] = useState('')
  const [step, setStep] = useState<'password' | '2fa' | 'forgot'>('password')
  const [busy, setBusy] = useState(false)
  const [forgotNotice, setForgotNotice] = useState<string | null>(null)
  const [forgotErr, setForgotErr] = useState<string | null>(null)

  async function handlePasswordSubmit(e: FormEvent) {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    try {
      const result = await onLogin(email, password)
      if (result === 'needs_2fa') {
        setStep('2fa')
        setFaCode('')
        onClearError()
      }
    } finally {
      setBusy(false)
    }
  }

  async function handle2faSubmit(e: FormEvent) {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    try {
      await onLogin(email, password, faCode.trim() || undefined)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="loginScreen">
      <div className="loginBrandRow">
        <AppLogo />
      </div>
      <div className="card loginCard" style={{ maxWidth: 580, margin: '8px auto 0' }}>
        {step === 'password' ? (
          <>
            <form className="stack loginForm" style={{ marginTop: 16 }} onSubmit={handlePasswordSubmit}>
              <label className="field">
                <span>Email address</span>
                <input
                  value={email}
                  onChange={(e) => {
                    onClearError()
                    setEmail(e.target.value)
                  }}
                  autoComplete="username"
                  autoFocus
                />
              </label>
              <label className="field">
                <span>Password</span>
                <div className="loginPasswordField">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => {
                      onClearError()
                      setPassword(e.target.value)
                    }}
                    onKeyDown={(e) => setCapsLockOn(e.getModifierState('CapsLock'))}
                    onKeyUp={(e) => setCapsLockOn(e.getModifierState('CapsLock'))}
                    onBlur={() => setCapsLockOn(false)}
                    autoComplete="current-password"
                  />
                  <button
                    type="button"
                    className="loginPasswordToggle"
                    tabIndex={0}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                    aria-pressed={showPassword}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => setShowPassword((v) => !v)}
                  >
                    {showPassword ? (
                      <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden>
                        <path
                          fill="currentColor"
                          d="M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46C3.08 8.3 1.78 10.02 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78 3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z"
                        />
                      </svg>
                    ) : (
                      <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden>
                        <path
                          fill="currentColor"
                          d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"
                        />
                      </svg>
                    )}
                  </button>
                </div>
                {capsLockOn ? (
                  <div className="loginCapsWarning" role="status">
                    Caps Lock is on
                  </div>
                ) : null}
              </label>
              {error ? <div className="error">{error}</div> : null}
              <div className="loginActionsRow">
                <button type="submit" className="btn primary" disabled={busy}>
                  {busy ? 'Signing in…' : 'Sign in'}
                </button>
                <button
                  type="button"
                  className="btn loginPasskeyBtn"
                  disabled={busy}
                  onClick={() =>
                    void (async () => {
                      if (busy) return
                      setBusy(true)
                      try {
                        await onPasskeyLogin(email)
                      } finally {
                        setBusy(false)
                      }
                    })()
                  }
                >
                  <svg className="loginPasskeyIcon" width="16" height="16" viewBox="0 0 24 24" aria-hidden>
                    <path
                      fill="currentColor"
                      d="M12.65 10C11.83 7.67 9.61 6 7 6c-3.31 0-6 2.69-6 6s2.69 6 6 6c2.61 0 4.83-1.67 5.65-4H17v4h4v-4h2v-4H12.65zM7 14c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z"
                    />
                  </svg>
                  Sign in with passkey
                </button>
              </div>
            </form>
            <div style={{ marginTop: 12, textAlign: 'center' }}>
              <a
                href="#forgot-password"
                className="loginForgotLink"
                aria-disabled={busy}
                onClick={(e) => {
                  e.preventDefault()
                  if (busy) return
                  onClearError()
                  setForgotNotice(null)
                  setForgotErr(null)
                  setStep('forgot')
                }}
              >
                Forgot password?
              </a>
            </div>
          </>
        ) : step === 'forgot' ? (
          <form
            className="stack"
            style={{ marginTop: 16 }}
            onSubmit={(e) => {
              e.preventDefault()
              if (busy) return
              setBusy(true)
              onClearError()
              setForgotNotice(null)
              setForgotErr(null)
              void (async () => {
                try {
                  const res = await apiFetch<ForgotPasswordResponse>('/auth/forgot-password', {
                    method: 'POST',
                    json: { email: email.trim() },
                  })
                  setForgotNotice(res.message)
                } catch (err: unknown) {
                  setForgotNotice(null)
                  setForgotErr((err as ApiError).message ?? 'Could not request password reset')
                } finally {
                  setBusy(false)
                }
              })()
            }}
          >
            <p className="muted" style={{ marginTop: 0 }}>
              Enter your account e-mail and we will send a reset link if automated e-mail alerts are configured.
            </p>
            <label className="field">
              <span>Email</span>
              <input
                value={email}
                onChange={(e) => {
                  onClearError()
                  setForgotNotice(null)
                  setEmail(e.target.value)
                }}
                autoComplete="username"
                autoFocus
              />
            </label>
            {error ? <div className="error">{error}</div> : null}
            {forgotErr ? <div className="error">{forgotErr}</div> : null}
            {forgotNotice ? <div className="muted">{forgotNotice}</div> : null}
            <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
              <button type="submit" className="btn primary" disabled={busy || !email.trim()}>
                {busy ? 'Sending…' : 'Send reset link'}
              </button>
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => {
                  onClearError()
                  setForgotNotice(null)
                  setForgotErr(null)
                  setStep('password')
                }}
              >
                Back to sign in
              </button>
            </div>
          </form>
        ) : (
          <form className="stack" style={{ marginTop: 16 }} onSubmit={handle2faSubmit}>
            <p className="muted" style={{ marginTop: 0 }}>
              This account uses two-factor authentication. Enter the code from your authenticator app.
            </p>
            <label className="field">
              <span>2FA code</span>
              <input
                value={faCode}
                onChange={(e) => {
                  onClearError()
                  setFaCode(e.target.value)
                }}
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="6-digit code"
                autoFocus
              />
            </label>
            {error ? <div className="error">{error}</div> : null}
            <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
              <button type="submit" className="btn primary" disabled={busy || faCode.trim().length < 6}>
                {busy ? 'Signing in…' : 'Continue'}
              </button>
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => {
                  onClearError()
                  setStep('password')
                  setFaCode('')
                }}
              >
                Back
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}


