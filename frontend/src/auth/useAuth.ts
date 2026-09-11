import { useCallback, useEffect, useState } from 'react'
import {
  startAuthentication,
  type PublicKeyCredentialRequestOptionsJSON,
} from '@simplewebauthn/browser'
import { apiFetch, COOKIE_SESSION_TOKEN, type ApiError } from '../api'
import { releaseAllBodyCursorLocks } from '../bodyCursorLock'
import type { TokenResponse, UserPublic } from '../types'

export function useAuth() {
  const [token, setToken] = useState<string | null>(null)
  const [me, setMe] = useState<UserPublic | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  /** Lives in this hook (not in LoginForm) so it survives remounts when `loading` toggles. */
  const [loginError, setLoginError] = useState<string | null>(null)
  const [sessionBootstrapped, setSessionBootstrapped] = useState(false)

  // Migrate off legacy localStorage JWTs; prefer HttpOnly ``canary_session`` cookie.
  useEffect(() => {
    let cancelled = false
    async function bootstrap() {
      try {
        localStorage.removeItem('token')
      } catch {
        /* */
      }
      try {
        const user = await apiFetch<UserPublic>('/auth/me', { token: COOKIE_SESSION_TOKEN })
        if (!cancelled) {
          setMe(user)
          setToken(COOKIE_SESSION_TOKEN)
        }
      } catch {
        if (!cancelled) {
          setMe(null)
          setToken(null)
        }
      } finally {
        if (!cancelled) {
          setSessionBootstrapped(true)
          setLoading(false)
        }
      }
    }
    void bootstrap()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!sessionBootstrapped) return
    let cancelled = false
    async function load() {
      // Do not call setLoading(true) when unauthenticated: App would replace the login form with
      // "Loading…", unmount LoginForm, and clear its local state (including any inline login error).
      if (!token) {
        setMe(null)
        setError(null)
        setLoading(false)
        releaseAllBodyCursorLocks()
        return
      }
      setLoading(true)
      setError(null)
      try {
        const user = await apiFetch<UserPublic>('/auth/me', { token })
        if (!cancelled) setMe(user)
      } catch (e: any) {
        if (!cancelled) {
          const msg = e?.message ?? 'Auth error'
          setError(msg)
          setLoginError(msg)
          setMe(null)
          setToken(null)
          try {
            localStorage.removeItem('token')
          } catch {
            /* */
          }
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [token, sessionBootstrapped])

  const refreshMe = useCallback(async () => {
    if (!token) return
    try {
      const user = await apiFetch<UserPublic>('/auth/me', { token })
      setMe(user)
    } catch {
      /* keep existing me */
    }
  }, [token])

  const applySessionToken = useCallback((_accessToken: string) => {
    // Server already set HttpOnly cookie; keep JWT out of JS storage.
    setToken(COOKIE_SESSION_TOKEN)
    void (async () => {
      try {
        const user = await apiFetch<UserPublic>('/auth/me', { token: COOKIE_SESSION_TOKEN })
        setMe(user)
      } catch {
        /* keep existing me */
      }
    })()
  }, [])

  return {
    token,
    me,
    loading: loading || !sessionBootstrapped,
    error,
    loginError,
    clearLoginError: () => setLoginError(null),
    refreshMe,
    applySessionToken,
    async login(email: string, password: string, totpCode?: string): Promise<'success' | 'needs_2fa' | 'error'> {
      setLoginError(null)
      try {
        await apiFetch<TokenResponse>('/auth/login', {
          json: { email, password, totp_code: totpCode ?? null },
          timeoutMs: 45_000,
        })
        setToken(COOKIE_SESSION_TOKEN)
        return 'success'
      } catch (e: unknown) {
        const msg = ((e as ApiError).message ?? '').trim() || 'Login failed'
        const totpEmpty = totpCode == null || String(totpCode).trim() === ''
        if (totpEmpty && msg === '2FA required') {
          return 'needs_2fa'
        }
        if (msg.includes('timed out')) {
          setLoginError('Sign-in timed out — the server may be busy. Wait a moment and try again.')
        } else {
          setLoginError(msg)
        }
        return 'error'
      }
    },
    async loginWithPasskey(email: string) {
      setLoginError(null)
      const emailNorm = email.trim().toLowerCase()
      if (!emailNorm) {
        setLoginError('Enter your email address, then use Sign in with passkey.')
        return
      }
      try {
        const options = await apiFetch<PublicKeyCredentialRequestOptionsJSON>('/auth/webauthn/login/begin', {
          method: 'POST',
          json: { email: emailNorm },
        })
        const assertion = await startAuthentication({ optionsJSON: options })
        await apiFetch<TokenResponse>('/auth/webauthn/login/finish', {
          method: 'POST',
          json: { email: emailNorm, credential: assertion },
        })
        setToken(COOKIE_SESSION_TOKEN)
      } catch (e: unknown) {
        setLoginError((e as ApiError).message ?? 'Passkey sign-in failed')
      }
    },
    logout() {
      releaseAllBodyCursorLocks()
      void apiFetch<{ ok: boolean }>('/auth/logout', { method: 'POST', token: COOKIE_SESSION_TOKEN }).catch(() => {
        /* */
      })
      try {
        localStorage.removeItem('token')
      } catch {
        /* */
      }
      setToken(null)
      setMe(null)
      setLoginError(null)
    },
  }
}


