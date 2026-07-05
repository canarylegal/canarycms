import {
  startAuthentication,
  startRegistration,
  type PublicKeyCredentialCreationOptionsJSON,
  type PublicKeyCredentialRequestOptionsJSON,
} from '@simplewebauthn/browser'
import { useCallback, useEffect, useMemo, useRef, useState, memo, type FormEvent, type ReactNode } from 'react'
import { AdminLoginUpdatePrompt } from './AdminLoginUpdatePrompt'
import { AdminConsole, RecoveryConsole } from './AdminConsole'
import { parseAppNavigation, readBootNavigation, sanitizeAppNavigation, syncAppNavigationUrl, type AppNavState } from './appNavigation'
import { CaseViewRoute } from './CaseViewRoute'
import { CalendarPage } from './CalendarPage'
import { DocusignPage } from './DocusignPage'
import { FeeScalesPanel } from './FeeScalesPanel'
import { QuoteSourcesPanel } from './QuoteSourcesPanel'
import { QuoteConvertModal } from './QuoteConvertModal'
import { QuoteWizard } from './QuoteWizard'
import { QuoteSendPrompt } from './QuoteSendPrompt'
import { useQuoteAwaitingSave, type QuoteAwaitingSaveContext } from './quoteAwaitingSave'
import { QUOTE_EMAIL_PRECEDENT_REFERENCE, type PendingCaseCompose } from './quoteEmailPrecedent'
import { ReportsPage } from './ReportsPage'
import { AccountsPage } from './AccountsPage'
import { TaskCreateModal } from './TaskCreateModal'
import { TasksTable } from './TasksTable'
import {
  GlobalContactCreateForm,
  ContactPersonOrgAddressFields,
  contactOutToFormFields,
  contactFieldsModelToPayload,
  resolveContactNameWithFallback,
} from './GlobalContactCreateForm'
import { ContactPortalPanel } from './ContactPortalPanel'
import type { CaseOpenDocPanel } from './case/CaseDetail'
import { closeMatterBlockMessage } from './case/closeMatterCheck'
import { matterContactTypeLabel } from './case/matterLabels'
import { PropertyDetailsForm } from './case/PropertyDetailsForm'
import {
  blankPropertyPayload,
  buildNewMatterDescription,
  subTypeHasPropertyMenu,
} from './case/propertyMatterHelpers'
import { releaseAllBodyCursorLocks } from './bodyCursorLock'
import { apiFetch, type ApiError } from './api'
import { fetchContactSearch } from './apiSearch'
import {
  ACCENT_COLOR_PRESETS,
  DEFAULT_ACCENT,
  DEFAULT_PAGE_BG,
  FONT_OPTIONS,
  PAGE_BG_COLOR_PRESETS,
} from './theme'
import { persistUserAppearance, useAppearanceFormState, useServerAppearance } from './useServerAppearance'
import { useUserUiPreferences } from './useUserUiPreferences'
import { useDebouncedValue } from './useDebouncedValue'
import { MainMenuFilterCheckboxDropdown } from './MainMenuFilterCheckboxDropdown'
import {
  CONTACTS_COLUMN_COUNT,
  CONTACTS_COLUMN_WIDTHS_DEFAULT,
  MAIN_MENU_COLUMN_COUNT,
  MAIN_MENU_COLUMN_WIDTHS_DEFAULT,
  TASKS_MENU_COLUMN_COUNT,
  TASKS_MENU_COLUMN_WIDTHS_DEFAULT,
  type MainMenuCaseStatusFilter,
} from './userUiPreferences'
import {
  effectiveColumnWidths,
  LEGACY_AUTO_CONTACTS_COLUMN_WIDTHS,
  LEGACY_AUTO_MAIN_MENU_COLUMN_WIDTHS,
  LEGACY_AUTO_TASKS_MENU_COLUMN_WIDTHS,
} from './columnGridDefaults'
import { useColumnWidths } from './useColumnWidths'
import { normalizeUiPreferences, resetMenuColumnWidths } from './userUiPreferences'
import { AppLogo } from './AppLogo'
import { AppSidebar } from './AppSidebar'
import { buildCaseContextMenuActions, scrollCaseRowIntoView, type CaseContextMenuActionKind } from './caseListKeyboard'
import { isEditableKeyboardTarget, isModalBlockingKeyboard } from './keyboardUtils'
import { usePrimaryNavKeyboard, type PrimaryNavId } from './usePrimaryNavKeyboard'
import {
  DEFAULT_OUTLOOK_WEB_MAIL_URL,
  isOrgMicrosoftGraphConfigured,
  OUTLOOK_WEB_WITHOUT_GRAPH_CONFIRM_MESSAGE,
} from './emailLauncher'
import { useDialogs } from './DialogProvider'
import { ContactSearchPicker } from './ContactSearchPicker'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import { SearchInput } from './SearchInput'
import { CaseSourceField, resolveCaseSourcePayload, useCaseSources } from './CaseSourceField'
import { copyTextToClipboard } from './copyToClipboard'
import { canaryDocumentTitle } from './tabTitle'
import { caseHasRevokedUserAccess, formatCaseStatusLabel, userCanAccessAccountsWorkspace, userCanAccessAdminConsole, userIsCashierAccountsHome, userIsMasterRecovery } from './types'
import type {
  CaseOut,
  CasePropertyPayload,
  TaskMenuRow,
  ContactOut,
  MatterHeadTypeOut,
  TokenResponse,
  Verify2FASessionResponse,
  ForgotPasswordResponse,
  ChangePasswordResponse,
  UserCalDAVProvisionOut,
  UserCalDAVStatusOut,
  UserPublic,
  UserSummary,
  WebAuthnCredentialOut,
} from './types'

type View =
  | 'main-menu'
  | 'quotes'
  | 'tasks'
  | 'case-menu'
  | 'contacts'
  | 'calendar'
  | 'docusign'
  | 'accounts'
  | 'reports'
  | 'user-settings'
  | 'admin-console'

function canaryViewTitleSegment(view: View, caseDetail: CaseOut | null): string {
  switch (view) {
    case 'main-menu':
      return 'Cases'
    case 'quotes':
      return 'Quotes'
    case 'case-menu': {
      const desc = caseDetail?.matter_description?.trim()
      if (desc) return desc
      const ref = caseDetail?.case_number?.trim()
      return ref || 'Case'
    }
    case 'tasks':
      return 'Tasks'
    case 'contacts':
      return 'Contacts'
    case 'docusign':
      return 'DocuSign'
    case 'calendar':
      return 'Calendar'
    case 'accounts':
      return 'Accounts'
    case 'reports':
      return 'Reports'
    case 'user-settings':
      return 'User Settings'
    case 'admin-console':
      return 'Admin Settings'
  }
}

function formatTs(s: string) {
  const d = new Date(s)
  return isNaN(d.getTime()) ? s : d.toLocaleString()
}

/** Non-admin users who must complete authenticator 2FA or register a passkey before using the rest of the app. */
function userNeedsSecondFactorSetup(me: UserPublic): boolean {
  if (userIsMasterRecovery(me)) return false
  return Boolean(me.organization_requires_second_factor && !me.is_2fa_enabled && !me.has_passkeys)
}

/** JWT/session did not satisfy org “verified second factor at sign-in” (passkey or password + authenticator). */
function sessionNeedsVerifiedSecondFactor(me: UserPublic): boolean {
  if (userIsMasterRecovery(me)) return false
  return me.session_second_factor_verified === false
}

function sessionNeedsPasswordChange(me: UserPublic): boolean {
  if (userIsMasterRecovery(me)) return false
  return me.session_password_change_required === true
}

function PasswordChangeSessionGate({
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

function SecondFactorSessionGate({
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

function useAuth() {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('token'))
  const [me, setMe] = useState<UserPublic | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  /** Lives in this hook (not in LoginForm) so it survives remounts when `loading` toggles. */
  const [loginError, setLoginError] = useState<string | null>(null)

  useEffect(() => {
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
          localStorage.removeItem('token')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [token])

  const refreshMe = useCallback(async () => {
    if (!token) return
    try {
      const user = await apiFetch<UserPublic>('/auth/me', { token })
      setMe(user)
    } catch {
      /* keep existing me */
    }
  }, [token])

  const applySessionToken = useCallback((accessToken: string) => {
    const t = accessToken.trim()
    if (!t) return
    localStorage.setItem('token', t)
    setToken(t)
    void (async () => {
      try {
        const user = await apiFetch<UserPublic>('/auth/me', { token: t })
        setMe(user)
      } catch {
        /* keep existing me */
      }
    })()
  }, [])

  return {
    token,
    me,
    loading,
    error,
    loginError,
    clearLoginError: () => setLoginError(null),
    refreshMe,
    applySessionToken,
    async login(email: string, password: string, totpCode?: string): Promise<'success' | 'needs_2fa' | 'error'> {
      setLoginError(null)
      try {
        const res = await apiFetch<TokenResponse>('/auth/login', {
          json: { email, password, totp_code: totpCode ?? null },
          timeoutMs: 45_000,
        })
        localStorage.setItem('token', res.access_token)
        setToken(res.access_token)
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
        const res = await apiFetch<TokenResponse>('/auth/webauthn/login/finish', {
          method: 'POST',
          json: { email: emailNorm, credential: assertion },
        })
        localStorage.setItem('token', res.access_token)
        setToken(res.access_token)
      } catch (e: unknown) {
        setLoginError((e as ApiError).message ?? 'Passkey sign-in failed')
      }
    },
    logout() {
      releaseAllBodyCursorLocks()
      localStorage.removeItem('token')
      setToken(null)
      setMe(null)
      setLoginError(null)
    },
  }
}

function ResetPasswordForm({ token, onDone }: { token: string; onDone: () => void }) {
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

function LoginForm({
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
      <div className="card" style={{ maxWidth: 520, margin: '24px auto 0' }}>
        {step === 'password' ? (
          <>
            <form className="stack loginForm" style={{ marginTop: 16 }} onSubmit={handlePasswordSubmit}>
              <label className="field">
                <span>Login id</span>
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
                <input
                  type="password"
                  value={password}
                  onChange={(e) => {
                    onClearError()
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
                <button
                  type="button"
                  className="btn"
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

function App({ initialTasksCaseFilter }: { initialTasksCaseFilter?: string | null } = {}) {
  const auth = useAuth()

  useEffect(() => {
    releaseAllBodyCursorLocks()
    function onPageShow() {
      releaseAllBodyCursorLocks()
    }
    window.addEventListener('pageshow', onPageShow)
    return () => window.removeEventListener('pageshow', onPageShow)
  }, [])

  const bootNav = useMemo(() => readBootNavigation(initialTasksCaseFilter), [initialTasksCaseFilter])
  const [resetToken, setResetToken] = useState<string | null>(() => {
    try {
      return new URLSearchParams(window.location.search).get('reset_token')
    } catch {
      return null
    }
  })
  const clearResetToken = useCallback(() => {
    setResetToken(null)
    try {
      const url = new URL(window.location.href)
      url.searchParams.delete('reset_token')
      window.history.replaceState({}, '', url.pathname + url.search + url.hash)
    } catch {
      // ignore
    }
  }, [])
  useServerAppearance(auth.me, auth.token)
  const { askConfirm, alert } = useDialogs()
  const [view, setViewState] = useState<View>(bootNav.view)
  const viewRef = useRef(view)
  viewRef.current = view
  const caseTitleDetailRef = useRef<CaseOut | null>(null)
  const [caseTitleDetail, setCaseTitleDetail] = useState<CaseOut | null>(null)
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(bootNav.caseId)
  const [showNewMatter, setShowNewMatter] = useState(false)

  // Cases
  const [cases, setCases] = useState<CaseOut[]>([])
  const [, setCasesBusy] = useState(false)
  const [casesErr, setCasesErr] = useState<string | null>(null)
  const [caseListFocusId, setCaseListFocusId] = useState<string | null>(bootNav.caseId)
  const [caseOpenDocPanel, setCaseOpenDocPanel] = useState<CaseOpenDocPanel | null>(null)
  const consumeCaseOpenDocPanel = useCallback(() => setCaseOpenDocPanel(null), [])
  const [taskMenuRows, setTaskMenuRows] = useState<TaskMenuRow[]>([])
  const [taskMenuCaseFilter, setTaskMenuCaseFilter] = useState<string | null>(bootNav.tasksCaseFilter)
  const [globalTaskCreateOpen, setGlobalTaskCreateOpen] = useState(false)
  const [tasksMenuFilterOpen, setTasksMenuFilterOpen] = useState(false)
  const [tasksLayoutOpen, setTasksLayoutOpen] = useState(false)
  const [tasksFilterMatterTypeOpen, setTasksFilterMatterTypeOpen] = useState(false)

  const [caseListUsers, setCaseListUsers] = useState<UserSummary[]>([])
  const canAdminConsole = userCanAccessAdminConsole(auth.me)
  const canAdminConsoleRef = useRef(canAdminConsole)
  canAdminConsoleRef.current = canAdminConsole
  const canAccessAccounts = userCanAccessAccountsWorkspace(auth.me)
  const canAccessAccountsRef = useRef(canAccessAccounts)
  canAccessAccountsRef.current = canAccessAccounts
  const [docusignEnabled, setDocusignEnabled] = useState<boolean | null>(null)
  const docusignEnabledRef = useRef(docusignEnabled)
  docusignEnabledRef.current = docusignEnabled
  const [reportsInitialTab, setReportsInitialTab] = useState<
    'client_account_reconcile' | null
  >(null)
  const [cashierMainMenuExplicit, setCashierMainMenuExplicit] = useState(false)
  const cashierMainMenuExplicitRef = useRef(cashierMainMenuExplicit)
  cashierMainMenuExplicitRef.current = cashierMainMenuExplicit

  const token = auth.token ?? undefined
  const [taskMenuSearch, setTaskMenuSearch] = useState('')
  const [taskMenuFilterMatterType, setTaskMenuFilterMatterType] = useState('')
  const [mainMenuFilterMatterTypes, setMainMenuFilterMatterTypes] = useState<string[]>([])
  const [mainMenuFilterFeeEarnerUserIds, setMainMenuFilterFeeEarnerUserIds] = useState<string[]>([])
  const [mainMenuFilterCaseStatuses, setMainMenuFilterCaseStatuses] = useState<MainMenuCaseStatusFilter[]>([])
  const [quotesFilterMatterTypes, setQuotesFilterMatterTypes] = useState<string[]>([])
  const [quotesFilterFeeEarnerUserIds, setQuotesFilterFeeEarnerUserIds] = useState<string[]>([])
  const [quotesFilterCaseStatuses, setQuotesFilterCaseStatuses] = useState<MainMenuCaseStatusFilter[]>(['quote'])
  const [quotesSubPanel, setQuotesSubPanel] = useState<'list' | 'fee-scales' | 'sources'>(bootNav.quotesSubPanel)
  const [quoteWizardOpen, setQuoteWizardOpen] = useState(false)
  const [newMatterFromQuotes, setNewMatterFromQuotes] = useState(false)
  const [quoteWizardPendingCaseId, setQuoteWizardPendingCaseId] = useState<string | null>(null)
  const [quoteAwaitingSave, setQuoteAwaitingSave] = useState<QuoteAwaitingSaveContext | null>(null)
  const [quoteSendOpen, setQuoteSendOpen] = useState(false)
  const [pendingComposeKind, setPendingComposeKind] = useState<PendingCaseCompose | null>(null)

  const selectedCaseIdRef = useRef(selectedCaseId)
  selectedCaseIdRef.current = selectedCaseId
  const quotesSubPanelRef = useRef(quotesSubPanel)
  quotesSubPanelRef.current = quotesSubPanel
  const taskMenuCaseFilterRef = useRef(taskMenuCaseFilter)
  taskMenuCaseFilterRef.current = taskMenuCaseFilter

  const syncNavFromState = useCallback((patch: Partial<AppNavState> & { view?: View }) => {
    const v = patch.view ?? viewRef.current
    const next: AppNavState = {
      view: v,
      caseId:
        patch.caseId !== undefined ? patch.caseId : v === 'case-menu' ? selectedCaseIdRef.current : null,
      quotesSubPanel: patch.quotesSubPanel ?? quotesSubPanelRef.current,
      tasksCaseFilter: patch.tasksCaseFilter ?? taskMenuCaseFilterRef.current,
    }
    syncAppNavigationUrl(next, 'replace')
  }, [])

  const setView = useCallback(
    (next: View) => {
      if (next === 'admin-console' && !canAdminConsoleRef.current) {
        next = 'main-menu'
      }
      if (next === 'accounts' && !canAccessAccountsRef.current) {
        next = 'main-menu'
      }
      if (next === 'docusign' && docusignEnabledRef.current !== true) {
        next = 'main-menu'
      }
      setViewState(next)
      syncNavFromState({ view: next, caseId: next === 'case-menu' ? selectedCaseIdRef.current : null })
    },
    [syncNavFromState],
  )

  const goMainMenu = useCallback(() => {
    if (userIsCashierAccountsHome(auth.me)) {
      setCashierMainMenuExplicit(true)
    }
    setView('main-menu')
  }, [auth.me, setView])

  const primaryNavHandlers = useMemo(
    (): Record<PrimaryNavId, () => void> => ({
      'main-menu': goMainMenu,
      quotes: () => {
        setView('quotes')
        setQuotesSubPanel('list')
      },
      calendar: () => setView('calendar'),
      tasks: () => setView('tasks'),
      contacts: () => setView('contacts'),
      docusign: () => setView('docusign'),
      accounts: () => setView('accounts'),
      reports: () => setView('reports'),
      'user-settings': () => setView('user-settings'),
      'admin-console': () => setView('admin-console'),
    }),
    [goMainMenu, setView],
  )

  usePrimaryNavKeyboard({
    enabled: Boolean(token),
    view,
    canAccessAccounts,
    canAdminConsole,
    docusignEnabled: docusignEnabled === true,
    onNavigate: primaryNavHandlers,
  })

  const confirmLogout = useCallback(async () => {
    const ok = await askConfirm({
      title: 'Sign out',
      message: 'Are you sure you want to sign out of Canary?',
      confirmLabel: 'Sign out',
      cancelLabel: 'Cancel',
    })
    if (ok) auth.logout()
  }, [askConfirm, auth.logout])

  const { prefs: uiPrefs, setPreference: setUiPreference, setPreferenceDebounced: setUiPreferenceDebounced } =
    useUserUiPreferences(auth.me, auth.token)

  const onMainMenuFilterMatterTypesChange = useCallback((value: string[]) => {
    setMainMenuFilterMatterTypes(value)
  }, [])

  const onMainMenuFilterFeeEarnerIdsChange = useCallback((value: string[]) => {
    setMainMenuFilterFeeEarnerUserIds(value)
  }, [])

  const onMainMenuFilterCaseStatusesChange = useCallback((value: MainMenuCaseStatusFilter[]) => {
    setMainMenuFilterCaseStatuses(value)
  }, [])

  const onQuotesFilterMatterTypesChange = useCallback((value: string[]) => {
    setQuotesFilterMatterTypes(value)
  }, [])
  const onQuotesFilterFeeEarnerIdsChange = useCallback((value: string[]) => {
    setQuotesFilterFeeEarnerUserIds(value)
  }, [])
  const onQuotesFilterCaseStatusesChange = useCallback((value: MainMenuCaseStatusFilter[]) => {
    setQuotesFilterCaseStatuses(value)
  }, [])
  const persistQuotesFilters = useCallback(
    (_matterTypes: string[], _feeEarnerUserIds: string[], _caseStatuses: MainMenuCaseStatusFilter[]) => {
      /* Quotes filters are session-local; default status Quote on first load. */
    },
    [],
  )

  const persistMainMenuFilters = useCallback(
    (matterTypes: string[], feeEarnerUserIds: string[], caseStatuses: MainMenuCaseStatusFilter[]) => {
      setUiPreference('main_menu_filter_matter_types', matterTypes)
      setUiPreference('main_menu_filter_fee_earner_user_ids', feeEarnerUserIds)
      setUiPreference('main_menu_filter_case_statuses', caseStatuses)
    },
    [setUiPreference],
  )

  const { gridTemplateColumns: casesGridColumns, startResize: casesStartResize } = useColumnWidths(
    MAIN_MENU_COLUMN_COUNT,
    {
      widths: effectiveColumnWidths(
        uiPrefs.main_menu_column_widths,
        MAIN_MENU_COLUMN_COUNT,
        LEGACY_AUTO_MAIN_MENU_COLUMN_WIDTHS,
      ),
      fallbackWidths: [...MAIN_MENU_COLUMN_WIDTHS_DEFAULT],
      onChange: (widths) => setUiPreferenceDebounced('main_menu_column_widths', widths, 300),
    },
  )

  const { gridTemplateColumns: tasksGridColumns, startResize: tasksStartResize } = useColumnWidths(
    TASKS_MENU_COLUMN_COUNT,
    {
      widths: effectiveColumnWidths(
        uiPrefs.tasks_menu_column_widths,
        TASKS_MENU_COLUMN_COUNT,
        LEGACY_AUTO_TASKS_MENU_COLUMN_WIDTHS,
      ),
      fallbackWidths: [...TASKS_MENU_COLUMN_WIDTHS_DEFAULT],
      onChange: (widths) => setUiPreferenceDebounced('tasks_menu_column_widths', widths, 300),
    },
  )

  const tasksMenuActiveFilterCount = useMemo(
    () => (taskMenuFilterMatterType ? 1 : 0),
    [taskMenuFilterMatterType],
  )

  const tasksMenuMatterTypeOptions = useMemo(() => {
    const s = new Set<string>()
    for (const r of taskMenuRows) {
      if (r.matter_type_label.trim()) s.add(r.matter_type_label)
    }
    return Array.from(s).sort((a, b) => a.localeCompare(b))
  }, [taskMenuRows])

  const tasksFilterMatterTypeOptions = useMemo(
    () => [
      { value: '', label: 'All' },
      ...tasksMenuMatterTypeOptions.map((label) => ({ value: label, label })),
    ],
    [tasksMenuMatterTypeOptions],
  )

  const taskLayoutOptions = useMemo(
    () => [
      { value: 'list', label: 'List' },
      { value: 'kanban', label: 'Kanban' },
    ],
    [],
  )

  useEffect(() => {
    if (!token) return
    let cancelled = false
    async function load() {
      try {
        const data = await apiFetch<UserSummary[]>('/users', { token })
        if (!cancelled) setCaseListUsers((Array.isArray(data) ? data : []).filter((u) => u.is_active))
      } catch {
        if (!cancelled) setCaseListUsers([])
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [token])

  async function refreshCases() {
    if (!token) return
    setCasesBusy(true)
    setCasesErr(null)
    try {
      const data = await apiFetch<CaseOut[]>('/cases', { token })
      setCases(Array.isArray(data) ? data : [])
    } catch (e: any) {
      setCasesErr(e?.message ?? 'Failed to load cases')
    } finally {
      setCasesBusy(false)
    }
  }

  const refreshTaskMenu = useCallback(async () => {
    if (!token) return
    try {
      const q = taskMenuCaseFilter ? `?case_id=${encodeURIComponent(taskMenuCaseFilter)}` : ''
      const data = await apiFetch<TaskMenuRow[]>(`/tasks${q}`, { token })
      setTaskMenuRows(Array.isArray(data) ? data : [])
    } catch {
      setTaskMenuRows([])
    }
  }, [token, taskMenuCaseFilter])

  useEffect(() => {
    if (!token) return
    void refreshCases()
  }, [token])

  useEffect(() => {
    if (!token || view !== 'tasks') return
    void refreshTaskMenu()
  }, [token, view, refreshTaskMenu])

  useEffect(() => {
    if (view !== 'tasks') {
      setTasksMenuFilterOpen(false)
      setTasksLayoutOpen(false)
      setTasksFilterMatterTypeOpen(false)
    }
  }, [view])

  useEffect(() => {
    syncNavFromState({})
  }, [syncNavFromState])

  useEffect(() => {
    if (view !== 'case-menu') setCaseTitleDetail(null)
  }, [view])

  const onCaseTitleDetailChange = useCallback((detail: CaseOut | null) => {
    caseTitleDetailRef.current = detail
    setCaseTitleDetail(detail)
    if (viewRef.current === 'case-menu') {
      document.title = canaryDocumentTitle(canaryViewTitleSegment('case-menu', detail))
    }
  }, [])

  const onPendingComposeConsumed = useCallback(() => {
    setPendingComposeKind(null)
  }, [])

  const onQuotePublished = useCallback(() => {
    setQuoteSendOpen(true)
  }, [])

  const onQuoteDiscarded = useCallback(() => {
    setQuoteAwaitingSave(null)
  }, [])

  useQuoteAwaitingSave(quoteAwaitingSave, {
    onPublished: onQuotePublished,
    onDiscarded: onQuoteDiscarded,
  })

  const onCaseListInvalidate = useCallback(() => {
    void refreshCases()
  }, [token])

  const onTaskMenuInvalidate = useCallback(() => {
    void refreshTaskMenu()
  }, [refreshTaskMenu])

  useEffect(() => {
    if (!auth.token) setCashierMainMenuExplicit(false)
  }, [auth.token])

  useEffect(() => {
    if (auth.loading || !auth.me) return
    if (!userIsCashierAccountsHome(auth.me)) return
    if (cashierMainMenuExplicitRef.current) return
    if (viewRef.current !== 'main-menu') return
    const path = window.location.pathname.replace(/\/+$/, '') || '/'
    if (path !== '/' && path !== '/main') return
    setViewState('accounts')
    syncNavFromState({ view: 'accounts', caseId: null })
  }, [auth.loading, auth.me, syncNavFromState])

  useEffect(() => {
    if (!auth.me || canAdminConsole) return
    if (viewRef.current !== 'admin-console') return
    setViewState('main-menu')
    syncNavFromState({ view: 'main-menu', caseId: null })
  }, [auth.me, canAdminConsole, syncNavFromState])

  useEffect(() => {
    if (!token) {
      setDocusignEnabled(false)
      return
    }
    setDocusignEnabled(null)
    void apiFetch<{ enabled: boolean }>('/docusign/options', { token })
      .then((o) => setDocusignEnabled(Boolean(o.enabled)))
      .catch(() => setDocusignEnabled(false))
  }, [token])

  useEffect(() => {
    if (!auth.me || canAccessAccounts) return
    if (viewRef.current !== 'accounts') return
    setViewState('main-menu')
    syncNavFromState({ view: 'main-menu', caseId: null })
  }, [auth.me, canAccessAccounts, syncNavFromState])

  useEffect(() => {
    if (docusignEnabled !== false) return
    if (viewRef.current !== 'docusign') return
    setViewState('main-menu')
    syncNavFromState({ view: 'main-menu', caseId: null })
  }, [docusignEnabled, syncNavFromState])

  useEffect(() => {
    function onPopState() {
      const parsed = parseAppNavigation(window.location)
      const nav = sanitizeAppNavigation(
        parsed,
        canAdminConsoleRef.current,
        canAccessAccountsRef.current,
        docusignEnabledRef.current === true,
      )
      if (nav.view !== parsed.view) {
        syncAppNavigationUrl(nav, 'replace')
      }
      setViewState(nav.view)
      setSelectedCaseId(nav.caseId)
      if (nav.caseId) setCaseListFocusId(nav.caseId)
      setQuotesSubPanel(nav.quotesSubPanel)
      setTaskMenuCaseFilter(nav.tasksCaseFilter)
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  const openCaseView = useCallback(
    (caseId: string) => {
      setSelectedCaseId(caseId)
      setViewState('case-menu')
      syncNavFromState({ view: 'case-menu', caseId })
    },
    [syncNavFromState],
  )

  const onMainMenuSelectCase = useCallback(
    (id: string, opts?: { docPanel?: CaseOpenDocPanel }) => {
      setCaseListFocusId(id)
      setCaseOpenDocPanel(opts?.docPanel ?? null)
      openCaseView(id)
    },
    [openCaseView],
  )

  const onMainMenuSort = useCallback(
    (k: 'reference' | 'client' | 'matter' | 'feeEarner' | 'status' | 'source' | 'created') => {
      if (k === uiPrefs.main_menu_sort_key) {
        setUiPreference('main_menu_sort_dir', uiPrefs.main_menu_sort_dir === 'asc' ? 'desc' : 'asc')
      } else {
        setUiPreference('main_menu_sort_key', k)
        setUiPreference('main_menu_sort_dir', 'asc')
      }
    },
    [setUiPreference, uiPrefs.main_menu_sort_dir, uiPrefs.main_menu_sort_key],
  )

  const onOpenNewMatter = useCallback(() => {
    setNewMatterFromQuotes(false)
    setShowNewMatter(true)
  }, [])
  const onCloseNewMatter = useCallback(() => {
    setShowNewMatter(false)
    setNewMatterFromQuotes(false)
  }, [])
  const onRefreshCases = useCallback(() => refreshCases(), [token])

  const [quotesNotice, setQuotesNotice] = useState<string | null>(null)
  const [quoteConvertCaseId, setQuoteConvertCaseId] = useState<string | null>(null)
  useEffect(() => {
    if (!quotesNotice) return
    const tid = window.setTimeout(() => setQuotesNotice(null), 8000)
    return () => window.clearTimeout(tid)
  }, [quotesNotice])

  const onQuoteConvert = useCallback(
    (caseId: string) => {
      if (!cases.some((c) => c.id === caseId && c.status === 'quote')) return
      setQuoteConvertCaseId(caseId)
    },
    [cases],
  )

  const quoteConvertCase = useMemo(() => {
    if (!quoteConvertCaseId) return null
    const row = cases.find((c) => c.id === quoteConvertCaseId)
    return row?.status === 'quote' ? row : null
  }, [quoteConvertCaseId, cases])

  const onQuoteConverted = useCallback(
    async ({ caseId, openAfter }: { caseId: string; openAfter: boolean }) => {
      setQuoteConvertCaseId(null)
      setCases((prev) => prev.map((c) => (c.id === caseId ? { ...c, status: 'open' as const } : c)))
      await refreshCases()
      setQuotesNotice('Quote converted to Active.')
      if (openAfter) openCaseView(caseId)
    },
    [openCaseView, refreshCases],
  )

  const onQuoteClose = useCallback(
    async (caseId: string) => {
      if (!token) return
      try {
        const blockMsg = await closeMatterBlockMessage(token, caseId)
        if (blockMsg) {
          void alert(blockMsg, 'Cannot close matter')
          return
        }
      } catch {
        /* fall through — server will reject if balances are non-zero */
      }
      const ok = await askConfirm({
        title: 'Close matter',
        message: 'Do you want to close this matter?',
        confirmLabel: 'Yes',
        cancelLabel: 'No',
      })
      if (!ok || !token) return
      try {
        await apiFetch(`/cases/${caseId}`, { method: 'PATCH', token, json: { status: 'quote_closed' } })
        void refreshCases()
      } catch (e: unknown) {
        const msg =
          e && typeof e === 'object' && 'message' in e
            ? String((e as { message?: string }).message)
            : 'Could not close matter'
        void alert(msg, 'Close matter')
      }
    },
    [alert, askConfirm, token],
  )

  const onMainMenuCaseCreated = useCallback(
    async (created?: CaseOut) => {
      setShowNewMatter(false)
      await refreshCases()
      if (!created?.id) return
      if (newMatterFromQuotes) {
        setQuoteWizardPendingCaseId(created.id)
        setQuoteWizardOpen(true)
        setNewMatterFromQuotes(false)
      } else {
        setCaseListFocusId(created.id)
        openCaseView(created.id)
      }
    },
    [newMatterFromQuotes, openCaseView],
  )

  const mainMenuFiltersLoadedForUser = useRef<string | null>(null)
  useEffect(() => {
    if (!auth.me?.id) {
      mainMenuFiltersLoadedForUser.current = null
      return
    }
    if (mainMenuFiltersLoadedForUser.current === auth.me.id) return
    mainMenuFiltersLoadedForUser.current = auth.me.id
    const saved = normalizeUiPreferences(auth.me.ui_preferences)
    setMainMenuFilterMatterTypes(saved.main_menu_filter_matter_types)
    setMainMenuFilterFeeEarnerUserIds(saved.main_menu_filter_fee_earner_user_ids)
    setMainMenuFilterCaseStatuses(saved.main_menu_filter_case_statuses.filter((s) => s !== 'quote' && s !== 'quote_closed'))
  }, [auth.me?.id])

  function renderMainContent() {
    if (!token) return null
    if (view === 'main-menu') return null
    if (view === 'quotes') {
      if (quotesSubPanel === 'fee-scales') {
        return <FeeScalesPanel token={token} onBack={() => setQuotesSubPanel('list')} />
      }
      if (quotesSubPanel === 'sources') {
        return <QuoteSourcesPanel token={token} me={auth.me} onBack={() => setQuotesSubPanel('list')} />
      }
      return null
    }

    if (view === 'admin-console') {
      if (!auth.me || !canAdminConsole) return null
      return <AdminConsole token={token} refreshMe={auth.refreshMe} />
    }
    if (view === 'user-settings')
      return <UserSettingsPage token={token} refreshMe={auth.refreshMe} applySessionToken={auth.applySessionToken} />
    if (view === 'calendar')
      return <CalendarPage token={token} me={auth.me} onOpenSettings={() => setView('user-settings')} />
    if (view === 'contacts') return <Contacts token={token} me={auth.me} />
    if (view === 'docusign') {
      if (docusignEnabled !== true) return null
      return <DocusignPage token={token} onSelectCase={openCaseView} />
    }

    if (view === 'accounts') {
      if (!canAccessAccounts) return null
      return (
        <AccountsPage
          token={token}
          me={auth.me}
          onOpenCase={openCaseView}
          onOpenReportsReconcile={() => {
            setReportsInitialTab('client_account_reconcile')
            setView('reports')
          }}
        />
      )
    }

    if (view === 'reports') {
      return (
        <ReportsPage
          token={token}
          me={auth.me}
          initialTab={reportsInitialTab ?? undefined}
          onInitialTabConsumed={() => setReportsInitialTab(null)}
        />
      )
    }

    if (view === 'case-menu' && selectedCaseId) {
      return (
        <CaseViewRoute
          token={token}
          caseId={selectedCaseId}
          currentUser={auth.me}
          openDocPanel={caseOpenDocPanel}
          onOpenDocPanelConsumed={consumeCaseOpenDocPanel}
          pendingComposeKind={pendingComposeKind}
          onPendingComposeConsumed={onPendingComposeConsumed}
          onCaseListInvalidate={onCaseListInvalidate}
          onTaskMenuInvalidate={onTaskMenuInvalidate}
          onCaseDetailChange={onCaseTitleDetailChange}
        />
      )
    }

    if (view === 'tasks') {
      return (
        <>
        <div className="mainMenuShell mainMenuShell--mainMenu">
          <div className={`mainMenuFilterBar${tasksMenuFilterOpen ? ' mainMenuFilterBar--dropdownOpen' : ''}`}>
            <div className="row mainMenuFilterRow mainMenuFilterRow--toolbar mainMenuFilterRow--searchRight">
              <div className="mainMenuFilterRowLeft">
                {taskMenuCaseFilter ? (
                  <button type="button" className="btn" onClick={() => setTaskMenuCaseFilter(null)}>
                    Show all tasks
                  </button>
                ) : null}
                <button type="button" className="btn primary toolbarLeadBtn" onClick={() => setGlobalTaskCreateOpen(true)}>
                  New task
                </button>
                <div className="tasksToolbarLayoutGroup">
                  <span className="tasksToolbarLayoutLabel">View</span>
                  <SingleSelectDropdown
                    hideLabel
                    label="Task layout"
                    options={taskLayoutOptions}
                    value={uiPrefs.tasks_menu_layout}
                    onChange={(v) => setUiPreference('tasks_menu_layout', v as 'list' | 'kanban')}
                    open={tasksLayoutOpen}
                    onOpenChange={setTasksLayoutOpen}
                  />
                </div>
                <button
                  type="button"
                  className="btn"
                  onClick={() => {
                    void refreshCases()
                    void refreshTaskMenu()
                  }}
                >
                  Refresh
                </button>
                <button
                  type="button"
                  className="btn"
                  onClick={() => void (async () => {
                    if (!token) return
                    const ok = await askConfirm({
                      title: 'Clear completed tasks',
                      message: taskMenuCaseFilter
                        ? 'Remove all completed tasks for this matter from the list?'
                        : 'Remove all of your completed tasks from the list?',
                    })
                    if (!ok) return
                    try {
                      const q = taskMenuCaseFilter ? `?case_id=${encodeURIComponent(taskMenuCaseFilter)}` : ''
                      await apiFetch(`/tasks/completed${q}`, { token, method: 'DELETE' })
                      void refreshTaskMenu()
                    } catch {
                      // ignore
                    }
                  })()}
                >
                  Clear completed tasks
                </button>
              </div>
              <div className="mainMenuFilterRowRight">
                <div className="caseToolbarDropdownWrap">
                  <button
                    type="button"
                    className="btn mainMenuFilterBtn"
                    aria-expanded={tasksMenuFilterOpen}
                    aria-haspopup="true"
                    aria-controls="tasks-menu-filter-menu"
                    id="tasks-menu-filter-button"
                    onClick={(e) => {
                      e.stopPropagation()
                      setTasksMenuFilterOpen((o) => !o)
                    }}
                  >
                    <span className="mainMenuFilterBtnInner">
                      <svg
                        className="mainMenuFilterBtnIcon"
                        width={16}
                        height={16}
                        viewBox="0 0 24 24"
                        fill="none"
                        xmlns="http://www.w3.org/2000/svg"
                        aria-hidden
                      >
                        <polygon
                          points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          fill="none"
                        />
                      </svg>
                      <span>Filter</span>
                      <span className="mainMenuFilterBtnCount">({tasksMenuActiveFilterCount})</span>
                    </span>
                  </button>
                  {tasksMenuFilterOpen ? (
                    <div
                      id="tasks-menu-filter-menu"
                      className="caseToolbarDropdown mainMenuFilterDropdown"
                      role="group"
                      aria-labelledby="tasks-menu-filter-button"
                      onMouseDown={(e) => e.stopPropagation()}
                    >
                      <div className="stack mainMenuFilterDropdownBody">
                        <SingleSelectDropdown
                          label="Matter type"
                          options={tasksFilterMatterTypeOptions}
                          value={taskMenuFilterMatterType}
                          onChange={setTaskMenuFilterMatterType}
                          open={tasksFilterMatterTypeOpen}
                          onOpenChange={setTasksFilterMatterTypeOpen}
                          placeholder="All"
                        />
                      </div>
                    </div>
                  ) : null}
                </div>
            <SearchInput
              placeholder="Search"
              value={taskMenuSearch}
              onChange={(e) => setTaskMenuSearch(e.target.value)}
              onClear={() => setTaskMenuSearch('')}
              className="mainMenuSearchInput"
              aria-label="Search tasks"
            />
              </div>
            </div>
          </div>
          <TasksTable
            token={token}
            currentUserId={auth.me?.id ?? ''}
            users={caseListUsers}
            rows={taskMenuRows}
            layoutMode={uiPrefs.tasks_menu_layout}
            search={taskMenuSearch}
            filterMatterType={taskMenuFilterMatterType}
            gridTemplateColumns={tasksGridColumns}
            startColumnResize={tasksStartResize}
            onSelectCase={(caseId) => {
              openCaseView(caseId)
            }}
            sortKey={uiPrefs.tasks_menu_sort_key}
            sortDir={uiPrefs.tasks_menu_sort_dir}
            onSort={(k) => {
              if (k === uiPrefs.tasks_menu_sort_key) {
                setUiPreference('tasks_menu_sort_dir', uiPrefs.tasks_menu_sort_dir === 'asc' ? 'desc' : 'asc')
              } else {
                setUiPreference('tasks_menu_sort_key', k)
                setUiPreference('tasks_menu_sort_dir', k === 'priority' ? 'desc' : 'asc')
              }
            }}
            onInvalidate={() => void refreshTaskMenu()}
          />
        </div>
        <TaskCreateModal
          open={globalTaskCreateOpen}
          token={token}
          users={caseListUsers}
          caseIdFixed={null}
          preset={null}
          onClose={() => setGlobalTaskCreateOpen(false)}
          onCreated={() => void refreshTaskMenu()}
        />
        </>
      )
    }

    return null
  }

  const mainMenuCasesPanel = token ? (
    <MainMenuCasesPanel
      cases={cases}
      casesErr={casesErr}
      users={caseListUsers}
      filterMatterTypes={mainMenuFilterMatterTypes}
      filterFeeEarnerUserIds={mainMenuFilterFeeEarnerUserIds}
      filterCaseStatuses={mainMenuFilterCaseStatuses}
      onFilterMatterTypesChange={onMainMenuFilterMatterTypesChange}
      onFilterFeeEarnerIdsChange={onMainMenuFilterFeeEarnerIdsChange}
      onFilterCaseStatusesChange={onMainMenuFilterCaseStatusesChange}
      onPersistFilters={persistMainMenuFilters}
      gridTemplateColumns={casesGridColumns}
      startColumnResize={casesStartResize}
      caseListFocusId={caseListFocusId}
      onCaseRowFocus={setCaseListFocusId}
      onSelectCase={onMainMenuSelectCase}
      sortKey={uiPrefs.main_menu_sort_key}
      sortDir={uiPrefs.main_menu_sort_dir}
      onSort={onMainMenuSort}
      onOpenNewMatter={onOpenNewMatter}
      onRefreshCases={onRefreshCases}
      keyboardActive={view === 'main-menu'}
    />
  ) : null

  const quotesFeeScalesButton = useMemo(
    () => (
      <>
        <button type="button" className="btn" onClick={() => setQuotesSubPanel('sources')}>
          Sources
        </button>
        <button type="button" className="btn" onClick={() => setQuotesSubPanel('fee-scales')}>
          Fee scales
        </button>
      </>
    ),
    [],
  )

  const quotesCasesPanel = token ? (
    <MainMenuCasesPanel
      cases={cases}
      casesErr={casesErr}
      users={caseListUsers}
      filterMatterTypes={quotesFilterMatterTypes}
      filterFeeEarnerUserIds={quotesFilterFeeEarnerUserIds}
      filterCaseStatuses={quotesFilterCaseStatuses}
      onFilterMatterTypesChange={onQuotesFilterMatterTypesChange}
      onFilterFeeEarnerIdsChange={onQuotesFilterFeeEarnerIdsChange}
      onFilterCaseStatusesChange={onQuotesFilterCaseStatusesChange}
      onPersistFilters={persistQuotesFilters}
      gridTemplateColumns={casesGridColumns}
      startColumnResize={casesStartResize}
      showSourceColumn
      caseListFocusId={caseListFocusId}
      onCaseRowFocus={setCaseListFocusId}
      onSelectCase={onMainMenuSelectCase}
      sortKey={uiPrefs.main_menu_sort_key}
      sortDir={uiPrefs.main_menu_sort_dir}
      onSort={onMainMenuSort}
      onOpenNewMatter={onOpenNewMatter}
      onRefreshCases={onRefreshCases}
      createButtonLabel="New quote"
      onCreateClick={() => setQuoteWizardOpen(true)}
      toolbarMiddle={quotesFeeScalesButton}
      contextMenuVariant="quotes"
      onQuoteConvert={onQuoteConvert}
      onQuoteClose={onQuoteClose}
      keyboardActive={view === 'quotes' && quotesSubPanel === 'list'}
    />
  ) : null

  useEffect(() => {
    if (auth.loading) {
      document.title = canaryDocumentTitle('Loading…')
      return
    }
    if (!auth.token) {
      document.title = canaryDocumentTitle('Sign in')
      return
    }
    if (auth.me && sessionNeedsVerifiedSecondFactor(auth.me)) {
      document.title = canaryDocumentTitle(
        userNeedsSecondFactorSetup(auth.me) ? 'Security setup' : 'Verify sign-in',
      )
      return
    }
    document.title = canaryDocumentTitle(canaryViewTitleSegment(view, caseTitleDetail))
  }, [auth.loading, auth.token, auth.me, view, caseTitleDetail])

  if (auth.loading) return <div className="center muted">Loading…</div>
  if (!auth.token) {
    if (resetToken) {
      return <ResetPasswordForm token={resetToken} onDone={clearResetToken} />
    }
    return (
      <LoginForm
        onLogin={auth.login}
        onPasskeyLogin={auth.loginWithPasskey}
        error={auth.loginError}
        onClearError={auth.clearLoginError}
      />
    )
  }

  if (auth.me && sessionNeedsPasswordChange(auth.me)) {
    return (
      <PasswordChangeSessionGate
        token={auth.token}
        me={auth.me}
        onLogout={auth.logout}
        refreshMe={auth.refreshMe}
        applySessionToken={auth.applySessionToken}
      />
    )
  }

  if (auth.me && sessionNeedsVerifiedSecondFactor(auth.me)) {
    return (
      <SecondFactorSessionGate
        token={auth.token}
        me={auth.me}
        onLogout={auth.logout}
        onPasskeyLogin={auth.loginWithPasskey}
        refreshMe={auth.refreshMe}
        applySessionToken={auth.applySessionToken}
        loginError={auth.loginError}
        onClearLoginError={auth.clearLoginError}
      />
    )
  }

  if (auth.me && userIsMasterRecovery(auth.me) && auth.token) {
    return (
      <div className="appShell">
        <header className="topbar">
          <div className="topbarMain">
            <nav className="topNav" aria-label="Recovery console">
              <span className="muted" style={{ padding: '6px 10px' }}>
                Master recovery
              </span>
            </nav>
          </div>
          <div className="topbarRight">
            <div className="muted">{auth.me.display_name}</div>
            <button type="button" className="btn" onClick={auth.logout}>
              Sign out
            </button>
          </div>
        </header>
        <main className="main main--mainMenu">
          <RecoveryConsole token={auth.token} />
        </main>
      </div>
    )
  }

  return (
    <div className="appShell appShell--sidebar">
      <AdminLoginUpdatePrompt token={auth.token} me={auth.me} canAdmin={canAdminConsole} />
      <AppSidebar
        view={view}
        goMainMenu={goMainMenu}
        onQuotes={() => {
          setView('quotes')
          setQuotesSubPanel('list')
        }}
        onCalendar={() => setView('calendar')}
        onTasks={() => setView('tasks')}
        onContacts={() => setView('contacts')}
        onDocusign={() => setView('docusign')}
        onAccounts={() => setView('accounts')}
        onReports={() => setView('reports')}
        onUserSettings={() => setView('user-settings')}
        onAdminConsole={() => setView('admin-console')}
        canAccessAccounts={canAccessAccounts}
        canAdminConsole={canAdminConsole}
        docusignEnabled={docusignEnabled === true}
        onLogout={confirmLogout}
      />
      <div className="appMainColumn">
        <main
          className={
            view === 'case-menu'
              ? 'main main--caseView'
              : view === 'main-menu' || view === 'quotes' || view === 'contacts' || view === 'tasks' || view === 'docusign' || view === 'accounts' || view === 'reports'
                ? 'main main--mainMenu'
                : 'main'
          }
        >
        {mainMenuCasesPanel ? (
          <div className={view === 'main-menu' ? 'mainMenuCasesHost' : 'mainMenuCasesHost mainMenuCasesHost--hidden'}>
            {mainMenuCasesPanel}
          </div>
        ) : null}
        {quotesCasesPanel ? (
          <div
            className={
              view === 'quotes' && quotesSubPanel === 'list'
                ? 'mainMenuCasesHost'
                : 'mainMenuCasesHost mainMenuCasesHost--hidden'
            }
          >
            {quotesNotice ? (
              <div className="notice" style={{ margin: '0 0 10px' }}>
                {quotesNotice}
              </div>
            ) : null}
            {quotesCasesPanel}
          </div>
        ) : null}
        {showNewMatter && token ? (
          <NewMatterModal
            token={token}
            currentUserId={auth.me?.id ?? ''}
            onClose={onCloseNewMatter}
            onCreated={onMainMenuCaseCreated}
            defaultStatus={newMatterFromQuotes ? 'quote' : 'open'}
          />
        ) : null}
        {quoteWizardOpen && token ? (
          <QuoteWizard
            token={token}
            open={quoteWizardOpen}
            onClose={() => setQuoteWizardOpen(false)}
            onOpenNewMatter={() => {
              setQuoteWizardOpen(false)
              setNewMatterFromQuotes(true)
              setShowNewMatter(true)
            }}
            onCaseCreatedRefresh={onRefreshCases}
            pendingNewCaseId={quoteWizardPendingCaseId}
            onClearPendingNewCase={() => setQuoteWizardPendingCaseId(null)}
            onAwaitingQuoteSave={setQuoteAwaitingSave}
          />
        ) : null}
        {quoteAwaitingSave && token ? (
          <QuoteSendPrompt
            token={token}
            caseId={quoteAwaitingSave.caseId}
            fileId={quoteAwaitingSave.fileId}
            preferredContactId={quoteAwaitingSave.preferredContactId}
            portalEnabled={quoteAwaitingSave.portalEnabled}
            open={quoteSendOpen}
            onClose={() => {
              setQuoteSendOpen(false)
              setQuoteAwaitingSave(null)
            }}
            onSendLetter={(caseId) => {
              openCaseView(caseId)
              setPendingComposeKind({ kind: 'letter' })
            }}
            onSendEmail={(caseId) => {
              openCaseView(caseId)
              setPendingComposeKind({
                kind: 'email',
                preferPrecedentReference: QUOTE_EMAIL_PRECEDENT_REFERENCE,
                attachmentFileId: quoteAwaitingSave.fileId,
              })
            }}
          />
        ) : null}
        {quoteConvertCase && token ? (
          <QuoteConvertModal
            token={token}
            quoteCase={quoteConvertCase}
            users={caseListUsers}
            onClose={() => setQuoteConvertCaseId(null)}
            onConverted={(result) => void onQuoteConverted(result)}
          />
        ) : null}
        {renderMainContent()}
      </main>
      </div>
    </div>
  )
}

type NewMatterPendingClient = {
  contact_id: string
  name: string
  email?: string | null
  phone?: string | null
}

function NewMatterModal({
  token,
  currentUserId,
  onClose,
  onCreated,
  defaultStatus = 'open',
}: {
  token: string
  currentUserId: string
  onClose: () => void
  onCreated: (created?: CaseOut) => void
  defaultStatus?: 'open' | 'quote'
}) {
  const { askConfirm } = useDialogs()
  const caseSources = useCaseSources(token)
  const [matterDescription, setMatterDescription] = useState('')
  const [matterHeadTypeId, setMatterHeadTypeId] = useState('')
  const [practiceArea, setPracticeArea] = useState('')
  const [sourceId, setSourceId] = useState('')
  const [sourceCustomName, setSourceCustomName] = useState('')
  const [feeEarner, setFeeEarner] = useState<string>(currentUserId)
  /** Active = open; Quote = quote (only these may be set on create). */
  const [newMatterStatus, setNewMatterStatus] = useState<'open' | 'quote'>(defaultStatus)
  const [portalEnabled, setPortalEnabled] = useState(false)
  const [step, setStep] = useState<'details' | 'property' | 'description' | 'contacts'>('details')
  const [propertyDraft, setPropertyDraft] = useState<CasePropertyPayload | null>(null)
  const [users, setUsers] = useState<UserSummary[]>([])
  const [matterHeadTypes, setMatterHeadTypes] = useState<MatterHeadTypeOut[]>([])
  const [matterHeadOpen, setMatterHeadOpen] = useState(false)
  const [matterSubOpen, setMatterSubOpen] = useState(false)
  const [sourceOpen, setSourceOpen] = useState(false)
  const [feeEarnerOpen, setFeeEarnerOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const [selectedGlobalContact, setSelectedGlobalContact] = useState<ContactOut | null>(null)
  const [contactErr, setContactErr] = useState<string | null>(null)
  /** Client contacts to link after the matter is created (Finish). */
  const [pendingClientLinks, setPendingClientLinks] = useState<NewMatterPendingClient[]>([])
  const [newContactFormKey, setNewContactFormKey] = useState(0)

  const hasClientOnMatter = pendingClientLinks.length > 0

  const selectedSubType = useMemo(() => {
    if (!practiceArea) return null
    return matterHeadTypes.flatMap((h) => h.sub_types).find((s) => s.id === practiceArea) ?? null
  }, [practiceArea, matterHeadTypes])

  const matterHeadOptions = useMemo(
    () => matterHeadTypes.map((head) => ({ value: head.id, label: head.name })),
    [matterHeadTypes],
  )

  const matterSubOptions = useMemo(() => {
    const head = matterHeadTypes.find((h) => h.id === matterHeadTypeId)
    return (head?.sub_types ?? []).map((sub) => ({ value: sub.id, label: sub.name }))
  }, [matterHeadTypes, matterHeadTypeId])

  const feeEarnerOptions = useMemo(
    () => users.map((u) => ({ value: u.id, label: `${u.display_name} (${u.email})` })),
    [users],
  )

  const closeDetailsDropdowns = useCallback((except?: 'head' | 'sub' | 'source' | 'feeEarner') => {
    if (except !== 'head') setMatterHeadOpen(false)
    if (except !== 'sub') setMatterSubOpen(false)
    if (except !== 'source') setSourceOpen(false)
    if (except !== 'feeEarner') setFeeEarnerOpen(false)
  }, [])

  useEffect(() => {
    setNewMatterStatus(defaultStatus)
  }, [defaultStatus])

  useEffect(() => {
    setPropertyDraft(null)
  }, [practiceArea])

  useEffect(() => {
    setPracticeArea('')
    setMatterSubOpen(false)
  }, [matterHeadTypeId])

  useEffect(() => {
    let cancelled = false
    async function loadUsers() {
      try {
        const data = await apiFetch<UserSummary[]>('/users', { token })
        if (!cancelled) {
          const active = (Array.isArray(data) ? data : []).filter((u) => u.is_active && u.can_be_fee_earner !== false)
          setUsers(active)
          setFeeEarner((prev) => {
            if (prev && active.some((u) => u.id === prev)) return prev
            if (currentUserId && active.some((u) => u.id === currentUserId)) return currentUserId
            return active[0]?.id ?? ''
          })
        }
      } catch {
        // ignore; keep dropdown empty
      }
    }
    void loadUsers()
    return () => {
      cancelled = true
    }
  }, [token])

  useEffect(() => {
    let cancelled = false
    async function loadMatterTypes() {
      try {
        const data = await apiFetch<MatterHeadTypeOut[]>('/matter-types', { token })
        if (!cancelled) setMatterHeadTypes(data)
      } catch {
        // ignore; keep dropdown empty
      }
    }
    void loadMatterTypes()
    return () => {
      cancelled = true
    }
  }, [token])

  return (
    <div className="modalOverlay" role="dialog" aria-modal="true">
      <div className="modal card modal--scrollBody">
        <div className="paneHead">
          <div>
            <h2>New matter</h2>
            <div className="muted">Reference is generated automatically.</div>
          </div>
          <button className="btn" onClick={onClose} disabled={busy}>
            Close
          </button>
        </div>
        <div className="modalBodyScroll">
        {step === 'details' ? (
        <div className="stack" style={{ marginTop: 12 }}>
          <SingleSelectDropdown
            label="Matter type"
            options={matterHeadOptions}
            value={matterHeadTypeId}
            onChange={setMatterHeadTypeId}
            open={matterHeadOpen}
            onOpenChange={(next) => {
              setMatterHeadOpen(next)
              if (next) closeDetailsDropdowns('head')
            }}
            disabled={busy}
            placeholder="— select —"
            emptyMessage={
              matterHeadOptions.length === 0
                ? 'No matter types available — add them under Admin → Matters.'
                : undefined
            }
          />
          {matterHeadTypeId ? (
            <SingleSelectDropdown
              label="Sub-type"
              options={matterSubOptions}
              value={practiceArea}
              onChange={setPracticeArea}
              open={matterSubOpen}
              onOpenChange={(next) => {
                setMatterSubOpen(next)
                if (next) closeDetailsDropdowns('sub')
              }}
              disabled={busy}
              placeholder="— select —"
              emptyMessage={
                matterSubOptions.length === 0
                  ? 'No sub-types for this matter type — add them under Admin → Matters.'
                  : undefined
              }
            />
          ) : (
            <p className="muted" style={{ margin: 0, fontSize: 13 }}>
              Choose a matter type, then pick a sub-type.
            </p>
          )}
          <CaseSourceField
            sources={caseSources}
            sourceId={sourceId}
            customName={sourceCustomName}
            onSourceIdChange={setSourceId}
            onCustomNameChange={setSourceCustomName}
            disabled={busy}
            open={sourceOpen}
            onOpenChange={(next) => {
              setSourceOpen(next)
              if (next) closeDetailsDropdowns('source')
            }}
          />
          <SingleSelectDropdown
            label="Fee earner"
            options={feeEarnerOptions}
            value={feeEarner}
            onChange={setFeeEarner}
            open={feeEarnerOpen}
            onOpenChange={(next) => {
              setFeeEarnerOpen(next)
              if (next) closeDetailsDropdowns('feeEarner')
            }}
            disabled={busy}
            placeholder="Select fee earner"
            emptyMessage={feeEarnerOptions.length === 0 ? 'No fee earners available.' : undefined}
          />
          <div className="field">
            <span>Status</span>
            <div className="row" style={{ gap: 20, marginTop: 6, flexWrap: 'wrap' }}>
              <label className="row" style={{ gap: 8, cursor: busy ? 'default' : 'pointer' }}>
                <input
                  type="radio"
                  name="new-matter-status"
                  checked={newMatterStatus === 'open'}
                  onChange={() => setNewMatterStatus('open')}
                  disabled={busy}
                />
                <span>Active</span>
              </label>
              <label className="row" style={{ gap: 8, cursor: busy ? 'default' : 'pointer' }}>
                <input
                  type="radio"
                  name="new-matter-status"
                  checked={newMatterStatus === 'quote'}
                  onChange={() => setNewMatterStatus('quote')}
                  disabled={busy}
                />
                <span>Quote</span>
              </label>
            </div>
          </div>
          <label className="row field" style={{ gap: 10, alignItems: 'flex-start', cursor: busy ? 'default' : 'pointer' }}>
            <input
              type="checkbox"
              checked={portalEnabled}
              disabled={busy}
              onChange={(e) => setPortalEnabled(e.target.checked)}
              style={{ marginTop: 3 }}
            />
            <span>
              Enable portal
              <span className="muted" style={{ display: 'block', fontSize: 13, marginTop: 2 }}>
                Allow client folder sharing and portal notifications for this matter.
              </span>
            </span>
          </label>
          {err ? <div className="error">{err}</div> : null}
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <button className="btn" onClick={onClose} disabled={busy}>
              Cancel
            </button>
            <button
              className="btn primary"
              disabled={busy}
              onClick={() => {
                setErr(null)
                setContactErr(null)
                if (!matterHeadTypeId) {
                  setErr('Select a matter type.')
                  return
                }
                if (!practiceArea) {
                  setErr('Select a sub-type.')
                  return
                }
                const sub = selectedSubType
                if (subTypeHasPropertyMenu(sub)) {
                  setPropertyDraft((d) => d ?? blankPropertyPayload())
                  setStep('property')
                } else {
                  setPropertyDraft(null)
                  setMatterDescription(buildNewMatterDescription(sub?.prefix ?? null, null))
                  setStep('description')
                }
              }}
            >
              Continue
            </button>
          </div>
        </div>
        ) : null}

        {step === 'property' && propertyDraft ? (
          <div className="stack" style={{ marginTop: 12 }}>
            <div className="paneHead" style={{ padding: 0, marginBottom: 8 }}>
              <div>
                <h2 style={{ margin: 0, fontSize: 18 }}>Property details</h2>
                <div className="muted">Same fields as the Property sub-menu on the matter.</div>
              </div>
              <button
                type="button"
                className="btn"
                onClick={() => {
                  setErr(null)
                  setStep('details')
                }}
                disabled={busy}
              >
                Back
              </button>
            </div>
            <div className="card" style={{ padding: 12 }}>
              <PropertyDetailsForm draft={propertyDraft} onChange={setPropertyDraft} disabled={busy} />
            </div>
            {err ? <div className="error">{err}</div> : null}
            <div className="row" style={{ justifyContent: 'flex-end' }}>
              <button
                type="button"
                className="btn primary"
                disabled={busy}
                onClick={() => {
                  setErr(null)
                  setMatterDescription(
                    buildNewMatterDescription(selectedSubType?.prefix ?? null, propertyDraft),
                  )
                  setStep('description')
                }}
              >
                Continue
              </button>
            </div>
          </div>
        ) : null}

        {step === 'description' ? (
          <div className="stack" style={{ marginTop: 12 }}>
            <div className="paneHead" style={{ padding: 0, marginBottom: 8 }}>
              <div>
                <h2 style={{ margin: 0, fontSize: 18 }}>Description</h2>
              </div>
              <button
                type="button"
                className="btn"
                onClick={() => {
                  setErr(null)
                  if (selectedSubType && subTypeHasPropertyMenu(selectedSubType)) {
                    setPropertyDraft((d) => d ?? blankPropertyPayload())
                    setStep('property')
                  } else {
                    setStep('details')
                  }
                }}
                disabled={busy}
              >
                Back
              </button>
            </div>
            <label className="field">
              <span>Description</span>
              <input
                value={matterDescription}
                onChange={(e) => setMatterDescription(e.target.value)}
                disabled={busy}
              />
            </label>
            {err ? <div className="error">{err}</div> : null}
            <div className="row" style={{ justifyContent: 'flex-end' }}>
              <button
                type="button"
                className="btn primary"
                disabled={busy || !matterDescription.trim()}
                onClick={() => {
                  setErr(null)
                  setContactErr(null)
                  setStep('contacts')
                }}
              >
                Continue
              </button>
            </div>
          </div>
        ) : null}

        {step === 'contacts' ? (
          <div className="card" style={{ marginTop: 12, padding: 12 }}>
            <div className="paneHead" style={{ padding: 0, marginBottom: 12 }}>
              <div>
                <h2 style={{ margin: 0, fontSize: 18 }}>Contacts</h2>
                <div className="muted">Link at least one client contact, then finish to create the matter.</div>
              </div>
              <button className="btn" onClick={() => setStep('description')} disabled={busy}>
                Back
              </button>
            </div>

            <div className="stack">
              <div className="muted">Clients for this matter (you can add more than one):</div>
              <div className="list scrollPanel--compact" style={{ marginTop: 12 }}>
                {pendingClientLinks.map((cc) => (
                  <div key={cc.contact_id} className="listCard row" style={{ justifyContent: 'space-between' }}>
                    <div>
                      <div className="listTitle">
                        {cc.name} <span className="muted">· {matterContactTypeLabel('client')}</span>
                      </div>
                      <div className="muted">{cc.email ?? cc.phone ?? '—'}</div>
                    </div>
                    <button
                      className="btn"
                      disabled={busy}
                      onClick={async () => {
                        const ok = await askConfirm({
                          title: 'Remove contact',
                          message: 'Remove this contact from the list?',
                          danger: true,
                          confirmLabel: 'Remove',
                        })
                        if (!ok) return
                        setContactErr(null)
                        setPendingClientLinks((prev) => prev.filter((p) => p.contact_id !== cc.contact_id))
                      }}
                    >
                      Remove
                    </button>
                  </div>
                ))}
                {pendingClientLinks.length === 0 ? <div className="muted">None added yet.</div> : null}
              </div>

              <label className="field">
                <span>Search existing global contacts</span>
                <ContactSearchPicker
                  token={token}
                  value={selectedGlobalContact?.id ?? null}
                  onChange={(_id, contact) => setSelectedGlobalContact(contact ?? null)}
                  disabled={busy}
                  filterContact={(c) => !pendingClientLinks.some((p) => p.contact_id === c.id)}
                  listMaxHeight={160}
                />
              </label>

              <div className="row" style={{ justifyContent: 'flex-end' }}>
                <button
                  className="btn primary"
                  disabled={
                    busy ||
                    !selectedGlobalContact ||
                    pendingClientLinks.some((p) => p.contact_id === selectedGlobalContact.id)
                  }
                  onClick={() => {
                    if (!selectedGlobalContact) return
                    const c = selectedGlobalContact
                    setContactErr(null)
                    setErr(null)
                    setPendingClientLinks((prev) => [
                      ...prev,
                      {
                        contact_id: c.id,
                        name: c.name,
                        email: c.email,
                        phone: c.phone,
                      },
                    ])
                    setSelectedGlobalContact(null)
                  }}
                >
                  Link as client
                </button>
              </div>

              <div className="card" style={{ padding: 12 }}>
                <GlobalContactCreateForm
                  key={newContactFormKey}
                  busy={busy}
                  submitLabel="Create & add as client"
                  intro={
                    <div className="muted" style={{ marginBottom: 8 }}>
                      Create new contact and add as client for this matter
                    </div>
                  }
                  onSubmit={async (payload) => {
                    setBusy(true)
                    setContactErr(null)
                    setErr(null)
                    try {
                      const created = await apiFetch<ContactOut>('/contacts', {
                        token,
                        method: 'POST',
                        json: payload,
                      })
                      setPendingClientLinks((prev) => [
                        ...prev,
                        {
                          contact_id: created.id,
                          name: created.name,
                          email: created.email,
                          phone: created.phone,
                        },
                      ])
                      setNewContactFormKey((k) => k + 1)
                    } catch (e: any) {
                      setContactErr(e?.message ?? 'Failed to create contact')
                      throw e
                    } finally {
                      setBusy(false)
                    }
                  }}
                />
              </div>

              {err ? <div className="error">{err}</div> : null}
              {contactErr ? <div className="error">{contactErr}</div> : null}
              <div className="row" style={{ justifyContent: 'flex-end', marginTop: 12 }}>
                <button
                  className="btn primary"
                  disabled={busy || !hasClientOnMatter}
                  onClick={async () => {
                    if (!hasClientOnMatter) return
                    if (!feeEarner) {
                      setErr('Select a fee earner.')
                      return
                    }
                    setBusy(true)
                    setErr(null)
                    setContactErr(null)
                    try {
                      const created = await apiFetch<CaseOut>('/cases', {
                        token,
                        json: {
                          matter_description: matterDescription.trim(),
                          status: newMatterStatus,
                          matter_sub_type_id: practiceArea || null,
                          fee_earner_user_id: feeEarner,
                          portal_enabled: portalEnabled,
                          ...resolveCaseSourcePayload(caseSources, sourceId, sourceCustomName),
                        },
                      })
                      for (const p of pendingClientLinks) {
                        await apiFetch(`/cases/${created.id}/contacts`, {
                          token,
                          json: {
                            contact_id: p.contact_id,
                            matter_contact_type: 'client',
                            matter_contact_reference: null,
                          },
                        })
                      }
                      if (selectedSubType && subTypeHasPropertyMenu(selectedSubType) && propertyDraft) {
                        const lines = [...propertyDraft.free_lines]
                        while (lines.length < 6) lines.push('')
                        await apiFetch(`/cases/${created.id}/property-details`, {
                          token,
                          method: 'PUT',
                          json: { ...propertyDraft, free_lines: lines.slice(0, 6) },
                        })
                      }
                      onCreated(created)
                    } catch (e: any) {
                      setErr(e?.message ?? 'Could not create matter')
                    } finally {
                      setBusy(false)
                    }
                  }}
                >
                  Finish
                </button>
              </div>
            </div>
          </div>
        ) : null}
        </div>
      </div>
    </div>
  )
}

function matterTypeLabel(c: CaseOut): string {
  const parts = [c.matter_head_type_name, c.matter_sub_type_name].filter(Boolean)
  return parts.length ? parts.join(' · ') : '—'
}

function feeEarnerLabel(c: CaseOut, users: UserSummary[]) {
  const u = users.find((x) => x.id === c.fee_earner_user_id)
  return u?.display_name ?? '—'
}

function caseMatchesMainMenuSearch(c: CaseOut, users: UserSummary[], search: string): boolean {
  const s = search.trim().toLowerCase()
  if (!s) return true
  const fe = feeEarnerLabel(c, users)
  const parts = [
    c.case_number,
    c.client_name ?? '',
    c.matter_description ?? '',
    formatCaseStatusLabel(c.status),
    fe,
    c.source_name ?? '',
  ]
  return parts.join(' ').toLowerCase().includes(s)
}

function filterMainMenuCases(
  cases: CaseOut[],
  matterTypes: string[],
  feeEarnerUserIds: string[],
  caseStatuses: MainMenuCaseStatusFilter[],
): CaseOut[] {
  let result = cases
  if (matterTypes.length > 0) {
    result = result.filter((c) => matterTypes.includes(matterTypeLabel(c)))
  }
  if (feeEarnerUserIds.length > 0) {
    result = result.filter((c) => c.fee_earner_user_id && feeEarnerUserIds.includes(c.fee_earner_user_id))
  }
  if (caseStatuses.length > 0) {
    result = result.filter((c) => caseStatuses.includes(c.status as MainMenuCaseStatusFilter))
  }
  return result
}

function buildCaseTableRows(
  cases: CaseOut[],
  users: UserSummary[],
  search: string,
  filters: {
    matterTypes: string[]
    feeEarnerUserIds: string[]
    caseStatuses: MainMenuCaseStatusFilter[]
    excludeQuoteMatters?: boolean
    quotesOnlyMatters?: boolean
  },
  sortKey: 'reference' | 'client' | 'matter' | 'feeEarner' | 'status' | 'source' | 'created',
  sortDir: 'asc' | 'desc',
): CaseOut[] {
  const s = search.trim()
  const pool = filters.quotesOnlyMatters
    ? cases.filter((c) => c.status === 'quote' || c.status === 'quote_closed')
    : filters.excludeQuoteMatters
      ? cases.filter((c) => c.status !== 'quote' && c.status !== 'quote_closed')
      : cases
  const filtered = s
    ? pool.filter((c) => caseMatchesMainMenuSearch(c, users, search))
    : filterMainMenuCases(pool, filters.matterTypes, filters.feeEarnerUserIds, filters.caseStatuses)
  const dir = sortDir === 'asc' ? 1 : -1
  return [...filtered].sort((a, b) => {
    const av =
      sortKey === 'reference'
        ? a.case_number
        : sortKey === 'client'
          ? a.client_name ?? ''
          : sortKey === 'matter'
            ? a.matter_description ?? ''
            : sortKey === 'feeEarner'
              ? feeEarnerLabel(a, users)
              : sortKey === 'status'
                ? a.status
                : sortKey === 'source'
                  ? a.source_name ?? ''
                : sortKey === 'created'
                  ? a.created_at
                  : ''
    const bv =
      sortKey === 'reference'
        ? b.case_number
        : sortKey === 'client'
          ? b.client_name ?? ''
          : sortKey === 'matter'
            ? b.matter_description ?? ''
            : sortKey === 'feeEarner'
              ? feeEarnerLabel(b, users)
              : sortKey === 'status'
                ? b.status
                : sortKey === 'source'
                  ? b.source_name ?? ''
                : sortKey === 'created'
                  ? b.created_at
                  : ''
    return String(av).localeCompare(String(bv)) * dir
  })
}

function CasesTable({
  cases,
  users,
  search,
  filterMatterTypes,
  filterFeeEarnerUserIds,
  filterCaseStatuses,
  caseListFocusId,
  onCaseRowFocus,
  onSelect,
  sortKey,
  sortDir,
  onSort,
  gridTemplateColumns,
  startColumnResize,
  showSourceColumn = false,
  contextMenuVariant = 'main',
  onQuoteConvert,
  onQuoteClose,
  keyboardEnabled = true,
}: {
  cases: CaseOut[]
  users: UserSummary[]
  search: string
  filterMatterTypes: string[]
  filterFeeEarnerUserIds: string[]
  filterCaseStatuses: MainMenuCaseStatusFilter[]
  caseListFocusId: string | null
  onCaseRowFocus: (id: string | null) => void
  onSelect: (id: string, opts?: { docPanel?: CaseOpenDocPanel }) => void
  sortKey: 'reference' | 'client' | 'matter' | 'feeEarner' | 'status' | 'source' | 'created'
  sortDir: 'asc' | 'desc'
  onSort: (k: 'reference' | 'client' | 'matter' | 'feeEarner' | 'status' | 'source' | 'created') => void
  gridTemplateColumns?: string
  startColumnResize: (colIndex: number, startClientX: number, measureRow?: HTMLElement | null) => void
  showSourceColumn?: boolean
  contextMenuVariant?: 'main' | 'quotes'
  onQuoteConvert?: (caseId: string) => void
  onQuoteClose?: (caseId: string) => void
  keyboardEnabled?: boolean
}) {
  const [caseCtx, setCaseCtx] = useState<null | { id: string; x: number; y: number; focusIndex: number }>(null)
  const caseCtxRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!caseCtx) return
    function handleMouseDown(e: MouseEvent) {
      const t = e.target as Node
      if (caseCtxRef.current?.contains(t)) return
      setCaseCtx(null)
    }
    document.addEventListener('mousedown', handleMouseDown)
    return () => document.removeEventListener('mousedown', handleMouseDown)
  }, [caseCtx])

  const rows = useMemo(
    () =>
      buildCaseTableRows(
        cases,
        users,
        search,
        {
          matterTypes: filterMatterTypes,
          feeEarnerUserIds: filterFeeEarnerUserIds,
          caseStatuses: filterCaseStatuses,
          excludeQuoteMatters: contextMenuVariant === 'main',
          quotesOnlyMatters: contextMenuVariant === 'quotes',
        },
        sortKey,
        sortDir,
      ),
    [cases, users, search, filterMatterTypes, filterFeeEarnerUserIds, filterCaseStatuses, sortKey, sortDir, contextMenuVariant],
  )

  const rowIds = useMemo(() => rows.map((r) => r.id), [rows])

  const contextMenuLabel = (action: CaseContextMenuActionKind): string => {
    switch (action) {
      case 'open':
        return 'Open'
      case 'accounts':
        return 'Accounts'
      case 'convert':
        return 'Convert'
      case 'close':
        return 'Close'
    }
  }

  const activateContextAction = useCallback(
    (action: CaseContextMenuActionKind, id: string) => {
      switch (action) {
        case 'open':
          onSelect(id)
          break
        case 'accounts':
          onSelect(id, { docPanel: 'accounts' })
          break
        case 'convert':
          onQuoteConvert?.(id)
          break
        case 'close':
          onQuoteClose?.(id)
          break
      }
    },
    [onQuoteClose, onQuoteConvert, onSelect],
  )

  const openContextMenuForCase = useCallback((id: string) => {
    const el = document.querySelector(`[data-case-row-id="${CSS.escape(id)}"]`) as HTMLElement | null
    const rect = el?.getBoundingClientRect()
    setCaseCtx({
      id,
      x: rect ? rect.left + 16 : 200,
      y: rect ? rect.top + Math.min(rect.height, 32) : 200,
      focusIndex: 0,
    })
  }, [])

  useEffect(() => {
    if (!keyboardEnabled) return

    function onKeyDown(e: KeyboardEvent) {
      if (isEditableKeyboardTarget(e.target) || isModalBlockingKeyboard()) return

      if (caseCtx) {
        const ctxCase = cases.find((c) => c.id === caseCtx.id)
        const actions = buildCaseContextMenuActions(contextMenuVariant, ctxCase?.status)
        if (actions.length === 0) return

        if (e.key === 'Escape') {
          e.preventDefault()
          setCaseCtx(null)
          return
        }
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault()
          const action = actions[caseCtx.focusIndex] ?? actions[0]
          activateContextAction(action, caseCtx.id)
          setCaseCtx(null)
          return
        }
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          e.preventDefault()
          const delta = e.key === 'ArrowDown' ? 1 : -1
          setCaseCtx((prev) => {
            if (!prev) return prev
            const nextIndex = (prev.focusIndex + delta + actions.length) % actions.length
            return { ...prev, focusIndex: nextIndex }
          })
          return
        }
        return
      }

      if (e.shiftKey) {
        if (e.key === 'Enter') {
          if (rowIds.length === 0) return
          e.preventDefault()
          const id = caseListFocusId ?? rowIds[0]
          if (!id) return
          onCaseRowFocus(id)
          openContextMenuForCase(id)
        }
        return
      }

      if (e.key === 'Enter') {
        if (!caseListFocusId) return
        e.preventDefault()
        onSelect(caseListFocusId)
        return
      }

      if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
      if (rowIds.length === 0) return

      e.preventDefault()
      const currentIndex = caseListFocusId ? rowIds.indexOf(caseListFocusId) : -1
      let nextIndex: number
      if (currentIndex < 0) {
        nextIndex = e.key === 'ArrowDown' ? 0 : rowIds.length - 1
      } else {
        nextIndex = e.key === 'ArrowDown' ? Math.min(currentIndex + 1, rowIds.length - 1) : Math.max(currentIndex - 1, 0)
      }
      const nextId = rowIds[nextIndex]
      if (!nextId) return
      onCaseRowFocus(nextId)
      scrollCaseRowIntoView(nextId)
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [
    activateContextAction,
    caseCtx,
    caseListFocusId,
    cases,
    contextMenuVariant,
    keyboardEnabled,
    onCaseRowFocus,
    onSelect,
    openContextMenuForCase,
    rowIds,
  ])

  const columns = useMemo(() => {
    const base = [
      ['reference', 'Reference'],
      ['client', 'Client name'],
      ['matter', 'Description'],
      ['feeEarner', 'Fee earner'],
    ] as const
    if (showSourceColumn) {
      return [...base, ['source', 'Source']] as const
    }
    return [...base, ['status', 'Status']] as const
  }, [showSourceColumn])

  const lastColIndex = columns.length - 1
  const ctxCase = caseCtx ? cases.find((c) => c.id === caseCtx.id) : null

  return (
    <div className="card casesTableCard" style={{ padding: 0, overflow: 'hidden' }}>
      <div className="casesTableScroll">
        <div className="table">
        <div className="tr th" style={gridTemplateColumns ? { gridTemplateColumns } : undefined}>
          {columns.map(([k, label], colIndex) => (
            <div key={k} className="thCell">
              <button type="button" className="thbtn" onClick={() => onSort(k)}>
                {label}
              </button>
              {colIndex < lastColIndex ? (
                <div
                  className="colResizeHandle"
                  role="separator"
                  aria-orientation="vertical"
                  aria-label={`Resize ${label} column`}
                  onMouseDown={(e) => {
                    e.preventDefault()
                    startColumnResize(colIndex, e.clientX, e.currentTarget.closest('.tr.th') as HTMLElement | null)
                  }}
                />
              ) : null}
            </div>
          ))}
        </div>
        {rows.map((c) => {
          const rowActive = caseListFocusId === c.id
          const rowInactive = c.status === 'closed' || c.status === 'archived'
          return (
            <button
              key={c.id}
              type="button"
              data-case-row-id={c.id}
              className={['tr', 'rowbtn', rowActive ? 'active' : '', rowInactive ? 'casesRowInactive' : '']
                .filter(Boolean)
                .join(' ')}
              style={gridTemplateColumns ? { gridTemplateColumns } : undefined}
              onClick={() => onCaseRowFocus(c.id)}
              onDoubleClick={() => onSelect(c.id)}
              onContextMenu={(e) => {
                e.preventDefault()
                onCaseRowFocus(c.id)
                setCaseCtx({ id: c.id, x: e.clientX, y: e.clientY, focusIndex: 0 })
              }}
            >
              <div className="td mono" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                {caseHasRevokedUserAccess(c) ? (
                  <span title="Access restricted for some users" aria-hidden style={{ opacity: 0.85 }}>
                    🔒
                  </span>
                ) : null}
                {c.case_number}
              </div>
              <div className="td">{c.client_name ?? '—'}</div>
              <div className="td">{c.matter_description}</div>
              <div className="td">{feeEarnerLabel(c, users)}</div>
              {showSourceColumn ? (
                <div className="td">{c.source_name ?? '—'}</div>
              ) : (
                <div className="td">{formatCaseStatusLabel(c.status)}</div>
              )}
            </button>
          )
        })}
        {rows.length === 0 ? <div className="muted" style={{ padding: 12 }}>No cases match.</div> : null}
        </div>
      </div>
      {caseCtx ? (
        <div
          ref={caseCtxRef}
          className="docContextMenu"
          role="menu"
          style={{ left: caseCtx.x, top: caseCtx.y, zIndex: 30 }}
          onMouseDown={(e) => e.stopPropagation()}
        >
          {buildCaseContextMenuActions(contextMenuVariant, ctxCase?.status).map((action, index) => (
            <div
              key={action}
              className={`docContextItem${caseCtx.focusIndex === index ? ' docContextItem--focused' : ''}`}
              role="menuitem"
              tabIndex={-1}
              onMouseEnter={() => setCaseCtx((prev) => (prev ? { ...prev, focusIndex: index } : prev))}
              onClick={() => {
                const id = caseCtx.id
                setCaseCtx(null)
                activateContextAction(action, id)
              }}
            >
              {contextMenuLabel(action)}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}

const MAIN_MENU_STATUS_FILTER_OPTIONS: { value: MainMenuCaseStatusFilter; label: string }[] = [
  { value: 'open', label: 'Active' },
  { value: 'post_completion', label: 'Post-completion' },
  { value: 'closed', label: 'Closed' },
  { value: 'archived', label: 'Archived' },
]

const QUOTES_MENU_STATUS_FILTER_OPTIONS: { value: MainMenuCaseStatusFilter; label: string }[] = [
  { value: 'quote', label: 'Quote' },
  { value: 'quote_closed', label: 'Closed' },
]

const MainMenuCasesPanel = memo(function MainMenuCasesPanel({
  cases,
  casesErr,
  users,
  filterMatterTypes,
  filterFeeEarnerUserIds,
  filterCaseStatuses,
  onFilterMatterTypesChange,
  onFilterFeeEarnerIdsChange,
  onFilterCaseStatusesChange,
  onPersistFilters,
  gridTemplateColumns,
  startColumnResize,
  caseListFocusId,
  onCaseRowFocus,
  onSelectCase,
  sortKey,
  sortDir,
  onSort,
  onOpenNewMatter,
  onRefreshCases,
  createButtonLabel = 'New matter',
  onCreateClick,
  toolbarMiddle,
  showSourceColumn = false,
  contextMenuVariant = 'main',
  onQuoteConvert,
  onQuoteClose,
  keyboardActive = false,
}: {
  cases: CaseOut[]
  casesErr: string | null
  users: UserSummary[]
  filterMatterTypes: string[]
  filterFeeEarnerUserIds: string[]
  filterCaseStatuses: MainMenuCaseStatusFilter[]
  onFilterMatterTypesChange: (value: string[]) => void
  onFilterFeeEarnerIdsChange: (value: string[]) => void
  onFilterCaseStatusesChange: (value: MainMenuCaseStatusFilter[]) => void
  onPersistFilters: (
    matterTypes: string[],
    feeEarnerUserIds: string[],
    caseStatuses: MainMenuCaseStatusFilter[],
  ) => void
  gridTemplateColumns?: string
  startColumnResize: (colIndex: number, startClientX: number, measureRow?: HTMLElement | null) => void
  caseListFocusId: string | null
  onCaseRowFocus: (id: string | null) => void
  onSelectCase: (id: string, opts?: { docPanel?: CaseOpenDocPanel }) => void
  sortKey: 'reference' | 'client' | 'matter' | 'feeEarner' | 'status' | 'source' | 'created'
  sortDir: 'asc' | 'desc'
  onSort: (k: 'reference' | 'client' | 'matter' | 'feeEarner' | 'status' | 'source' | 'created') => void
  onOpenNewMatter: () => void
  onRefreshCases: () => void
  createButtonLabel?: string
  onCreateClick?: () => void
  toolbarMiddle?: ReactNode
  showSourceColumn?: boolean
  contextMenuVariant?: 'main' | 'quotes'
  onQuoteConvert?: (caseId: string) => void
  onQuoteClose?: (caseId: string) => void
  keyboardActive?: boolean
}) {
  const [caseSearch, setCaseSearch] = useState('')
  const [filterOpen, setFilterOpen] = useState(false)
  const [openFilterField, setOpenFilterField] = useState<'matterType' | 'feeEarner' | 'status' | null>(null)

  const matterTypeOptions = useMemo(() => {
    const set = new Set<string>()
    for (const c of cases) {
      set.add(matterTypeLabel(c))
    }
    return Array.from(set)
      .sort((a, b) => a.localeCompare(b))
      .map((label) => ({ value: label, label }))
  }, [cases])

  const feeEarnerOptions = useMemo(() => {
    const byId = new Map<string, UserSummary>()
    for (const u of users) {
      if (u.can_be_fee_earner === false) continue
      if (!byId.has(u.id)) byId.set(u.id, u)
    }
    return Array.from(byId.values())
      .sort((a, b) => a.display_name.localeCompare(b.display_name))
      .map((u) => ({ value: u.id, label: u.display_name }))
  }, [users])

  const activeFilterCount =
    filterMatterTypes.length + filterFeeEarnerUserIds.length + filterCaseStatuses.length

  const statusFilterOptions =
    contextMenuVariant === 'quotes' ? QUOTES_MENU_STATUS_FILTER_OPTIONS : MAIN_MENU_STATUS_FILTER_OPTIONS

  const toggleFilterOpen = () => {
    setFilterOpen((open) => {
      const next = !open
      if (!next) {
        setOpenFilterField(null)
        onPersistFilters(filterMatterTypes, filterFeeEarnerUserIds, filterCaseStatuses)
      }
      return next
    })
  }

  const clearAllFilters = () => {
    setOpenFilterField(null)
    onFilterMatterTypesChange([])
    onFilterFeeEarnerIdsChange([])
    onFilterCaseStatusesChange([])
    onPersistFilters([], [], [])
  }

  return (
    <div className="mainMenuShell mainMenuShell--mainMenu">
      {casesErr ? <div className="error">{casesErr}</div> : null}
      <div className={`mainMenuFilterBar${filterOpen ? ' mainMenuFilterBar--dropdownOpen' : ''}`}>
        <div className="row mainMenuFilterRow mainMenuFilterRow--toolbar mainMenuFilterRow--searchRight">
          <div className="mainMenuFilterRowLeft">
            <button type="button" className="btn primary toolbarLeadBtn" onClick={onCreateClick ?? onOpenNewMatter}>
              {createButtonLabel}
            </button>
            {toolbarMiddle}
            <button type="button" className="btn" onClick={onRefreshCases}>
              Refresh
            </button>
          </div>
          <div className="mainMenuFilterRowRight">
            <div className="caseToolbarDropdownWrap mainMenuFilterToolbarGroup">
              <button
                type="button"
                className="btn mainMenuFilterBtn"
                aria-expanded={filterOpen}
                aria-haspopup="true"
                aria-controls="main-menu-filter-menu"
                id="main-menu-filter-button"
                onClick={toggleFilterOpen}
              >
                <span className="mainMenuFilterBtnInner">
                  <svg
                    className="mainMenuFilterBtnIcon"
                    width={16}
                    height={16}
                    viewBox="0 0 24 24"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                    aria-hidden
                  >
                    <polygon
                      points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      fill="none"
                    />
                  </svg>
                  <span>Filter</span>
                  <span className="mainMenuFilterBtnCount">({activeFilterCount})</span>
                </span>
              </button>
              {activeFilterCount > 0 ? (
                <button
                  type="button"
                  className="mainMenuFilterClearBtn mainMenuFilterClearBtn--toolbar"
                  aria-label="Clear all filters"
                  onClick={clearAllFilters}
                >
                  ×
                </button>
              ) : null}
              <div
                id="main-menu-filter-menu"
                className={`caseToolbarDropdown mainMenuFilterDropdown${filterOpen ? '' : ' mainMenuFilterDropdown--hidden'}`}
                role="group"
                aria-labelledby="main-menu-filter-button"
                aria-hidden={!filterOpen}
                onMouseDown={(e) => e.stopPropagation()}
              >
                <div className="stack mainMenuFilterDropdownBody">
                  <MainMenuFilterCheckboxDropdown
                    label="Matter type"
                    options={matterTypeOptions}
                    selected={filterMatterTypes}
                    onChange={onFilterMatterTypesChange}
                    open={openFilterField === 'matterType'}
                    onOpenChange={(open) => setOpenFilterField(open ? 'matterType' : null)}
                  />
                  <MainMenuFilterCheckboxDropdown
                    label="Fee earner"
                    options={feeEarnerOptions}
                    selected={filterFeeEarnerUserIds}
                    onChange={onFilterFeeEarnerIdsChange}
                    open={openFilterField === 'feeEarner'}
                    onOpenChange={(open) => setOpenFilterField(open ? 'feeEarner' : null)}
                  />
                  <MainMenuFilterCheckboxDropdown
                    label="Status"
                    options={statusFilterOptions}
                    selected={filterCaseStatuses}
                    onChange={(next) => onFilterCaseStatusesChange(next as MainMenuCaseStatusFilter[])}
                    open={openFilterField === 'status'}
                    onOpenChange={(open) => setOpenFilterField(open ? 'status' : null)}
                  />
                </div>
              </div>
            </div>
            <SearchInput
              placeholder="Search"
              value={caseSearch}
              onChange={(e) => setCaseSearch(e.target.value)}
              onClear={() => setCaseSearch('')}
              className="mainMenuSearchInput"
              aria-label="Search cases"
            />
          </div>
        </div>
      </div>
      {null}
      <CasesTable
        cases={cases}
        users={users}
        search={caseSearch}
        filterMatterTypes={filterMatterTypes}
        filterFeeEarnerUserIds={filterFeeEarnerUserIds}
        filterCaseStatuses={filterCaseStatuses}
        gridTemplateColumns={gridTemplateColumns}
        startColumnResize={startColumnResize}
        showSourceColumn={showSourceColumn}
        caseListFocusId={caseListFocusId}
        onCaseRowFocus={onCaseRowFocus}
        onSelect={onSelectCase}
        sortKey={sortKey}
        sortDir={sortDir}
        onSort={onSort}
        contextMenuVariant={contextMenuVariant}
        onQuoteConvert={onQuoteConvert}
        onQuoteClose={onQuoteClose}
        keyboardEnabled={keyboardActive && !filterOpen && openFilterField === null}
      />
    </div>
  )
})


function UserSettingsPage({
  token,
  refreshMe,
  applySessionToken,
  securitySetupOnly,
  passwordChangeRequiredOnly,
}: {
  token: string
  refreshMe: () => Promise<void>
  applySessionToken: (accessToken: string) => void
  securitySetupOnly?: boolean
  passwordChangeRequiredOnly?: boolean
}) {
  const { askConfirm } = useDialogs()
  const [account, setAccount] = useState<UserPublic | null>(null)
  const {
    appFont,
    setAppFont,
    appAccent,
    setAppAccent,
    appPageBg,
    setAppPageBg,
    appMode,
    setAppMode,
    prefs: appearancePrefs,
  } = useAppearanceFormState(account)
  const [themeSavedHint, setThemeSavedHint] = useState(false)
  const [columnsResetHint, setColumnsResetHint] = useState(false)
  const [themeSaveErr, setThemeSaveErr] = useState<string | null>(null)

  const [busy, setBusy] = useState(false)

  const [caldav, setCaldav] = useState<UserCalDAVStatusOut | null>(null)
  const [caldavLoadErr, setCaldavLoadErr] = useState<string | null>(null)
  const [caldavActionErr, setCaldavActionErr] = useState<string | null>(null)
  const [caldavBusy, setCaldavBusy] = useState(false)
  const [caldavProvision, setCaldavProvision] = useState<UserCalDAVProvisionOut | null>(null)
  const [caldavCopyHint, setCaldavCopyHint] = useState<string | null>(null)

  const [pwdCurrent, setPwdCurrent] = useState('')
  const [pwdNew, setPwdNew] = useState('')
  const [pwdConfirm, setPwdConfirm] = useState('')
  const [pwdErr, setPwdErr] = useState<string | null>(null)
  const [pwdOk, setPwdOk] = useState(false)
  const [secBusy, setSecBusy] = useState(false)
  const [faSetup, setFaSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null)
  const [faCode, setFaCode] = useState('')
  const [faErr, setFaErr] = useState<string | null>(null)
  const [faOk, setFaOk] = useState(false)
  const [disablePwd, setDisablePwd] = useState('')
  const [disableTotp, setDisableTotp] = useState('')
  const [cancelSetupPwd, setCancelSetupPwd] = useState('')
  const [setupResumePwd, setSetupResumePwd] = useState('')
  const [accountLoadErr, setAccountLoadErr] = useState<string | null>(null)

  const [passkeys, setPasskeys] = useState<WebAuthnCredentialOut[]>([])
  const [pkErr, setPkErr] = useState<string | null>(null)
  const [pkLabel, setPkLabel] = useState('')

  const [emailPref, setEmailPref] = useState<'desktop' | 'outlook_web'>('desktop')
  const [emailDesktopClient, setEmailDesktopClient] = useState<'outlook' | 'other'>('outlook')
  const [outlookUrl, setOutlookUrl] = useState(DEFAULT_OUTLOOK_WEB_MAIL_URL)
  const [emailSaveErr, setEmailSaveErr] = useState<string | null>(null)
  const [emailSaveOk, setEmailSaveOk] = useState(false)
  const [emailBusy, setEmailBusy] = useState(false)
  const [signatureBusy, setSignatureBusy] = useState(false)
  const [signatureErr, setSignatureErr] = useState<string | null>(null)
  const [signatureFileKey, setSignatureFileKey] = useState(0)
  const [signatureScale, setSignatureScale] = useState(7)

  async function load() {
    setBusy(true)
    setAccountLoadErr(null)
    setCaldavLoadErr(null)
    try {
      try {
        const me = await apiFetch<UserPublic>('/auth/me', { token })
        setAccount(me)
      } catch (e: unknown) {
        setAccount(null)
        setAccountLoadErr((e as ApiError).message ?? 'Failed to load account')
      }
      if (!securitySetupOnly && !passwordChangeRequiredOnly) {
        try {
          const st = await apiFetch<UserCalDAVStatusOut>('/users/me/calendar', { token })
          setCaldav(st)
        } catch (e: unknown) {
          setCaldav(null)
          setCaldavLoadErr((e as ApiError).message ?? 'Failed to load CalDAV status')
        }
      } else {
        setCaldav(null)
        setCaldavLoadErr(null)
      }
      if (!passwordChangeRequiredOnly) {
        try {
          const rows = await apiFetch<WebAuthnCredentialOut[]>('/auth/webauthn/credentials', { token })
          setPasskeys(rows)
          setPkErr(null)
        } catch (e: unknown) {
          setPasskeys([])
          setPkErr((e as ApiError).message ?? 'Could not load passkeys')
        }
      } else {
        setPasskeys([])
        setPkErr(null)
      }
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    void load()
  }, [token, securitySetupOnly, passwordChangeRequiredOnly])

  useEffect(() => {
    if (!account) return
    setEmailPref(account.email_launch_preference ?? 'desktop')
    setEmailDesktopClient(account.email_desktop_client === 'other' ? 'other' : 'outlook')
    setOutlookUrl((account.email_outlook_web_url ?? '').trim() || DEFAULT_OUTLOOK_WEB_MAIL_URL)
    setSignatureScale(account.signature_scale ?? 7)
  }, [account])

  async function confirmOutlookWebWithoutGraph(): Promise<boolean> {
    if (!account || isOrgMicrosoftGraphConfigured(account)) return true
    return askConfirm({
      title: 'Outlook web without Microsoft Graph',
      message: OUTLOOK_WEB_WITHOUT_GRAPH_CONFIRM_MESSAGE,
      confirmLabel: 'Yes',
      cancelLabel: 'Nevermind',
    })
  }

  async function saveSignatureScale(scale: number) {
    setSignatureBusy(true)
    setSignatureErr(null)
    try {
      const me = await apiFetch<UserPublic>('/users/me/signature-settings', {
        token,
        method: 'PUT',
        json: { signature_scale: scale },
      })
      setAccount(me)
      await refreshMe()
    } catch (e: unknown) {
      setSignatureErr((e as ApiError).message ?? 'Could not save signature scale')
    } finally {
      setSignatureBusy(false)
    }
  }

  async function saveEmailHandling() {
    setEmailSaveErr(null)
    setEmailSaveOk(false)
    if (emailPref === 'outlook_web') {
      const proceed = await confirmOutlookWebWithoutGraph()
      if (!proceed) return
    }
    setEmailBusy(true)
    try {
      const u = await apiFetch<UserPublic>('/users/me/email-handling', {
        method: 'PUT',
        token,
        json: {
          email_launch_preference: emailPref,
          email_outlook_web_url: emailPref === 'outlook_web' ? outlookUrl.trim() : null,
          email_desktop_client: emailPref === 'desktop' ? emailDesktopClient : undefined,
        },
      })
      setAccount(u)
      await refreshMe()
      setEmailSaveOk(true)
    } catch (e: unknown) {
      setEmailSaveErr((e as ApiError).message ?? 'Save failed')
    } finally {
      setEmailBusy(false)
    }
  }

  async function submitPasswordChange() {
    setPwdErr(null)
    setPwdOk(false)
    if (pwdNew.length < 12) {
      setPwdErr('New password must be at least 12 characters.')
      return
    }
    if (pwdNew !== pwdConfirm) {
      setPwdErr('New password and confirmation do not match.')
      return
    }
    setSecBusy(true)
    try {
      const res = await apiFetch<ChangePasswordResponse>('/auth/change-password', {
        method: 'POST',
        token,
        json: { current_password: pwdCurrent, new_password: pwdNew },
      })
      applySessionToken(res.access_token)
      setAccount(res.user)
      await refreshMe()
      setPwdOk(true)
      setPwdCurrent('')
      setPwdNew('')
      setPwdConfirm('')
    } catch (e: unknown) {
      setPwdErr((e as ApiError).message ?? 'Could not change password')
    } finally {
      setSecBusy(false)
    }
  }

  async function start2faSetup(resumePassword?: string) {
    setFaErr(null)
    setFaOk(false)
    setSecBusy(true)
    try {
      const pwd = (resumePassword ?? setupResumePwd).trim()
      const res = await apiFetch<{ secret: string; otpauth_uri: string }>('/auth/2fa/setup', {
        method: 'POST',
        token,
        json: account?.pending_authenticator_setup || pwd ? { password: pwd || null } : {},
      })
      setFaSetup(res)
      setFaCode('')
    } catch (e: unknown) {
      setFaErr((e as ApiError).message ?? 'Could not start 2FA setup')
    } finally {
      setSecBusy(false)
    }
  }

  async function verify2fa() {
    setFaErr(null)
    setFaOk(false)
    const code = faCode.trim()
    if (code.length < 4) {
      setFaErr('Enter the code from your authenticator app.')
      return
    }
    setSecBusy(true)
    try {
      const res = await apiFetch<Verify2FASessionResponse>('/auth/2fa/verify', {
        method: 'POST',
        token,
        json: { code },
      })
      applySessionToken(res.access_token)
      setAccount(res.user)
      setFaSetup(null)
      setFaCode('')
      setFaOk(true)
      setCancelSetupPwd('')
    } catch (e: unknown) {
      setFaErr((e as ApiError).message ?? 'Verification failed')
    } finally {
      setSecBusy(false)
    }
  }

  async function disable2fa() {
    setFaErr(null)
    setFaOk(false)
    setSecBusy(true)
    try {
      await apiFetch<null>('/auth/2fa/disable', {
        method: 'POST',
        token,
        json: { password: disablePwd, totp_code: disableTotp.trim() },
      })
      setDisablePwd('')
      setDisableTotp('')
      const me = await apiFetch<UserPublic>('/auth/me', { token })
      setAccount(me)
      setFaOk(true)
      await refreshMe()
    } catch (e: unknown) {
      setFaErr((e as ApiError).message ?? 'Could not disable 2FA')
    } finally {
      setSecBusy(false)
    }
  }

  async function cancel2faSetup() {
    setFaErr(null)
    setFaOk(false)
    setSecBusy(true)
    try {
      await apiFetch<null>('/auth/2fa/cancel-setup', {
        method: 'POST',
        token,
        json: { password: cancelSetupPwd },
      })
      setCancelSetupPwd('')
      setFaSetup(null)
      setFaCode('')
      const me = await apiFetch<UserPublic>('/auth/me', { token })
      setAccount(me)
      await refreshMe()
    } catch (e: unknown) {
      setFaErr((e as ApiError).message ?? 'Could not cancel setup')
    } finally {
      setSecBusy(false)
    }
  }

  async function registerPasskey() {
    setPkErr(null)
    setFaErr(null)
    setSecBusy(true)
    try {
      const options = await apiFetch<PublicKeyCredentialCreationOptionsJSON>('/auth/webauthn/register/begin', {
        method: 'POST',
        token,
      })
      const att = await startRegistration({ optionsJSON: options })
      const session = await apiFetch<TokenResponse>('/auth/webauthn/register/finish', {
        method: 'POST',
        token,
        json: { credential: att, label: pkLabel.trim() || null },
      })
      applySessionToken(session.access_token)
      setPkLabel('')
      const rows = await apiFetch<WebAuthnCredentialOut[]>('/auth/webauthn/credentials', {
        token: session.access_token,
      })
      setPasskeys(rows)
      const me = await apiFetch<UserPublic>('/auth/me', { token: session.access_token })
      setAccount(me)
    } catch (e: unknown) {
      setPkErr((e as ApiError).message ?? 'Could not register passkey')
    } finally {
      setSecBusy(false)
    }
  }

  return (
    <div
      className="mainMenuShell mainMenuShell--surface"
      style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}
    >
      <div className="paneHead">
        <div>
          <h2 style={{ margin: 0 }}>
            {passwordChangeRequiredOnly ? 'Update password' : securitySetupOnly ? 'Security setup' : 'User settings'}
          </h2>
          <div className="muted" style={{ marginTop: 4 }}>
            {passwordChangeRequiredOnly
              ? 'Enter your current password and choose a new one to continue.'
              : securitySetupOnly
                ? 'Your organisation requires an authenticator app (2FA) or at least one passkey. Complete either option below.'
                : 'Preferences for your account: appearance, sign-in security, e-mail launcher, calendar sync, and layout choices (calendar view, filters, task layout, column widths, sort order) saved automatically as you use the app.'}
          </div>
        </div>
        {!passwordChangeRequiredOnly ? (
          <button type="button" className="btn" onClick={() => void load()} disabled={busy}>
            Refresh
          </button>
        ) : null}
      </div>
      <div style={{ flex: 1, minHeight: 0, marginTop: 12, overflow: 'auto' }} className="stack">
        {accountLoadErr ? <div className="error">{accountLoadErr}</div> : null}
        {!securitySetupOnly && !passwordChangeRequiredOnly ? (
        <section className="card" style={{ padding: 16 }}>
          <h3 style={{ marginTop: 0 }}>Signature image</h3>
          <p className="muted" style={{ marginTop: 0 }}>
            Upload a PNG, JPEG, GIF, or WebP image of your signature. Use merge code{' '}
            <code>[FEE_EARNER_SIGNATURE]</code> on its own line in letter precedents — Canary replaces it with your
            image when composing documents (fee earner on the matter). Scale controls width (7 ≈ 2 inches). If you
            have not uploaded a signature, the firm default from Admin → Precedents is used when one is configured.
          </p>
          {signatureErr ? <div className="error">{signatureErr}</div> : null}
          <label className="field" style={{ maxWidth: 420, marginBottom: 12 }}>
            <span>Scale</span>
            <div className="row" style={{ gap: 12, alignItems: 'center' }}>
              <input
                type="range"
                min={1}
                max={10}
                step={1}
                value={signatureScale}
                disabled={signatureBusy}
                style={{ flex: 1 }}
                onChange={(ev) => {
                  const v = Number(ev.target.value)
                  setSignatureScale(v)
                  void saveSignatureScale(v)
                }}
              />
              <span style={{ minWidth: 88, textAlign: 'right' }}>{signatureScale} / 10</span>
            </div>
            <span className="muted">
              About {((2 * signatureScale) / 7).toFixed(2)} inches wide in composed documents
            </span>
          </label>
          <div className="muted" style={{ marginBottom: 8 }}>
            {account?.has_signature
              ? `Current file: ${account.signature_original_filename ?? 'signature image'}`
              : 'No signature uploaded yet.'}
          </div>
          <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
            <label className="btn" style={{ cursor: signatureBusy ? 'not-allowed' : 'pointer' }}>
              Upload signature…
              <input
                key={signatureFileKey}
                type="file"
                accept="image/png,image/jpeg,image/gif,image/webp"
                disabled={signatureBusy}
                style={{ display: 'none' }}
                onChange={(ev) => {
                  const f = ev.target.files?.[0]
                  ev.target.value = ''
                  if (!f) return
                  void (async () => {
                    setSignatureBusy(true)
                    setSignatureErr(null)
                    try {
                      const fd = new FormData()
                      fd.append('upload', f)
                      const me = await apiFetch<UserPublic>('/users/me/signature', {
                        token,
                        method: 'POST',
                        body: fd,
                      })
                      setAccount(me)
                      setSignatureFileKey((k) => k + 1)
                      await refreshMe()
                    } catch (e: unknown) {
                      setSignatureErr((e as ApiError).message ?? 'Upload failed')
                    } finally {
                      setSignatureBusy(false)
                    }
                  })()
                }}
              />
            </label>
            {account?.has_signature ? (
              <button
                type="button"
                className="btn danger"
                disabled={signatureBusy}
                onClick={() => {
                  void (async () => {
                    setSignatureBusy(true)
                    setSignatureErr(null)
                    try {
                      const me = await apiFetch<UserPublic>('/users/me/signature', {
                        token,
                        method: 'DELETE',
                      })
                      setAccount(me)
                      setSignatureFileKey((k) => k + 1)
                      await refreshMe()
                    } catch (e: unknown) {
                      setSignatureErr((e as ApiError).message ?? 'Could not remove signature')
                    } finally {
                      setSignatureBusy(false)
                    }
                  })()
                }}
              >
                Remove signature
              </button>
            ) : null}
          </div>
        </section>
        ) : null}
        {!securitySetupOnly && !passwordChangeRequiredOnly ? (
        <section className="card" style={{ padding: 16 }}>
          <h3 style={{ marginTop: 0 }}>Appearance</h3>
          <p className="muted" style={{ marginTop: 0 }}>
            Font, accent colour, page background, and light or dark mode are saved to your account and follow you on any
            device or browser when you sign in.
          </p>
          <div className="stack" style={{ maxWidth: 480, gap: 12 }}>
            <SingleSelectDropdown
              label="Font"
              options={FONT_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
              value={appFont}
              onChange={(v) => {
                setAppFont(v)
                setThemeSavedHint(false)
              }}
            />
            <label className="field">
              <span>Accent colour</span>
              <div className="row" style={{ gap: 8, alignItems: 'center' }}>
                <input
                  type="color"
                  value={/^#[0-9a-fA-F]{6}$/.test(appAccent.trim()) ? appAccent.trim() : DEFAULT_ACCENT}
                  onChange={(e) => {
                    setAppAccent(e.target.value)
                    setThemeSavedHint(false)
                  }}
                  aria-label="Accent colour"
                  style={{ width: 44, height: 32, padding: 0, border: 'none', cursor: 'pointer' }}
                />
                <input
                  className="allow-select"
                  value={appAccent}
                  onChange={(e) => {
                    setAppAccent(e.target.value)
                    setThemeSavedHint(false)
                  }}
                  placeholder={DEFAULT_ACCENT}
                  spellCheck={false}
                  style={{ flex: 1, minWidth: 0 }}
                />
              </div>
              <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
                Presets
              </div>
              <div className="row" style={{ flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
                {ACCENT_COLOR_PRESETS.map((p) => (
                  <button
                    key={p.label}
                    type="button"
                    title={p.label}
                    aria-label={`Set accent to ${p.label}`}
                    onClick={() => {
                      setAppAccent(p.value)
                      setThemeSavedHint(false)
                    }}
                    style={{
                      width: 28,
                      height: 28,
                      borderRadius: 6,
                      border: '2px solid var(--border)',
                      background: p.value,
                      cursor: 'pointer',
                      padding: 0,
                      boxSizing: 'border-box',
                    }}
                  />
                ))}
              </div>
            </label>
            <label className="field">
              <span>Background colour</span>
              <div className="muted" style={{ marginBottom: 6, fontSize: 12 }}>
                Colour behind cards and toolbars. Leave blank to use the default blue (light) or slate (dark) for the current
                mode.
              </div>
              <div className="row" style={{ gap: 8, alignItems: 'center' }}>
                <input
                  type="color"
                  value={/^#[0-9a-fA-F]{6}$/.test(appPageBg.trim()) ? appPageBg.trim() : DEFAULT_PAGE_BG}
                  onChange={(e) => {
                    setAppPageBg(e.target.value)
                    setThemeSavedHint(false)
                  }}
                  aria-label="Background colour"
                  style={{ width: 44, height: 32, padding: 0, border: 'none', cursor: 'pointer' }}
                />
                <input
                  className="allow-select"
                  value={appPageBg}
                  onChange={(e) => {
                    setAppPageBg(e.target.value)
                    setThemeSavedHint(false)
                  }}
                  placeholder={`${DEFAULT_PAGE_BG} or leave empty for default`}
                  spellCheck={false}
                  style={{ flex: 1, minWidth: 0 }}
                />
              </div>
              <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
                Presets
              </div>
              <div className="row" style={{ flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
                {PAGE_BG_COLOR_PRESETS.map((p) => (
                  <button
                    key={p.label}
                    type="button"
                    title={p.label}
                    aria-label={p.value ? `Set background to ${p.label}` : 'Use built-in default background'}
                    onClick={() => {
                      setAppPageBg(p.value)
                      setThemeSavedHint(false)
                    }}
                    style={
                      p.value
                        ? {
                            width: 28,
                            height: 28,
                            borderRadius: 6,
                            border: '2px solid var(--border)',
                            background: p.value,
                            cursor: 'pointer',
                            padding: 0,
                            boxSizing: 'border-box',
                          }
                        : {
                            width: 28,
                            height: 28,
                            borderRadius: 6,
                            border: '2px dashed var(--border)',
                            background: 'var(--panel2)',
                            cursor: 'pointer',
                            padding: 0,
                            boxSizing: 'border-box',
                          }
                    }
                  />
                ))}
              </div>
            </label>
            <fieldset className="field" style={{ border: 'none', margin: 0, padding: 0 }}>
              <legend style={{ marginBottom: 6 }}>Colour mode</legend>
              <div className="row" style={{ gap: 16 }}>
                <label className="row" style={{ gap: 6, cursor: 'pointer' }}>
                  <input
                    type="radio"
                    name="canary-mode"
                    checked={appMode === 'light'}
                    onChange={() => {
                      setAppMode('light')
                      setThemeSavedHint(false)
                    }}
                  />
                  Light
                </label>
                <label className="row" style={{ gap: 6, cursor: 'pointer' }}>
                  <input
                    type="radio"
                    name="canary-mode"
                    checked={appMode === 'dark'}
                    onChange={() => {
                      setAppMode('dark')
                      setThemeSavedHint(false)
                    }}
                  />
                  Dark
                </label>
              </div>
            </fieldset>
            {themeSaveErr ? <div className="error">{themeSaveErr}</div> : null}
            {themeSavedHint ? <div className="muted">Appearance saved.</div> : null}
            <div className="row" style={{ gap: 8 }}>
              <button
                type="button"
                className="btn primary"
                disabled={busy}
                onClick={() => {
                  void (async () => {
                    setThemeSaveErr(null)
                    setBusy(true)
                    try {
                      await persistUserAppearance(token, appearancePrefs)
                      setThemeSavedHint(true)
                      await refreshMe()
                    } catch (e: unknown) {
                      setThemeSaveErr((e as ApiError).message ?? 'Could not save appearance')
                    } finally {
                      setBusy(false)
                    }
                  })()
                }}
              >
                Save appearance
              </button>
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => {
                  void (async () => {
                    setThemeSaveErr(null)
                    setBusy(true)
                    try {
                      const defaults = { font: '', accent: DEFAULT_ACCENT, mode: 'light' as const, pageBg: '' }
                      setAppFont('')
                      setAppAccent(DEFAULT_ACCENT)
                      setAppPageBg('')
                      setAppMode('light')
                      await persistUserAppearance(token, defaults)
                      setThemeSavedHint(true)
                      await refreshMe()
                    } catch (e: unknown) {
                      setThemeSaveErr((e as ApiError).message ?? 'Could not reset appearance')
                    } finally {
                      setBusy(false)
                    }
                  })()
                }}
              >
                Reset to defaults
              </button>
            </div>
            <div style={{ marginTop: 14, paddingTop: 14, borderTop: '1px solid var(--border)' }}>
              <div className="muted" style={{ fontSize: 13, marginBottom: 8 }}>
                Menu tables (main menu, quotes, tasks, contacts) remember column widths when you drag column edges.
              </div>
              <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <button
                  type="button"
                  className="btn"
                  disabled={busy}
                  onClick={() => {
                    void (async () => {
                      setThemeSaveErr(null)
                      setColumnsResetHint(false)
                      setBusy(true)
                      try {
                        await resetMenuColumnWidths(token)
                        setColumnsResetHint(true)
                        await refreshMe()
                      } catch (e: unknown) {
                        setThemeSaveErr((e as ApiError).message ?? 'Could not reset menu columns')
                      } finally {
                        setBusy(false)
                      }
                    })()
                  }}
                >
                  Reset menu columns
                </button>
                {columnsResetHint ? <span className="muted">Menu columns reset.</span> : null}
              </div>
            </div>
          </div>
        </section>
        ) : null}

        <section className="card" style={{ padding: 16, marginTop: securitySetupOnly || passwordChangeRequiredOnly ? 0 : 16 }}>
          <h3 style={{ marginTop: 0 }}>
            {passwordChangeRequiredOnly ? 'New password' : securitySetupOnly ? 'Authenticator & passkeys' : 'Password & two-factor authentication'}
          </h3>
          <p className="muted" style={{ marginTop: 0 }}>
            {passwordChangeRequiredOnly
              ? 'Your organisation requires periodic password updates. Choose a new password that is at least 12 characters.'
              : securitySetupOnly
                ? 'Enable an authenticator app or register a passkey — either option satisfies your organisation’s requirement.'
                : 'Change your Canary login password. Optional 2FA (authenticator app) or passkeys add a second step at sign-in.'}
          </p>

          {!securitySetupOnly ? (
            <>
              <h4 style={{ margin: '16px 0 8px', fontSize: '1rem', fontWeight: 600 }}>Change password</h4>
              <div className="stack" style={{ maxWidth: 480, gap: 10 }}>
                <label className="field">
                  <span>Current password</span>
                  <input
                    type="password"
                    autoComplete="current-password"
                    value={pwdCurrent}
                    onChange={(e) => setPwdCurrent(e.target.value)}
                    disabled={busy || secBusy}
                  />
                </label>
                <label className="field">
                  <span>New password</span>
                  <input
                    type="password"
                    autoComplete="new-password"
                    value={pwdNew}
                    onChange={(e) => setPwdNew(e.target.value)}
                    disabled={busy || secBusy}
                  />
                </label>
                <label className="field">
                  <span>Confirm new password</span>
                  <input
                    type="password"
                    autoComplete="new-password"
                    value={pwdConfirm}
                    onChange={(e) => setPwdConfirm(e.target.value)}
                    disabled={busy || secBusy}
                  />
                </label>
                <div className="muted" style={{ fontSize: 13 }}>
                  At least 12 characters.
                </div>
                {pwdErr ? <div className="error">{pwdErr}</div> : null}
                {pwdOk ? <div className="muted">Password updated.</div> : null}
                <div className="row" style={{ gap: 8 }}>
                  <button
                    type="button"
                    className="btn primary"
                    disabled={busy || secBusy || !pwdCurrent || !pwdNew}
                    onClick={() => void submitPasswordChange()}
                  >
                    Update password
                  </button>
                </div>
              </div>
            </>
          ) : null}

          {!passwordChangeRequiredOnly ? (
          <>
          <h4 style={{ margin: securitySetupOnly ? '0 0 8px' : '20px 0 8px', fontSize: '1rem', fontWeight: 600 }}>
            Authenticator (2FA)
          </h4>
          <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
            Status:{' '}
            <strong>{account?.is_2fa_enabled ? 'Enabled' : 'Not enabled'}</strong>
          </p>

          {faErr ? <div className="error">{faErr}</div> : null}
          {faOk ? <div className="muted">2FA updated.</div> : null}

          {account?.is_2fa_enabled ? (
            <div className="stack" style={{ maxWidth: 480, gap: 10, marginTop: 8 }}>
              <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                To turn off 2FA, enter your Canary password and a current code from your authenticator app.
              </p>
              <label className="field">
                <span>Password</span>
                <input
                  type="password"
                  autoComplete="current-password"
                  value={disablePwd}
                  onChange={(e) => setDisablePwd(e.target.value)}
                  disabled={busy || secBusy}
                />
              </label>
              <label className="field">
                <span>Authenticator code</span>
                <input
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  value={disableTotp}
                  onChange={(e) => setDisableTotp(e.target.value)}
                  disabled={busy || secBusy}
                  placeholder="6-digit code"
                />
              </label>
              <button
                type="button"
                className="btn danger"
                disabled={busy || secBusy || !disablePwd.trim() || disableTotp.trim().length < 6}
                onClick={() => void disable2fa()}
              >
                Disable 2FA
              </button>
            </div>
          ) : !faSetup ? (
            <div className="stack" style={{ maxWidth: 560, gap: 10, marginTop: 8 }}>
              <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                Use an app such as Google Authenticator, Microsoft Authenticator, or 1Password. You will scan a QR code or
                enter the secret key, then confirm with a one-time code.
              </p>
              {account?.pending_authenticator_setup ? (
                <label className="field">
                  <span>Canary password (required to resume pending setup)</span>
                  <input
                    type="password"
                    autoComplete="current-password"
                    value={setupResumePwd}
                    onChange={(e) => setSetupResumePwd(e.target.value)}
                    disabled={busy || secBusy}
                  />
                </label>
              ) : null}
              <button
                type="button"
                className="btn primary"
                disabled={
                  busy ||
                  secBusy ||
                  Boolean(account?.pending_authenticator_setup && !setupResumePwd.trim())
                }
                onClick={() => void start2faSetup()}
              >
                {account?.pending_authenticator_setup ? 'Continue 2FA setup' : 'Begin 2FA setup'}
              </button>
            </div>
          ) : (
            <div className="stack" style={{ maxWidth: 560, gap: 12, marginTop: 8 }}>
              <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                Scan this QR code in your authenticator app, or add the account manually using the secret key below. Then
                enter a 6-digit code to confirm.
              </p>
              <div className="row" style={{ gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                <img
                  src={`https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(faSetup.otpauth_uri)}`}
                  width={180}
                  height={180}
                  alt=""
                  style={{ borderRadius: 8, border: '1px solid var(--border)' }}
                />
                <div className="stack" style={{ gap: 8, flex: '1 1 200px', minWidth: 0 }}>
                  <label className="field">
                    <span>Secret key (manual entry)</span>
                    <input readOnly value={faSetup.secret} style={{ fontFamily: 'monospace', fontSize: 13 }} />
                  </label>
                  <button
                    type="button"
                    className="btn"
                    disabled={busy || secBusy}
                    onClick={() =>
                      void copyTextToClipboard(faSetup.secret).then((ok) =>
                        setFaErr(ok ? null : 'Could not copy — select the secret and copy manually.'),
                      )
                    }
                  >
                    Copy secret
                  </button>
                </div>
              </div>
              <p className="muted" style={{ margin: 0, fontSize: 12 }}>
                The QR image is generated by a third-party service from your setup link (no password is sent).
              </p>
              <label className="field">
                <span>Confirmation code</span>
                <input
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  value={faCode}
                  onChange={(e) => setFaCode(e.target.value)}
                  disabled={busy || secBusy}
                  placeholder="000000"
                />
              </label>
              <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                <button
                  type="button"
                  className="btn primary"
                  disabled={busy || secBusy || faCode.trim().length < 4}
                  onClick={() => void verify2fa()}
                >
                  Enable 2FA
                </button>
                <div className="stack" style={{ gap: 6, flex: '1 1 220px' }}>
                  <label className="field" style={{ marginBottom: 0 }}>
                    <span className="muted" style={{ fontSize: 12 }}>
                      Cancel setup (your Canary password)
                    </span>
                    <input
                      type="password"
                      autoComplete="current-password"
                      value={cancelSetupPwd}
                      onChange={(e) => setCancelSetupPwd(e.target.value)}
                      disabled={busy || secBusy}
                      placeholder="Password to clear pending setup"
                    />
                  </label>
                  <button
                    type="button"
                    className="btn"
                    disabled={busy || secBusy || !cancelSetupPwd}
                    onClick={() => void cancel2faSetup()}
                  >
                    Cancel setup
                  </button>
                </div>
              </div>
            </div>
          )}

          <h4 style={{ margin: '24px 0 8px', fontSize: '1rem', fontWeight: 600 }}>Passkeys</h4>
          <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
            Passkeys let you sign in with your device (Face ID, Touch ID, Windows Hello, or a security key). You can register
            several and remove ones you no longer use.
          </p>
          {pkErr ? <div className="error">{pkErr}</div> : null}
          <div className="stack" style={{ maxWidth: 520, gap: 10, marginTop: 8 }}>
            <label className="field">
              <span className="muted" style={{ fontSize: 12 }}>
                Label (optional)
              </span>
              <input
                value={pkLabel}
                onChange={(e) => setPkLabel(e.target.value)}
                disabled={busy || secBusy}
                maxLength={200}
              />
            </label>
            <button
              type="button"
              className="btn primary"
              disabled={busy || secBusy}
              onClick={() => void registerPasskey()}
            >
              Register new passkey
            </button>
          </div>
          <div className="list" style={{ marginTop: 12 }}>
            {passkeys.map((pk) => (
              <div key={pk.id} className="listCard row" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                <div>
                  <div className="listTitle">{pk.label?.trim() || 'Passkey'}</div>
                  <div className="muted" style={{ fontSize: 12 }}>
                    Added {formatTs(pk.created_at)}
                    {pk.transports ? ` · ${pk.transports}` : ''}
                  </div>
                </div>
                <button
                  type="button"
                  className="btn danger"
                  disabled={busy || secBusy}
                  onClick={() =>
                    void (async () => {
                      const ok = await askConfirm({
                        title: 'Remove passkey',
                        message: 'Remove this passkey from your account?',
                        danger: true,
                        confirmLabel: 'Remove',
                      })
                      if (!ok) return
                      setSecBusy(true)
                      setPkErr(null)
                      try {
                        await apiFetch<null>(`/auth/webauthn/credentials/${pk.id}`, { method: 'DELETE', token })
                        const rows = await apiFetch<WebAuthnCredentialOut[]>('/auth/webauthn/credentials', { token })
                        setPasskeys(rows)
                        const me = await apiFetch<UserPublic>('/auth/me', { token })
                        setAccount(me)
                        await refreshMe()
                      } catch (e: unknown) {
                        setPkErr((e as ApiError).message ?? 'Could not remove passkey')
                      } finally {
                        setSecBusy(false)
                      }
                    })()
                  }
                >
                  Remove
                </button>
              </div>
            ))}
            {passkeys.length === 0 ? <div className="muted">No passkeys registered yet.</div> : null}
          </div>
          </>
          ) : null}
        </section>

        {!securitySetupOnly && !passwordChangeRequiredOnly ? (
        <section className="card" style={{ padding: 16, marginTop: 16 }}>
          <h3 style={{ marginTop: 0 }}>E-mail</h3>
          <p className="muted" style={{ marginTop: 0 }}>
            Choose how <strong>New → E-mail</strong> and <strong>Send by e-mail</strong> open compose.{' '}
            <strong>Outlook on the web</strong> uses your tenant&apos;s OWA URL. <strong>Desktop app</strong> uses either
            Microsoft 365 + the Canary Outlook add-in, or <code>mailto:</code> for Thunderbird and other clients (attach
            case files with <strong>Compose from matter</strong> in the add-in).
          </p>
          <div className="stack" style={{ maxWidth: 560, gap: 14, marginTop: 12 }}>
            <SingleSelectDropdown
              label="Compose with"
              options={[
                { value: 'desktop', label: 'Desktop app' },
                { value: 'outlook_web', label: 'Outlook on the web' },
              ]}
              value={emailPref}
              onChange={(v) => {
                void (async () => {
                  if (v === 'outlook_web') {
                    const proceed = await confirmOutlookWebWithoutGraph()
                    if (!proceed) return
                    setEmailPref('outlook_web')
                    setOutlookUrl((u) => u.trim() || DEFAULT_OUTLOOK_WEB_MAIL_URL)
                    return
                  }
                  setEmailPref('desktop')
                })()
              }}
              disabled={emailBusy}
            />
            {emailPref === 'desktop' ? (
              <SingleSelectDropdown
                label="Desktop mail program"
                options={[
                  { value: 'outlook', label: 'Outlook (Microsoft 365)' },
                  { value: 'other', label: 'Thunderbird or other' },
                ]}
                value={emailDesktopClient}
                onChange={(v) => setEmailDesktopClient(v === 'other' ? 'other' : 'outlook')}
                disabled={emailBusy}
              />
            ) : null}
            {emailPref === 'desktop' ? (
              <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                {emailDesktopClient === 'outlook' ? (
                  <>
                    With Microsoft 365 configured, <strong>Send by e-mail</strong> creates an Exchange draft and opens
                    compose via the Canary Outlook add-in (Drafts is the fallback).
                  </>
                ) : (
                  <>
                    Compose uses <code>mailto:</code> even when Microsoft 365 is configured. Attach case files with{' '}
                    <strong>Compose from matter</strong> in the Canary Thunderbird or Outlook add-in after compose
                    opens.
                  </>
                )}
              </p>
            ) : null}
            {emailPref === 'outlook_web' ? (
              <label className="field">
                <span>Outlook web URL</span>
                <p className="muted" style={{ marginTop: 0, marginBottom: 6, fontSize: 13 }}>
                  Used when composing from a matter and when opening filed e-mail with Outlook web. Use your tenant&apos;s
                  mail URL (e.g. <code>https://outlook.office.com/mail</code> or <code>https://outlook.office365.com/mail</code>).
                  Avoid pasting a specific message or search link here.
                </p>
                <input
                  className="allow-select"
                  value={outlookUrl}
                  onChange={(e) => setOutlookUrl(e.target.value)}
                  disabled={emailBusy}
                  spellCheck={false}
                  autoComplete="off"
                  placeholder={DEFAULT_OUTLOOK_WEB_MAIL_URL}
                />
              </label>
            ) : null}
            {emailSaveErr ? <div className="error">{emailSaveErr}</div> : null}
            {emailSaveOk ? <div className="muted">Saved.</div> : null}
            <div className="row" style={{ gap: 8 }}>
              <button
                type="button"
                className="btn primary"
                disabled={emailBusy || busy}
                onClick={() => void saveEmailHandling()}
              >
                {emailBusy ? 'Saving…' : 'Save e-mail settings'}
              </button>
            </div>
          </div>
        </section>
        ) : null}

        {!securitySetupOnly && !passwordChangeRequiredOnly ? (
        <section className="card" style={{ padding: 16, marginTop: 16 }}>
          <h3 style={{ marginTop: 0 }}>Calendar (CalDAV)</h3>
          <p className="muted" style={{ marginTop: 0 }}>
            Subscribe in Apple Calendar, Thunderbird, etc. Use the app password below — not your Canary login. Extra calendars
            and sharing are managed in your client and on the server (Radicale).
          </p>
          {caldavLoadErr ? <div className="error">{caldavLoadErr}</div> : null}
          {caldavActionErr ? <div className="error">{caldavActionErr}</div> : null}
          {caldavCopyHint ? <div className="muted">{caldavCopyHint}</div> : null}
          {caldav && !caldav.enabled ? (
            <p className="muted">CalDAV is not enabled for your account yet.</p>
          ) : null}
          {caldav && caldav.enabled ? (
            <div className="stack" style={{ maxWidth: 560, gap: 10 }}>
              <label className="field">
                <span>Server / principal URL</span>
                <input readOnly value={caldav.caldav_url} style={{ fontFamily: 'monospace', fontSize: 13 }} />
              </label>
              <label className="field">
                <span>CalDAV username</span>
                <input readOnly value={caldav.caldav_username} style={{ fontFamily: 'monospace', fontSize: 13 }} />
              </label>
              <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                <button
                  type="button"
                  className="btn"
                  disabled={busy || caldavBusy}
                  onClick={() => {
                    void copyTextToClipboard(caldav.caldav_url).then((ok) =>
                      setCaldavCopyHint(ok ? 'Copied URL.' : 'Could not copy automatically — select and copy the URL.'),
                    )
                  }}
                >
                  Copy URL
                </button>
                <button
                  type="button"
                  className="btn"
                  disabled={busy || caldavBusy}
                  onClick={() => {
                    void copyTextToClipboard(caldav.caldav_username).then((ok) =>
                      setCaldavCopyHint(ok ? 'Copied username.' : 'Could not copy — select and copy the username.'),
                    )
                  }}
                >
                  Copy username
                </button>
              </div>
            </div>
          ) : null}
          {caldavProvision ? (
            <div
              style={{
                marginTop: 12,
                padding: 12,
                borderRadius: 8,
                background: 'rgba(139, 92, 246, 0.12)',
                border: '1px solid rgba(139, 92, 246, 0.35)',
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: 8 }}>CalDAV app password (save it now)</div>
              <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
                {caldavProvision.note}
              </p>
              <label className="field">
                <span>Password</span>
                <input readOnly value={caldavProvision.caldav_password} style={{ fontFamily: 'monospace', fontSize: 13 }} />
              </label>
              <div className="row" style={{ gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
                <button
                  type="button"
                  className="btn"
                  onClick={() => {
                    void copyTextToClipboard(caldavProvision.caldav_password).then((ok) =>
                      setCaldavCopyHint(ok ? 'Copied password.' : 'Could not copy — select the password field manually.'),
                    )
                  }}
                >
                  Copy password
                </button>
                <button type="button" className="btn primary" onClick={() => setCaldavProvision(null)}>
                  I’ve saved it
                </button>
              </div>
            </div>
          ) : null}
          <div className="row" style={{ gap: 8, flexWrap: 'wrap', marginTop: 16 }}>
            {caldav && !caldav.enabled ? (
              <button
                type="button"
                className="btn primary"
                disabled={busy || caldavBusy || !!caldavLoadErr}
                onClick={() => {
                  setCaldavActionErr(null)
                  setCaldavCopyHint(null)
                  setCaldavBusy(true)
                  apiFetch<UserCalDAVProvisionOut>('/users/me/calendar/enable', { method: 'POST', token })
                    .then((p) => {
                      setCaldavProvision(p)
                      setCaldav({ enabled: true, caldav_url: p.caldav_url, caldav_username: p.caldav_username })
                    })
                    .catch((e: unknown) =>
                      setCaldavActionErr((e as ApiError).message ?? 'Could not enable CalDAV'),
                    )
                    .finally(() => setCaldavBusy(false))
                }}
              >
                Enable CalDAV
              </button>
            ) : null}
            {caldav?.enabled ? (
              <>
                <button
                  type="button"
                  className="btn"
                  disabled={busy || caldavBusy}
                  onClick={() => {
                    setCaldavActionErr(null)
                    setCaldavCopyHint(null)
                    setCaldavBusy(true)
                    apiFetch<UserCalDAVProvisionOut>('/users/me/calendar/reset-password', { method: 'POST', token })
                      .then((p) => setCaldavProvision(p))
                      .catch((e: unknown) =>
                        setCaldavActionErr((e as ApiError).message ?? 'Could not reset password'),
                      )
                      .finally(() => setCaldavBusy(false))
                  }}
                >
                  Reset app password
                </button>
                <button
                  type="button"
                  className="btn"
                  disabled={busy || caldavBusy}
                  onClick={() => {
                    void (async () => {
                      const ok = await askConfirm({
                        title: 'Disable CalDAV?',
                        message: 'Your calendar app will stop syncing until you enable again.',
                        danger: true,
                        confirmLabel: 'Disable',
                      })
                      if (!ok) return
                      setCaldavActionErr(null)
                      setCaldavCopyHint(null)
                      setCaldavProvision(null)
                      setCaldavBusy(true)
                      apiFetch<null>('/users/me/calendar/disable', { method: 'DELETE', token })
                      .then(() => {
                        setCaldav((c) =>
                          c
                            ? {
                                enabled: false,
                                caldav_url: c.caldav_url,
                                caldav_username: c.caldav_username,
                              }
                            : c,
                        )
                      })
                      .catch((e: unknown) =>
                        setCaldavActionErr((e as ApiError).message ?? 'Could not disable CalDAV'),
                      )
                      .finally(() => setCaldavBusy(false))
                    })()
                  }}
                >
                  Disable CalDAV
                </button>
              </>
            ) : null}
          </div>
        </section>
        ) : null}
      </div>
    </div>
  )
}


function contactTypeLabel(t: ContactOut['type']) {
  return t === 'person' ? 'Person' : 'Organisation'
}

function Contacts({ token, me }: { token: string; me?: UserPublic | null }) {
  const { askConfirm } = useDialogs()
  const { prefs: uiPrefs, setPreference: setUiPreference, setPreferenceDebounced: setUiPreferenceDebounced } =
    useUserUiPreferences(me, token)
  const [contactsSearch, setContactsSearch] = useState('')
  const debouncedContactsSearch = useDebouncedValue(contactsSearch.trim(), 300)
  const [contactsFilterOpen, setContactsFilterOpen] = useState(false)
  const [contactsFilterType, setContactsFilterType] = useState<'' | ContactOut['type']>('')
  const [contactsFilterEmail, setContactsFilterEmail] = useState<'' | 'has' | 'missing'>('')
  const [contactsFilterPhone, setContactsFilterPhone] = useState<'' | 'has' | 'missing'>('')
  const { gridTemplateColumns: contactsGridColumns, startResize: contactsStartResize } = useColumnWidths(
    CONTACTS_COLUMN_COUNT,
    {
      widths: effectiveColumnWidths(
        uiPrefs.contacts_column_widths,
        CONTACTS_COLUMN_COUNT,
        LEGACY_AUTO_CONTACTS_COLUMN_WIDTHS,
      ),
      fallbackWidths: [...CONTACTS_COLUMN_WIDTHS_DEFAULT],
      onChange: (widths) => setUiPreferenceDebounced('contacts_column_widths', widths, 300),
    },
  )
  const [contacts, setContacts] = useState<ContactOut[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [contactRowFocusId, setContactRowFocusId] = useState<string | null>(null)

  const [createOpen, setCreateOpen] = useState(false)
  const [createErr, setCreateErr] = useState<string | null>(null)

  const [editing, setEditing] = useState<ContactOut | null>(null)
  const [contactCtx, setContactCtx] = useState<null | { x: number; y: number; c: ContactOut }>(null)
  const contactCtxRef = useRef<HTMLDivElement | null>(null)

  async function load() {
    setBusy(true)
    setErr(null)
    try {
      const data = await fetchContactSearch(token, {
        q: debouncedContactsSearch || undefined,
        type: contactsFilterType || undefined,
        hasEmail:
          contactsFilterEmail === 'has' ? true : contactsFilterEmail === 'missing' ? false : undefined,
        hasPhone:
          contactsFilterPhone === 'has' ? true : contactsFilterPhone === 'missing' ? false : undefined,
      })
      setContacts(data)
    } catch (e: any) {
      setErr(e?.message ?? 'Failed to load contacts')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    void load()
  }, [token, debouncedContactsSearch, contactsFilterType, contactsFilterEmail, contactsFilterPhone])

  useEffect(() => {
    if (!contactCtx) return
    function handleMouseDown(e: MouseEvent) {
      const t = e.target as Node
      if (contactCtxRef.current?.contains(t)) return
      setContactCtx(null)
    }
    document.addEventListener('mousedown', handleMouseDown)
    return () => document.removeEventListener('mousedown', handleMouseDown)
  }, [contactCtx])

  const contactsActiveFilterCount = useMemo(
    () =>
      (contactsFilterType ? 1 : 0) +
      (contactsFilterEmail ? 1 : 0) +
      (contactsFilterPhone ? 1 : 0),
    [contactsFilterType, contactsFilterEmail, contactsFilterPhone],
  )

  const rows = useMemo(() => {
    const dir = uiPrefs.contacts_sort_dir === 'asc' ? 1 : -1
    const key = uiPrefs.contacts_sort_key
    return [...contacts].sort((a, b) => {
      const av =
        key === 'name'
          ? a.name
          : key === 'type'
            ? a.type
            : key === 'email'
              ? a.email ?? ''
              : a.phone ?? ''
      const bv =
        key === 'name'
          ? b.name
          : key === 'type'
            ? b.type
            : key === 'email'
              ? b.email ?? ''
              : b.phone ?? ''
      return String(av).localeCompare(String(bv)) * dir
    })
  }, [contacts, uiPrefs.contacts_sort_key, uiPrefs.contacts_sort_dir])

  function toggleContactsSort(key: 'name' | 'type' | 'email' | 'phone') {
    if (uiPrefs.contacts_sort_key === key) {
      setUiPreference('contacts_sort_dir', uiPrefs.contacts_sort_dir === 'asc' ? 'desc' : 'asc')
    } else {
      setUiPreference('contacts_sort_key', key)
      setUiPreference('contacts_sort_dir', 'asc')
    }
  }

  function closeCreateModal() {
    if (busy) return
    setCreateOpen(false)
    setCreateErr(null)
  }

  return (
    <div className="mainMenuShell mainMenuShell--mainMenu">
      {err ? <div className="error">{err}</div> : null}
      <div className={`mainMenuFilterBar${contactsFilterOpen ? ' mainMenuFilterBar--dropdownOpen' : ''}`}>
        <div className="row mainMenuFilterRow mainMenuFilterRow--toolbar mainMenuFilterRow--searchRight">
          <div className="mainMenuFilterRowLeft">
            <button
              type="button"
              className="btn primary toolbarLeadBtn"
              onClick={() => {
                setCreateErr(null)
                setCreateOpen(true)
              }}
            >
              New contact
            </button>
            <button type="button" className="btn" onClick={() => void load()} disabled={busy}>
              Refresh
            </button>
          </div>
          <div className="mainMenuFilterRowRight">
            <div className="caseToolbarDropdownWrap">
              <button
                type="button"
                className="btn mainMenuFilterBtn"
                aria-expanded={contactsFilterOpen}
                aria-haspopup="true"
                aria-controls="contacts-menu-filter-menu"
                id="contacts-menu-filter-button"
                onClick={(e) => {
                  e.stopPropagation()
                  setContactsFilterOpen((o) => !o)
                }}
              >
                <span className="mainMenuFilterBtnInner">
                  <svg
                    className="mainMenuFilterBtnIcon"
                    width={16}
                    height={16}
                    viewBox="0 0 24 24"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                    aria-hidden
                  >
                    <polygon
                      points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      fill="none"
                    />
                  </svg>
                  <span>Filter</span>
                  <span className="mainMenuFilterBtnCount">({contactsActiveFilterCount})</span>
                </span>
              </button>
              {contactsFilterOpen ? (
                <div
                  id="contacts-menu-filter-menu"
                  className="caseToolbarDropdown mainMenuFilterDropdown"
                  role="group"
                  aria-labelledby="contacts-menu-filter-button"
                  onMouseDown={(e) => e.stopPropagation()}
                >
                  <div className="stack mainMenuFilterDropdownBody">
                    <SingleSelectDropdown
                      label="Type"
                      options={[
                        { value: '', label: 'All' },
                        { value: 'person', label: 'Person' },
                        { value: 'organisation', label: 'Organisation' },
                      ]}
                      value={contactsFilterType}
                      onChange={(v) => setContactsFilterType(v as '' | ContactOut['type'])}
                      placeholder="All"
                    />
                    <SingleSelectDropdown
                      label="Email"
                      options={[
                        { value: '', label: 'Any' },
                        { value: 'has', label: 'Has email' },
                        { value: 'missing', label: 'Missing email' },
                      ]}
                      value={contactsFilterEmail}
                      onChange={(v) => setContactsFilterEmail(v as '' | 'has' | 'missing')}
                      placeholder="Any"
                    />
                    <SingleSelectDropdown
                      label="Phone"
                      options={[
                        { value: '', label: 'Any' },
                        { value: 'has', label: 'Has phone' },
                        { value: 'missing', label: 'Missing phone' },
                      ]}
                      value={contactsFilterPhone}
                      onChange={(v) => setContactsFilterPhone(v as '' | 'has' | 'missing')}
                      placeholder="Any"
                    />
                  </div>
                </div>
              ) : null}
            </div>
            <SearchInput
              placeholder="Search"
              value={contactsSearch}
              onChange={(e) => setContactsSearch(e.target.value)}
              onClear={() => setContactsSearch('')}
              className="mainMenuSearchInput"
              aria-label="Search contacts"
            />
          </div>
        </div>
      </div>

      <div className="card casesTableCard" style={{ padding: 0, overflow: 'hidden' }}>
        <div className="casesTableScroll contactsTableScroll">
          <div className="table">
            <div className="tr th" style={contactsGridColumns ? { gridTemplateColumns: contactsGridColumns } : undefined}>
              {(
                [
                  ['name', 'Name'],
                  ['type', 'Type'],
                  ['email', 'Email'],
                  ['phone', 'Phone'],
                ] as const
              ).map(([k, label], colIndex) => (
                <div key={k} className="thCell">
                  <button type="button" className="thbtn" onClick={() => toggleContactsSort(k)}>
                    {label}
                  </button>
                  {colIndex < 3 ? (
                    <div
                      className="colResizeHandle"
                      role="separator"
                      aria-orientation="vertical"
                      aria-label={`Resize ${label} column`}
                      onMouseDown={(e) => {
                        e.preventDefault()
                        contactsStartResize(colIndex, e.clientX, e.currentTarget.closest('.tr.th') as HTMLElement | null)
                      }}
                    />
                  ) : null}
                </div>
              ))}
            </div>
            {rows.map((c) => (
              <button
                key={c.id}
                type="button"
                className={`tr rowbtn${contactRowFocusId === c.id ? ' active' : ''}`}
                style={contactsGridColumns ? { gridTemplateColumns: contactsGridColumns } : undefined}
                onClick={() => setContactRowFocusId(c.id)}
                onDoubleClick={() => setEditing(c)}
                onContextMenu={(e) => {
                  e.preventDefault()
                  setContactCtx({ x: e.clientX, y: e.clientY, c })
                }}
              >
                <div className="td">{c.name}</div>
                <div className="td">{contactTypeLabel(c.type)}</div>
                <div className="td">{c.email ?? '—'}</div>
                <div className="td">{c.phone ?? '—'}</div>
              </button>
            ))}
            {rows.length === 0 ? (
              <div className="muted" style={{ padding: 12 }}>
                {contacts.length === 0 ? 'No contacts yet.' : 'No contacts match your search.'}
              </div>
            ) : null}
          </div>
        </div>
      </div>

      {contactCtx ? (
        <div
          ref={contactCtxRef}
          className="docContextMenu"
          style={{ left: contactCtx.x, top: contactCtx.y, zIndex: 30 }}
          onMouseDown={(e) => e.stopPropagation()}
        >
          <div
            className="docContextItem"
            role="menuitem"
            tabIndex={0}
            onClick={() => {
              const c = contactCtx.c
              setContactCtx(null)
              setEditing(c)
            }}
          >
            Open
          </div>
          <div
            className="docContextItem"
            role="menuitem"
            tabIndex={0}
            onClick={() => {
              void (async () => {
                const c = contactCtx.c
                setContactCtx(null)
                const ok = await askConfirm({
                  title: 'Delete contact',
                  message: `Delete “${c.name}” from the global directory?`,
                  danger: true,
                  confirmLabel: 'Delete',
                })
                if (!ok) return
                setBusy(true)
                setErr(null)
                try {
                  await apiFetch(`/contacts/${c.id}`, { token, method: 'DELETE' })
                  if (editing?.id === c.id) setEditing(null)
                  await load()
                } catch (e: any) {
                  setErr(e?.message ?? 'Delete failed')
                } finally {
                  setBusy(false)
                }
              })()
            }}
          >
            Delete
          </div>
        </div>
      ) : null}

      {createOpen ? (
        <div
          className="modalOverlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="new-contact-title"
          onClick={() => closeCreateModal()}
        >
          <div
            className="modal modal--scrollBody card"
            style={{ maxWidth: 720, width: 'min(720px, 100%)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="paneHead">
              <div>
                <h2 id="new-contact-title">New contact</h2>
                <div className="muted">Add a person or organisation to the global directory (same details as when creating from a matter).</div>
              </div>
              <button type="button" className="btn" onClick={() => closeCreateModal()} disabled={busy}>
                Close
              </button>
            </div>
            <div className="stack modalBodyScroll" style={{ marginTop: 12 }}>
              <GlobalContactCreateForm
                busy={busy}
                formError={createErr}
                submitLabel="Create"
                showCancelButton
                cancelLabel="Cancel"
                onCancel={() => closeCreateModal()}
                onSubmit={async (payload) => {
                  setBusy(true)
                  setCreateErr(null)
                  try {
                    await apiFetch('/contacts', { token, json: payload })
                    setCreateOpen(false)
                    setCreateErr(null)
                    await load()
                  } catch (e: any) {
                    setCreateErr(e?.message ?? 'Create failed')
                    throw e
                  } finally {
                    setBusy(false)
                  }
                }}
              />
            </div>
          </div>
        </div>
      ) : null}

      {editing ? (
        <div
          className="modalOverlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="edit-contact-title"
          onClick={() => {
            setEditing(null)
          }}
        >
          <div
            className="modal modal--scrollBody card"
            style={{ maxWidth: 640, width: 'min(640px, 100%)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <ContactEditor
              token={token}
              contact={editing}
              onSaved={async () => {
                setEditing(null)
                await load()
              }}
              onDeleted={async () => {
                setEditing(null)
                await load()
              }}
              onCancel={() => setEditing(null)}
            />
          </div>
        </div>
      ) : null}
    </div>
  )
}

function ContactEditor({
  token,
  contact,
  onSaved,
  onDeleted,
  onCancel,
}: {
  token: string
  contact: ContactOut
  onSaved: () => void
  onDeleted?: () => void
  onCancel: () => void
}) {
  const { askConfirm } = useDialogs()
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [fields, setFields] = useState(() => contactOutToFormFields(contact))

  useEffect(() => {
    setFields(contactOutToFormFields(contact))
  }, [contact.id])

  const resolvedName = useMemo(
    () =>
      resolveContactNameWithFallback(
        fields.type,
        {
          title: fields.title,
          first_name: fields.firstName,
          middle_name: fields.middleName,
          last_name: fields.lastName,
        },
        { company_name: fields.companyName, trading_name: fields.tradingName },
        contact.name,
      ),
    [fields, contact.name],
  )

  return (
    <>
      <div className="paneHead">
        <div>
          <h2 id="edit-contact-title">Edit contact</h2>
        </div>
        <div className="row" style={{ flexWrap: 'wrap', gap: 8 }}>
          <button className="btn" onClick={onCancel} disabled={busy}>
            Close
          </button>
          {onDeleted ? (
            <button
              className="btn"
              disabled={busy}
              onClick={async () => {
                const ok = await askConfirm({
                  title: 'Delete contact',
                  message: 'Permanently delete this contact from the global directory?',
                  danger: true,
                  confirmLabel: 'Delete',
                })
                if (!ok) return
                setBusy(true)
                setErr(null)
                try {
                  await apiFetch<unknown>(`/contacts/${contact.id}`, { token, method: 'DELETE' })
                  onDeleted()
                } catch (e: any) {
                  setErr(e?.message ?? 'Delete failed')
                } finally {
                  setBusy(false)
                }
              }}
            >
              Delete globally
            </button>
          ) : null}
          <button
            className="btn primary"
            disabled={busy || !resolvedName.trim()}
            onClick={async () => {
              if (fields.type === 'organisation' && !fields.tradingName.trim()) {
                setErr('Trading name is required for organisations.')
                return
              }
              const payload = contactFieldsModelToPayload(fields, { fallbackName: contact.name })
              if (!payload) {
                setErr('Name is required.')
                return
              }
              setBusy(true)
              setErr(null)
              try {
                await apiFetch(`/contacts/${contact.id}`, {
                  token,
                  method: 'PATCH',
                  json: payload,
                })
                onSaved()
              } catch (e: any) {
                setErr(e?.message ?? 'Save failed')
              } finally {
                setBusy(false)
              }
            }}
          >
            Save
          </button>
        </div>
      </div>
      {err ? <div className="error">{err}</div> : null}
      <div className="stack modalBodyScroll" style={{ marginTop: 12 }}>
        <ContactPersonOrgAddressFields
          value={fields}
          onChange={(patch) => setFields((prev) => ({ ...prev, ...patch }))}
          busy={busy}
        />
        <ContactPortalPanel token={token} contactId={contact.id} contactName={contact.name} contactEmail={contact.email} />
      </div>
    </>
  )
}

export default App
