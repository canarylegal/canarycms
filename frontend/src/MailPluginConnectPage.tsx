import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  startAuthentication,
  type PublicKeyCredentialRequestOptionsJSON,
} from '@simplewebauthn/browser'
import { apiFetch, type ApiError } from './api'
import { AppLogo } from './AppLogo'
import type { TokenResponse, UserPublic } from './types'

type MailPluginClient = 'thunderbird' | 'outlook'

type ConnectParams = {
  client: MailPluginClient
  state: string
  redirectUri: string
}

const CLIENT_LABEL: Record<MailPluginClient, string> = {
  thunderbird: 'Thunderbird',
  outlook: 'Outlook',
}

function parseConnectParams(): ConnectParams | { error: string } {
  const params = new URLSearchParams(window.location.search)
  const client = params.get('client')?.trim().toLowerCase()
  const state = params.get('state')?.trim() ?? ''
  const redirectUri = params.get('redirect_uri')?.trim() ?? ''
  if (client !== 'thunderbird' && client !== 'outlook') {
    return { error: 'Missing or invalid client parameter.' }
  }
  if (!state || state.length < 16) {
    return { error: 'Missing or invalid state parameter.' }
  }
  if (!redirectUri) {
    return { error: 'Missing redirect_uri parameter.' }
  }
  return { client, state, redirectUri }
}

function sessionReadyForAuthorize(me: UserPublic): string | null {
  if (me.is_master_recovery) {
    return 'The master recovery account cannot authorize mail add-ins.'
  }
  if (me.session_password_change_required) {
    return 'Change your password in Canary before authorizing this add-in.'
  }
  if (me.session_second_factor_verified === false) {
    return 'Complete sign-in with passkey or authenticator app before authorizing this add-in.'
  }
  return null
}

function ConnectLoginForm({
  onSignedIn,
}: {
  onSignedIn: (token: string) => void
}) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [faCode, setFaCode] = useState('')
  const [step, setStep] = useState<'password' | '2fa'>('password')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function loginWithPassword(totp?: string) {
    setBusy(true)
    setError(null)
    try {
      const res = await apiFetch<TokenResponse>('/auth/login', {
        json: { email: email.trim(), password, totp_code: totp ?? null },
        timeoutMs: 45_000,
      })
      localStorage.setItem('token', res.access_token)
      onSignedIn(res.access_token)
      return 'success' as const
    } catch (e: unknown) {
      const msg = ((e as ApiError).message ?? '').trim() || 'Sign-in failed'
      if ((totp == null || totp.trim() === '') && msg === '2FA required') {
        return 'needs_2fa' as const
      }
      setError(msg)
      return 'error' as const
    } finally {
      setBusy(false)
    }
  }

  async function loginWithPasskey() {
    setBusy(true)
    setError(null)
    const emailNorm = email.trim().toLowerCase()
    if (!emailNorm) {
      setError('Enter your login id, then use Sign in with passkey.')
      setBusy(false)
      return
    }
    try {
      const options = await apiFetch<PublicKeyCredentialRequestOptionsJSON>('/auth/webauthn/login/begin', {
        method: 'POST',
        json: { email: emailNorm },
      })
      const assertion = await startAuthentication({ optionsJSON: options })
      const res = await apiFetch<TokenResponse>('/auth/webauthn/login/finish', {
        method: 'POST',
        json: { email: emailNorm, credential: assertion },
      })
      localStorage.setItem('token', res.access_token)
      onSignedIn(res.access_token)
    } catch (e: unknown) {
      setError((e as ApiError).message ?? 'Passkey sign-in failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card" style={{ maxWidth: 520, margin: '24px auto 0' }}>
      <p className="muted" style={{ marginTop: 0 }}>
        Sign in to Canary to connect your mail add-in. Passkeys and authenticator apps are supported here.
      </p>
      {step === 'password' ? (
        <form
          className="stack loginForm"
          style={{ marginTop: 16 }}
          onSubmit={(e: FormEvent) => {
            e.preventDefault()
            void (async () => {
              const result = await loginWithPassword()
              if (result === 'needs_2fa') {
                setStep('2fa')
                setFaCode('')
                setError(null)
              }
            })()
          }}
        >
          <label className="field">
            <span>Login id</span>
            <input
              value={email}
              onChange={(e) => {
                setError(null)
                setEmail(e.target.value)
              }}
              autoComplete="username"
              autoFocus
            />
          </label>
          <label className="field">
            <span>Password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => {
                setError(null)
                setPassword(e.target.value)
              }}
              autoComplete="current-password"
            />
          </label>
          {error ? <div className="error">{error}</div> : null}
          <div className="loginActionsRow">
            <button type="submit" className="btn primary" disabled={busy}>
              {busy ? 'Signing in…' : 'Sign in'}
            </button>
            <button type="button" className="btn" disabled={busy} onClick={() => void loginWithPasskey()}>
              Sign in with passkey
            </button>
          </div>
        </form>
      ) : (
        <form
          className="stack"
          style={{ marginTop: 16 }}
          onSubmit={(e: FormEvent) => {
            e.preventDefault()
            void loginWithPassword(faCode.trim() || undefined)
          }}
        >
          <p className="muted" style={{ marginTop: 0 }}>
            Enter the code from your authenticator app.
          </p>
          <label className="field">
            <span>Authenticator code</span>
            <input
              value={faCode}
              onChange={(e) => {
                setError(null)
                setFaCode(e.target.value)
              }}
              inputMode="numeric"
              autoComplete="one-time-code"
              autoFocus
            />
          </label>
          {error ? <div className="error">{error}</div> : null}
          <div className="loginActionsRow">
            <button type="submit" className="btn primary" disabled={busy}>
              {busy ? 'Verifying…' : 'Continue'}
            </button>
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={() => {
                setStep('password')
                setFaCode('')
                setError(null)
              }}
            >
              Back
            </button>
          </div>
        </form>
      )}
    </div>
  )
}

export default function MailPluginConnectPage() {
  const params = useMemo(() => parseConnectParams(), [])
  const [token, setToken] = useState(() => localStorage.getItem('token') ?? '')
  const [me, setMe] = useState<UserPublic | null>(null)
  const [loadingMe, setLoadingMe] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadMe = useCallback(async (accessToken: string) => {
    setLoadingMe(true)
    try {
      const user = await apiFetch<UserPublic>('/auth/me', { token: accessToken })
      setMe(user)
      setError(null)
    } catch (e: unknown) {
      setMe(null)
      localStorage.removeItem('token')
      setToken('')
      setError((e as ApiError).message ?? 'Could not load your account.')
    } finally {
      setLoadingMe(false)
    }
  }, [])

  useEffect(() => {
    if ('error' in params) {
      setLoadingMe(false)
      return
    }
    if (!token) {
      setLoadingMe(false)
      return
    }
    void loadMe(token)
  }, [loadMe, params, token])

  async function authorize() {
    if ('error' in params || !token || !me) return
    const block = sessionReadyForAuthorize(me)
    if (block) {
      setError(block)
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await apiFetch<{ code: string }>('/auth/plugin/authorize', {
        method: 'POST',
        token,
        json: {
          client: params.client,
          state: params.state,
          redirect_uri: params.redirectUri,
        },
      })
      const target = new URL(params.redirectUri)
      target.searchParams.set('code', res.code)
      target.searchParams.set('state', params.state)
      target.searchParams.set('client', params.client)
      window.location.replace(target.toString())
    } catch (e: unknown) {
      setError((e as ApiError).message ?? 'Could not authorize the add-in.')
      setBusy(false)
    }
  }

  if ('error' in params) {
    return (
      <div className="loginScreen">
        <div className="loginBrandRow">
          <AppLogo />
        </div>
        <div className="card" style={{ maxWidth: 520, margin: '24px auto 0' }}>
          <div className="error">{params.error}</div>
        </div>
      </div>
    )
  }

  const clientLabel = CLIENT_LABEL[params.client]
  const authorizeBlock = me ? sessionReadyForAuthorize(me) : null

  return (
    <div className="loginScreen">
      <div className="loginBrandRow">
        <AppLogo />
      </div>
      {loadingMe ? (
        <p className="muted" style={{ textAlign: 'center' }}>
          Loading…
        </p>
      ) : !token || !me ? (
        <ConnectLoginForm
          onSignedIn={(nextToken) => {
            setToken(nextToken)
            void loadMe(nextToken)
          }}
        />
      ) : (
        <div className="card" style={{ maxWidth: 520, margin: '24px auto 0' }}>
          <h2 style={{ margin: '0 0 8px', fontSize: 20 }}>Connect {clientLabel}</h2>
          <p className="muted" style={{ marginTop: 0 }}>
            Signed in as <strong>{me.display_name || me.email}</strong>. Allow {clientLabel} to access Canary on this
            computer?
          </p>
          {authorizeBlock ? <div className="error">{authorizeBlock}</div> : null}
          {error ? <div className="error">{error}</div> : null}
          <div className="loginActionsRow" style={{ marginTop: 16 }}>
            <button
              type="button"
              className="btn primary"
              disabled={busy || Boolean(authorizeBlock)}
              onClick={() => void authorize()}
            >
              {busy ? 'Authorizing…' : `Authorise ${clientLabel}`}
            </button>
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={() => {
                localStorage.removeItem('token')
                setToken('')
                setMe(null)
                setError(null)
              }}
            >
              Use another account
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
