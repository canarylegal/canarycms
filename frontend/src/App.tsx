import {
  startAuthentication,
  startRegistration,
  type PublicKeyCredentialCreationOptionsJSON,
  type PublicKeyCredentialRequestOptionsJSON,
} from '@simplewebauthn/browser'
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { AdminBilling } from './AdminBilling'
import { AdminDeploy } from './AdminDeploy'
import { AdminLoginUpdatePrompt } from './AdminLoginUpdatePrompt'
import { AdminEmail } from './AdminEmail'
import { AdminFirmDetails } from './AdminFirmDetails'
import { AdminSubMenus } from './AdminSubMenus'
import { AdminTasks } from './AdminTasks'
import { CalendarPage } from './CalendarPage'
import { ReportsPage } from './ReportsPage'
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
import { CASE_FILES_STORAGE_KEY, signalCaseFilesChanged } from './caseFilesCrossTab'
import { CaseDetail, type CaseOpenDocPanel } from './case/CaseDetail'
import { matterContactTypeLabel } from './case/matterLabels'
import { PropertyDetailsForm } from './case/PropertyDetailsForm'
import {
  blankPropertyPayload,
  buildNewMatterDescription,
  subTypeHasPropertyMenu,
} from './case/propertyMatterHelpers'
import { CASE_MENU_OPTIONS } from './caseMenuOptions'
import { apiFetch, apiUrl, applyAuthHeaders } from './api'
import {
  ACCENT_COLOR_PRESETS,
  DEFAULT_ACCENT,
  DEFAULT_PAGE_BG,
  FONT_OPTIONS,
  PAGE_BG_COLOR_PRESETS,
} from './theme'
import { persistUserAppearance, useAppearanceFormState, useServerAppearance } from './useServerAppearance'
import { useUserUiPreferences } from './useUserUiPreferences'
import { useColumnWidths } from './useColumnWidths'
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
import { normalizeUiPreferences } from './userUiPreferences'
import { AppLogo } from './AppLogo'
import { openOnlyOfficePrecedentEditor } from './onlyofficeEditorWindow'
import {
  DEFAULT_OUTLOOK_WEB_MAIL_URL,
  isOrgMicrosoftGraphConfigured,
  OUTLOOK_WEB_WITHOUT_GRAPH_CONFIRM_MESSAGE,
} from './emailLauncher'
import { useDialogs } from './DialogProvider'
import { SearchInput } from './SearchInput'
import type { ApiError } from './api'
import { copyTextToClipboard } from './copyToClipboard'
import { canaryDocumentTitle } from './tabTitle'
import { caseHasRevokedUserAccess, formatCaseStatusLabel, GLOBAL_PRECEDENT_SCOPE } from './types'
import type {
  AdminAuditEvent,
  CaseContactOut,
  CaseNoteOut,
  CaseOut,
  CasePropertyPayload,
  CaseTaskOut,
  TaskMenuRow,
  ContactOut,
  FileSummary,
  FirmSettingsOut,
  LetterheadStyle,
  MergeCodeCatalogImportResult,
  MergeCodeCatalogOut,
  MatterContactTypeOut,
  MatterHeadTypeOut,
  MatterSubTypeOut,
  PrecedentCategoryOut,
  PrecedentOut,
  TokenResponse,
  Verify2FASessionResponse,
  ForgotPasswordResponse,
  ChangePasswordResponse,
  AdminSendPasswordResetResponse,
  AdminUserPublic,
  UserCalDAVProvisionOut,
  UserCalDAVStatusOut,
  UserPermissionCategoryOut,
  UserPublic,
  UserSummary,
  WebAuthnCredentialOut,
} from './types'

type View =
  | 'main-menu'
  | 'tasks'
  | 'case-menu'
  | 'contacts'
  | 'calendar'
  | 'reports'
  | 'user-settings'
  | 'admin-console'

function canaryViewTitleSegment(view: View, caseDetail: CaseOut | null): string {
  switch (view) {
    case 'main-menu':
      return 'Main menu'
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
    case 'calendar':
      return 'Calendar'
    case 'reports':
      return 'Reports'
    case 'user-settings':
      return 'User Settings'
    case 'admin-console':
      return 'Admin settings'
  }
}

function formatTs(s: string) {
  const d = new Date(s)
  return isNaN(d.getTime()) ? s : d.toLocaleString()
}

/** Non-admin users who must complete authenticator 2FA or register a passkey before using the rest of the app. */
function userNeedsSecondFactorSetup(me: UserPublic): boolean {
  if (me.admin_console_access) return false
  return Boolean(me.organization_requires_second_factor && !me.is_2fa_enabled && !me.has_passkeys)
}

/** JWT/session did not satisfy org “verified second factor at sign-in” (passkey or password + authenticator). */
function sessionNeedsVerifiedSecondFactor(me: UserPublic): boolean {
  if (me.admin_console_access) return false
  return me.session_second_factor_verified === false
}

function sessionNeedsPasswordChange(me: UserPublic): boolean {
  if (me.admin_console_access) return false
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
        return
      }
      setLoading(true)
      setError(null)
      try {
        const user = await apiFetch<UserPublic>('/auth/me', { token })
        if (!cancelled) setMe(user)
      } catch (e: any) {
        if (!cancelled) {
          setError(e?.message ?? 'Auth error')
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
        setLoginError(msg)
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
        <p className="muted">Sign in to continue.</p>
        {step === 'password' ? (
          <>
            <form className="stack" style={{ marginTop: 16 }} onSubmit={handlePasswordSubmit}>
              <label className="field">
                <span>Email</span>
                <input
                  value={email}
                  onChange={(e) => {
                    onClearError()
                    setEmail(e.target.value)
                  }}
                  autoComplete="username"
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
              <button type="submit" className="btn primary" style={{ marginTop: 8 }} disabled={busy}>
                {busy ? 'Signing in…' : 'Sign in'}
              </button>
            </form>
            <button
              type="button"
              className="btn"
              style={{ marginTop: 12, width: '100%' }}
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
  const { askConfirm } = useDialogs()
  const [view, setView] = useState<View>(() => (initialTasksCaseFilter ? 'tasks' : 'main-menu'))
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null)
  const [showNewMatter, setShowNewMatter] = useState(false)

  // Cases
  const [cases, setCases] = useState<CaseOut[]>([])
  const [, setCasesBusy] = useState(false)
  const [casesErr, setCasesErr] = useState<string | null>(null)
  const [caseListFocusId, setCaseListFocusId] = useState<string | null>(null)
  const [caseOpenDocPanel, setCaseOpenDocPanel] = useState<CaseOpenDocPanel | null>(null)
  const consumeCaseOpenDocPanel = useCallback(() => setCaseOpenDocPanel(null), [])
  const [taskMenuRows, setTaskMenuRows] = useState<TaskMenuRow[]>([])
  const [taskMenuCaseFilter, setTaskMenuCaseFilter] = useState<string | null>(initialTasksCaseFilter ?? null)
  const [globalTaskCreateOpen, setGlobalTaskCreateOpen] = useState(false)
  const [tasksMenuFilterOpen, setTasksMenuFilterOpen] = useState(false)

  // Case detail data
  const [caseDetail, setCaseDetail] = useState<CaseOut | null>(null)
  const [notes, setNotes] = useState<CaseNoteOut[]>([])
  const [tasks, setTasks] = useState<CaseTaskOut[]>([])
  const [files, setFiles] = useState<FileSummary[]>([])
  const [caseContacts, setCaseContacts] = useState<CaseContactOut[]>([])
  const [detailErr, setDetailErr] = useState<string | null>(null)
  const [caseListUsers, setCaseListUsers] = useState<UserSummary[]>([])
  const canAdminConsole = Boolean(auth.me?.admin_console_access || auth.me?.role === 'admin')

  const token = auth.token ?? undefined
  const [taskMenuSearch, setTaskMenuSearch] = useState('')
  const [taskMenuFilterMatterType, setTaskMenuFilterMatterType] = useState('')
  const [mainMenuFilterMatterTypes, setMainMenuFilterMatterTypes] = useState<string[]>([])
  const [mainMenuFilterFeeEarnerUserIds, setMainMenuFilterFeeEarnerUserIds] = useState<string[]>([])
  const [mainMenuFilterCaseStatuses, setMainMenuFilterCaseStatuses] = useState<MainMenuCaseStatusFilter[]>([])

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

  const refreshCaseDetail = useCallback(async (caseId: string) => {
    if (!token) return
    setDetailErr(null)
    try {
      const [c, n, t, f, cc] = await Promise.all([
        apiFetch<CaseOut>(`/cases/${caseId}`, { token }),
        apiFetch<CaseNoteOut[]>(`/cases/${caseId}/notes`, { token }),
        apiFetch<CaseTaskOut[]>(`/cases/${caseId}/tasks`, { token }),
        apiFetch<FileSummary[]>(`/cases/${caseId}/files`, { token }),
        apiFetch<CaseContactOut[]>(`/cases/${caseId}/contacts`, { token }),
      ])
      setCaseDetail(c)
      setNotes(Array.isArray(n) ? n : [])
      setTasks(Array.isArray(t) ? t : [])
      setFiles(Array.isArray(f) ? f : [])
      setCaseContacts(Array.isArray(cc) ? cc : [])
    } catch (e: any) {
      setDetailErr(e?.message ?? 'Failed to load case')
    }
  }, [token])

  const refreshOpenCaseDetail = useCallback(() => {
    if (selectedCaseId) void refreshCaseDetail(selectedCaseId)
  }, [selectedCaseId, refreshCaseDetail])

  /** Refreshes the open case and notifies other browser tabs (``storage``) so their document list can update. */
  const refreshCaseDetailWithCrossTabSignal = useCallback(() => {
    refreshOpenCaseDetail()
    if (selectedCaseId) signalCaseFilesChanged(selectedCaseId)
  }, [selectedCaseId, refreshOpenCaseDetail])

  useEffect(() => {
    if (!token) return
    void refreshCases()
  }, [token])

  useEffect(() => {
    if (!token || view !== 'tasks') return
    void refreshTaskMenu()
  }, [token, view, refreshTaskMenu])

  useEffect(() => {
    if (!token || !selectedCaseId) return
    void refreshCaseDetail(selectedCaseId)
  }, [token, selectedCaseId, refreshCaseDetail])

  useEffect(() => {
    function onMsg(e: MessageEvent) {
      if (e.origin !== window.location.origin) return
      const d = e.data as { type?: string; caseId?: string } | null
      if (d?.type === 'canary-files-changed' && d.caseId && selectedCaseId === d.caseId) {
        void refreshCaseDetail(d.caseId)
      }
    }
    window.addEventListener('message', onMsg)
    return () => window.removeEventListener('message', onMsg)
  }, [selectedCaseId, refreshCaseDetail])

  useEffect(() => {
    function onStorage(e: StorageEvent) {
      if (e.key !== CASE_FILES_STORAGE_KEY || !e.newValue || !token) return
      let parsed: { caseId?: string } = {}
      try {
        parsed = JSON.parse(e.newValue) as { caseId?: string }
      } catch {
        return
      }
      if (parsed.caseId && selectedCaseId === parsed.caseId) {
        void refreshCaseDetail(parsed.caseId)
      }
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [token, selectedCaseId, refreshCaseDetail])

  useEffect(() => {
    if (view !== 'tasks') setTasksMenuFilterOpen(false)
  }, [view])

  const onMainMenuSelectCase = useCallback((id: string, opts?: { docPanel?: CaseOpenDocPanel }) => {
    setCaseListFocusId(id)
    setSelectedCaseId(id)
    setCaseOpenDocPanel(opts?.docPanel ?? null)
    setView('case-menu')
  }, [])

  const onMainMenuSort = useCallback(
    (k: 'reference' | 'client' | 'matter' | 'feeEarner' | 'status' | 'created') => {
      if (k === uiPrefs.main_menu_sort_key) {
        setUiPreference('main_menu_sort_dir', uiPrefs.main_menu_sort_dir === 'asc' ? 'desc' : 'asc')
      } else {
        setUiPreference('main_menu_sort_key', k)
        setUiPreference('main_menu_sort_dir', 'asc')
      }
    },
    [setUiPreference, uiPrefs.main_menu_sort_dir, uiPrefs.main_menu_sort_key],
  )

  const onOpenNewMatter = useCallback(() => setShowNewMatter(true), [])
  const onCloseNewMatter = useCallback(() => setShowNewMatter(false), [])
  const onRefreshCases = useCallback(() => void refreshCases(), [token])
  const onMainMenuCaseCreated = useCallback(async () => {
    setShowNewMatter(false)
    await refreshCases()
  }, [token])

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
    setMainMenuFilterCaseStatuses(saved.main_menu_filter_case_statuses)
  }, [auth.me?.id])

  function renderMainContent() {
    if (!token) return null
    if (view === 'main-menu') return null

    if (view === 'admin-console') return <AdminConsole token={token} refreshMe={auth.refreshMe} />
    if (view === 'user-settings')
      return <UserSettingsPage token={token} refreshMe={auth.refreshMe} applySessionToken={auth.applySessionToken} />
    if (view === 'calendar')
      return <CalendarPage token={token} me={auth.me} onOpenSettings={() => setView('user-settings')} />
    if (view === 'contacts') return <Contacts token={token} me={auth.me} />

    if (view === 'reports') {
      return <ReportsPage token={token} me={auth.me} />
    }

    if (view === 'case-menu') {
      return (
        <CaseDetail
          token={token}
          caseDetail={caseDetail}
          notes={notes}
          tasks={tasks}
          files={files}
          caseContacts={caseContacts}
          error={detailErr}
          selectedCaseId={selectedCaseId}
          currentUser={auth.me}
          openDocPanel={caseOpenDocPanel}
          onOpenDocPanelConsumed={consumeCaseOpenDocPanel}
          onRefresh={refreshCaseDetailWithCrossTabSignal}
          onCaseListInvalidate={() => void refreshCases()}
          onTaskMenuInvalidate={() => void refreshTaskMenu()}
        />
      )
    }

    if (view === 'tasks') {
      return (
        <>
        <div className="mainMenuShell mainMenuShell--mainMenu">
          <div className={`mainMenuFilterBar${tasksMenuFilterOpen ? ' mainMenuFilterBar--dropdownOpen' : ''}`}>
            <div className="row mainMenuFilterRow mainMenuFilterRow--toolbar">
              <div className="mainMenuFilterRowLeft">
            <SearchInput
              placeholder="Search tasks (reference, client, matter, task, date, assigned)…"
              value={taskMenuSearch}
              onChange={(e) => setTaskMenuSearch(e.target.value)}
              onClear={() => setTaskMenuSearch('')}
              className="mainMenuSearchInput"
              aria-label="Search tasks"
            />
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
                        <label className="field">
                          <span>Matter type</span>
                          <select
                            value={taskMenuFilterMatterType}
                            onChange={(e) => setTaskMenuFilterMatterType(e.target.value)}
                            aria-label="Filter tasks by matter type"
                          >
                            <option value="">All</option>
                            {tasksMenuMatterTypeOptions.map((opt) => (
                              <option key={opt} value={opt}>
                                {opt}
                              </option>
                            ))}
                          </select>
                        </label>
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>
              <div className="mainMenuFilterRowRight">
                {taskMenuCaseFilter ? (
                  <button type="button" className="btn" onClick={() => setTaskMenuCaseFilter(null)}>
                    Show all tasks
                  </button>
                ) : null}
                <button type="button" className="btn primary" onClick={() => setGlobalTaskCreateOpen(true)}>
                  New task
                </button>
                <div className="tasksToolbarLayoutGroup">
                  <span className="tasksToolbarLayoutLabel">View</span>
                  <select
                    className="tasksToolbarLayoutSelect"
                    value={uiPrefs.tasks_menu_layout}
                    onChange={(e) => setUiPreference('tasks_menu_layout', e.target.value as 'list' | 'kanban')}
                    aria-label="Task layout"
                  >
                    <option value="list">List</option>
                    <option value="kanban">Kanban</option>
                  </select>
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
              setSelectedCaseId(caseId)
              setView('case-menu')
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
          casesForPicker={cases}
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
      token={token}
      currentUserId={auth.me?.id ?? ''}
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
      showNewMatter={showNewMatter}
      onOpenNewMatter={onOpenNewMatter}
      onCloseNewMatter={onCloseNewMatter}
      onRefreshCases={onRefreshCases}
      onCaseCreated={onMainMenuCaseCreated}
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
    document.title = canaryDocumentTitle(canaryViewTitleSegment(view, caseDetail))
  }, [auth.loading, auth.token, auth.me, view, caseDetail])

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

  return (
    <div className="appShell">
      <AdminLoginUpdatePrompt token={auth.token} me={auth.me} canAdmin={canAdminConsole} />
      <header className="topbar">
        <div className="topbarMain">
          <nav className="topNav" aria-label="Primary">
            <button
              type="button"
              className={`navBtn ${view === 'main-menu' || view === 'case-menu' ? 'active' : ''}`}
              onClick={() => setView('main-menu')}
            >
              Main Menu
            </button>
            <button type="button" className={`navBtn ${view === 'calendar' ? 'active' : ''}`} onClick={() => setView('calendar')}>
              Calendar
            </button>
            <button
              type="button"
              className={`navBtn ${view === 'tasks' ? 'active' : ''}`}
              onClick={() => setView('tasks')}
            >
              Tasks
            </button>
            <button type="button" className={`navBtn ${view === 'contacts' ? 'active' : ''}`} onClick={() => setView('contacts')}>
              Contacts
            </button>
            <button type="button" className={`navBtn ${view === 'reports' ? 'active' : ''}`} onClick={() => setView('reports')}>
              Reports
            </button>
            <button
              type="button"
              className={`navBtn ${view === 'user-settings' ? 'active' : ''}`}
              onClick={() => setView('user-settings')}
            >
              User Settings
            </button>
            {canAdminConsole ? (
              <button
                type="button"
                className={`navBtn ${view === 'admin-console' ? 'active' : ''}`}
                onClick={() => setView('admin-console')}
              >
                Admin settings
              </button>
            ) : null}
          </nav>
        </div>
        <div className="topbarRight">
          <div className="muted">{auth.me?.email}</div>
          <button type="button" className="btn" onClick={auth.logout}>
            Sign out
          </button>
        </div>
      </header>
      <main
        className={
          view === 'case-menu'
            ? 'main main--caseView'
            : view === 'main-menu' || view === 'contacts' || view === 'tasks' || view === 'reports'
              ? 'main main--mainMenu'
              : 'main'
        }
      >
        {mainMenuCasesPanel ? (
          <div className={view === 'main-menu' ? 'mainMenuCasesHost' : 'mainMenuCasesHost mainMenuCasesHost--hidden'}>
            {mainMenuCasesPanel}
          </div>
        ) : null}
        {renderMainContent()}
      </main>
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
}: {
  token: string
  currentUserId: string
  onClose: () => void
  onCreated: () => void
}) {
  const { askConfirm } = useDialogs()
  const [matterDescription, setMatterDescription] = useState('')
  const [practiceArea, setPracticeArea] = useState('')
  const [feeEarner, setFeeEarner] = useState<string>(currentUserId)
  /** Active = open; Quote = quote (only these may be set on create). */
  const [newMatterStatus, setNewMatterStatus] = useState<'open' | 'quote'>('open')
  const [step, setStep] = useState<'details' | 'property' | 'description' | 'contacts'>('details')
  const [propertyDraft, setPropertyDraft] = useState<CasePropertyPayload | null>(null)
  const [users, setUsers] = useState<UserSummary[]>([])
  const [matterHeadTypes, setMatterHeadTypes] = useState<MatterHeadTypeOut[]>([])
  const [contacts, setContacts] = useState<ContactOut[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const [contactSearch, setContactSearch] = useState('')
  const [selectedGlobalContactId, setSelectedGlobalContactId] = useState<string | null>(null)
  const [contactErr, setContactErr] = useState<string | null>(null)
  /** Client contacts to link after the matter is created (Finish). */
  const [pendingClientLinks, setPendingClientLinks] = useState<NewMatterPendingClient[]>([])
  const [newContactFormKey, setNewContactFormKey] = useState(0)

  const hasClientOnMatter = pendingClientLinks.length > 0

  const selectedSubType = useMemo(() => {
    if (!practiceArea) return null
    return matterHeadTypes.flatMap((h) => h.sub_types).find((s) => s.id === practiceArea) ?? null
  }, [practiceArea, matterHeadTypes])

  useEffect(() => {
    setPropertyDraft(null)
  }, [practiceArea])

  useEffect(() => {
    let cancelled = false
    async function loadUsers() {
      try {
        const data = await apiFetch<UserSummary[]>('/users', { token })
        if (!cancelled) {
          const active = (Array.isArray(data) ? data : []).filter((u) => u.is_active)
          setUsers(active)
          setFeeEarner((prev) => {
            if (prev) return prev
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

  useEffect(() => {
    if (step !== 'contacts') return
    let cancelled = false
    async function loadContacts() {
      try {
        const data = await apiFetch<ContactOut[]>('/contacts', { token })
        if (!cancelled) setContacts(data)
      } catch {
        // ignore
      }
    }
    void loadContacts()
    return () => {
      cancelled = true
    }
  }, [step, token])

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
          <label className="field">
            <span>Matter type</span>
            <select
              value={practiceArea}
              onChange={(e) => setPracticeArea(e.target.value)}
              disabled={busy}
            >
              <option value="">— select —</option>
              {matterHeadTypes.map((head) => (
                <optgroup key={head.id} label={head.name}>
                  {head.sub_types.map((sub) => (
                    <option key={sub.id} value={sub.id}>{sub.name}</option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Fee earner</span>
            <select
              value={feeEarner}
              onChange={(e) => setFeeEarner(e.target.value)}
              disabled={busy}
              required
            >
              <option value="" disabled>
                Select fee earner
              </option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.display_name} ({u.email})
                </option>
              ))}
            </select>
          </label>
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
          {err ? <div className="error">{err}</div> : null}
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <button className="btn" onClick={onClose} disabled={busy}>
              Cancel
            </button>
            <button
              className="btn primary"
              disabled={busy || !practiceArea}
              onClick={() => {
                setErr(null)
                setContactErr(null)
                const sub = matterHeadTypes.flatMap((h) => h.sub_types).find((s) => s.id === practiceArea)
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
              <div className="list" style={{ maxHeight: 140, overflow: 'auto' }}>
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
                <input value={contactSearch} onChange={(e) => setContactSearch(e.target.value)} />
              </label>

              <div className="list" style={{ maxHeight: 160, overflow: 'auto' }}>
                {contacts
                  .filter((c) => {
                    const s = contactSearch.trim().toLowerCase()
                    if (!s) return true
                    return (
                      c.name.toLowerCase().includes(s) ||
                      (c.email ?? '').toLowerCase().includes(s) ||
                      (c.phone ?? '').toLowerCase().includes(s)
                    )
                  })
                  .slice(0, 25)
                  .map((c) => (
                    <div key={c.id} className="listCard row" style={{ justifyContent: 'space-between' }}>
                      <div>
                        <div className="listTitle">
                          {c.name} <span className="muted">· {c.type}</span>
                        </div>
                        <div className="muted">{c.email ?? c.phone ?? '—'}</div>
                      </div>
                      <button
                        className={`btn ${selectedGlobalContactId === c.id ? 'primary' : ''}`}
                        disabled={busy || pendingClientLinks.some((p) => p.contact_id === c.id)}
                        onClick={() => setSelectedGlobalContactId(c.id)}
                      >
                        {pendingClientLinks.some((p) => p.contact_id === c.id)
                          ? 'Added'
                          : selectedGlobalContactId === c.id
                            ? 'Selected'
                            : 'Select'}
                      </button>
                    </div>
                  ))}
                {contacts.length === 0 ? <div className="muted">No contacts yet.</div> : null}
              </div>

              <div className="row" style={{ justifyContent: 'flex-end' }}>
                <button
                  className="btn primary"
                  disabled={
                    busy ||
                    !selectedGlobalContactId ||
                    pendingClientLinks.some((p) => p.contact_id === selectedGlobalContactId)
                  }
                  onClick={() => {
                    if (!selectedGlobalContactId) return
                    const c = contacts.find((x) => x.id === selectedGlobalContactId)
                    if (!c) return
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
                    setSelectedGlobalContactId(null)
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
                      setContacts((prev) => {
                        const without = prev.filter((x) => x.id !== created.id)
                        return [created, ...without]
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
                      onCreated()
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
  },
  sortKey: 'reference' | 'client' | 'matter' | 'feeEarner' | 'status' | 'created',
  sortDir: 'asc' | 'desc',
): CaseOut[] {
  const s = search.trim()
  const filtered = s
    ? cases.filter((c) => caseMatchesMainMenuSearch(c, users, search))
    : filterMainMenuCases(
        cases,
        filters.matterTypes,
        filters.feeEarnerUserIds,
        filters.caseStatuses,
      )
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
  sortKey: 'reference' | 'client' | 'matter' | 'feeEarner' | 'status' | 'created'
  sortDir: 'asc' | 'desc'
  onSort: (k: 'reference' | 'client' | 'matter' | 'feeEarner' | 'status' | 'created') => void
  gridTemplateColumns?: string
  startColumnResize: (colIndex: number, startClientX: number, measureRow?: HTMLElement | null) => void
}) {
  const [caseCtx, setCaseCtx] = useState<null | { id: string; x: number; y: number }>(null)
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

  const rows = buildCaseTableRows(
    cases,
    users,
    search,
    {
      matterTypes: filterMatterTypes,
      feeEarnerUserIds: filterFeeEarnerUserIds,
      caseStatuses: filterCaseStatuses,
    },
    sortKey,
    sortDir,
  )

  return (
    <div className="card casesTableCard" style={{ padding: 0, overflow: 'hidden' }}>
      <div className="casesTableScroll">
        <div className="table">
        <div className="tr th" style={gridTemplateColumns ? { gridTemplateColumns } : undefined}>
          {(
            [
              ['reference', 'Reference'],
              ['client', 'Client name'],
              ['matter', 'Description'],
              ['feeEarner', 'Fee earner'],
              ['status', 'Status'],
            ] as const
          ).map(([k, label], colIndex) => (
            <div key={k} className="thCell">
              <button type="button" className="thbtn" onClick={() => onSort(k)}>
                {label}
              </button>
              {colIndex < 4 ? (
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
              className={['tr', 'rowbtn', rowActive ? 'active' : '', rowInactive ? 'casesRowInactive' : '']
                .filter(Boolean)
                .join(' ')}
              style={gridTemplateColumns ? { gridTemplateColumns } : undefined}
              onClick={() => onCaseRowFocus(c.id)}
              onDoubleClick={() => onSelect(c.id)}
              onContextMenu={(e) => {
                e.preventDefault()
                setCaseCtx({ id: c.id, x: e.clientX, y: e.clientY })
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
              <div className="td">
                {formatCaseStatusLabel(c.status)}
              </div>
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
          style={{ left: caseCtx.x, top: caseCtx.y, zIndex: 30 }}
          onMouseDown={(e) => e.stopPropagation()}
        >
          <div
            className="docContextItem"
            role="menuitem"
            tabIndex={0}
            onClick={() => {
              const id = caseCtx.id
              setCaseCtx(null)
              onSelect(id)
            }}
          >
            Open
          </div>
          <div
            className="docContextItem"
            role="menuitem"
            tabIndex={0}
            onClick={() => {
              const id = caseCtx.id
              setCaseCtx(null)
              onSelect(id, { docPanel: 'accounts' })
            }}
          >
            Accounts
          </div>
        </div>
      ) : null}
    </div>
  )
}

const MAIN_MENU_STATUS_FILTER_OPTIONS: { value: MainMenuCaseStatusFilter; label: string }[] = [
  { value: 'open', label: 'Active' },
  { value: 'quote', label: 'Quote' },
  { value: 'post_completion', label: 'Post-completion' },
  { value: 'closed', label: 'Closed' },
  { value: 'archived', label: 'Archived' },
]

function MainMenuCasesPanel({
  token,
  currentUserId,
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
  showNewMatter,
  onOpenNewMatter,
  onCloseNewMatter,
  onRefreshCases,
  onCaseCreated,
}: {
  token: string
  currentUserId: string
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
  sortKey: 'reference' | 'client' | 'matter' | 'feeEarner' | 'status' | 'created'
  sortDir: 'asc' | 'desc'
  onSort: (k: 'reference' | 'client' | 'matter' | 'feeEarner' | 'status' | 'created') => void
  showNewMatter: boolean
  onOpenNewMatter: () => void
  onCloseNewMatter: () => void
  onRefreshCases: () => void
  onCaseCreated: () => void | Promise<void>
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
      if (!byId.has(u.id)) byId.set(u.id, u)
    }
    return Array.from(byId.values())
      .sort((a, b) => a.display_name.localeCompare(b.display_name))
      .map((u) => ({ value: u.id, label: u.display_name }))
  }, [users])

  const activeFilterCount =
    filterMatterTypes.length + filterFeeEarnerUserIds.length + filterCaseStatuses.length

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
            <button type="button" className="btn" onClick={onOpenNewMatter}>
              New matter
            </button>
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
                    options={MAIN_MENU_STATUS_FILTER_OPTIONS}
                    selected={filterCaseStatuses}
                    onChange={(next) => onFilterCaseStatusesChange(next as MainMenuCaseStatusFilter[])}
                    open={openFilterField === 'status'}
                    onOpenChange={(open) => setOpenFilterField(open ? 'status' : null)}
                  />
                </div>
              </div>
            </div>
            <SearchInput
              placeholder="Search cases (reference, client, matter, fee earner, status)…"
              value={caseSearch}
              onChange={(e) => setCaseSearch(e.target.value)}
              onClear={() => setCaseSearch('')}
              className="mainMenuSearchInput"
              aria-label="Search cases"
            />
          </div>
        </div>
      </div>
      {showNewMatter ? (
        <NewMatterModal
          token={token}
          currentUserId={currentUserId}
          onClose={onCloseNewMatter}
          onCreated={onCaseCreated}
        />
      ) : null}
      <CasesTable
        cases={cases}
        users={users}
        search={caseSearch}
        filterMatterTypes={filterMatterTypes}
        filterFeeEarnerUserIds={filterFeeEarnerUserIds}
        filterCaseStatuses={filterCaseStatuses}
        gridTemplateColumns={gridTemplateColumns}
        startColumnResize={startColumnResize}
        caseListFocusId={caseListFocusId}
        onCaseRowFocus={onCaseRowFocus}
        onSelect={onSelectCase}
        sortKey={sortKey}
        sortDir={sortDir}
        onSort={onSort}
      />
    </div>
  )
}

function AdminMatters({ token }: { token: string }) {
  const { askConfirm } = useDialogs()
  const [heads, setHeads] = useState<MatterHeadTypeOut[]>([])
  const [selectedHeadId, setSelectedHeadId] = useState<string | null>(null)
  const [selectedSubId, setSelectedSubId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [subPrecCats, setSubPrecCats] = useState<PrecedentCategoryOut[]>([])
  const [newPrecCatName, setNewPrecCatName] = useState('')

  // Sub type form state
  const [newSubName, setNewSubName] = useState('')
  const [editingSubId, setEditingSubId] = useState<string | null>(null)
  const [editingSubName, setEditingSubName] = useState('')

  // Sub type config state (prefix + menus)
  const [prefixInput, setPrefixInput] = useState('')
  const [newMenuName, setNewMenuName] = useState('')
  const [editingMenuId, setEditingMenuId] = useState<string | null>(null)
  const [editingMenuName, setEditingMenuName] = useState('')

  async function loadHeads() {
    try {
      const data = await apiFetch<MatterHeadTypeOut[]>('/matter-types', { token })
      setHeads(data)
    } catch (e: any) {
      setErr(e?.message ?? 'Failed to load matter types')
    }
  }

  useEffect(() => { void loadHeads() }, [token])

  useEffect(() => {
    if (!selectedSubId) {
      setSubPrecCats([])
      return
    }
    void apiFetch<PrecedentCategoryOut[]>(`/matter-types/sub-types/${selectedSubId}/precedent-categories`, { token })
      .then(setSubPrecCats)
      .catch(() => setSubPrecCats([]))
  }, [selectedSubId, token])

  const selectedHead = heads.find((h) => h.id === selectedHeadId) ?? null
  const selectedSub: MatterSubTypeOut | null =
    selectedHead?.sub_types.find((s) => s.id === selectedSubId) ?? null

  // Sync prefix input when selected sub changes
  useEffect(() => {
    setPrefixInput(selectedSub?.prefix ?? '')
    setNewPrecCatName('')
    setNewMenuName('')
    setEditingMenuId(null)
  }, [selectedSubId, selectedHead])

  // Clear sub selection when head changes
  useEffect(() => {
    setSelectedSubId(null)
  }, [selectedHeadId])

  const smallBtn = { padding: '3px 8px', fontSize: '0.82em' } as const
  const inlineInput = { flex: 1, width: 'auto' } as const

  // ── Head type visibility (canonical list from Canary; no add/rename/delete) ──

  async function setHeadHidden(id: string, is_hidden: boolean) {
    setBusy(true); setErr(null)
    try {
      await apiFetch(`/matter-types/heads/${id}`, { token, method: 'PATCH', json: { is_hidden } })
      await loadHeads()
    } catch (e: any) { setErr(e?.message ?? 'Failed') } finally { setBusy(false) }
  }

  // ── Sub type actions ─────────────────────────────────────────────────────

  async function addSub() {
    if (!newSubName.trim() || !selectedHeadId) return
    setBusy(true); setErr(null)
    try {
      await apiFetch(`/matter-types/heads/${selectedHeadId}/sub-types`, { token, json: { name: newSubName.trim() } })
      setNewSubName('')
      await loadHeads()
    } catch (e: any) { setErr(e?.message ?? 'Failed') } finally { setBusy(false) }
  }

  async function saveSubRename(id: string) {
    if (!editingSubName.trim()) return
    setBusy(true); setErr(null)
    try {
      await apiFetch(`/matter-types/sub-types/${id}`, { token, method: 'PATCH', json: { name: editingSubName.trim() } })
      setEditingSubId(null)
      await loadHeads()
    } catch (e: any) { setErr(e?.message ?? 'Failed') } finally { setBusy(false) }
  }

  async function deleteSub(id: string) {
    const ok = await askConfirm({
      title: 'Delete sub type',
      message:
        'Delete this sub type? You must remove its sub-menus, precedent categories, and precedents scoped to it first; hiding the head matter type does not delete sub-types or menus.',
      danger: true,
      confirmLabel: 'Delete',
    })
    if (!ok) return
    setBusy(true); setErr(null)
    try {
      await apiFetch(`/matter-types/sub-types/${id}`, { token, method: 'DELETE' })
      if (selectedSubId === id) setSelectedSubId(null)
      await loadHeads()
    } catch (e: any) { setErr(e?.message ?? 'Failed') } finally { setBusy(false) }
  }

  // ── Prefix action ────────────────────────────────────────────────────────

  async function savePrefix() {
    if (!selectedSubId) return
    setBusy(true); setErr(null)
    try {
      await apiFetch(`/matter-types/sub-types/${selectedSubId}`, {
        token, method: 'PATCH', json: { prefix: prefixInput.trim() || null },
      })
      await loadHeads()
    } catch (e: any) { setErr(e?.message ?? 'Failed') } finally { setBusy(false) }
  }

  // ── Menu actions ─────────────────────────────────────────────────────────

  async function addMenu() {
    if (!newMenuName.trim() || !selectedSubId) return
    setBusy(true); setErr(null)
    try {
      await apiFetch(`/matter-types/sub-types/${selectedSubId}/menus`, { token, json: { name: newMenuName.trim() } })
      setNewMenuName('')
      await loadHeads()
    } catch (e: any) { setErr(e?.message ?? 'Failed') } finally { setBusy(false) }
  }

  async function saveMenuRename(id: string) {
    if (!editingMenuName.trim()) return
    setBusy(true); setErr(null)
    try {
      await apiFetch(`/matter-types/menus/${id}`, { token, method: 'PATCH', json: { name: editingMenuName.trim() } })
      setEditingMenuId(null)
      await loadHeads()
    } catch (e: any) { setErr(e?.message ?? 'Failed') } finally { setBusy(false) }
  }

  async function deleteMenu(id: string) {
    const ok = await askConfirm({
      title: 'Remove menu',
      message: 'Remove this menu?',
      danger: true,
      confirmLabel: 'Remove',
    })
    if (!ok) return
    setBusy(true); setErr(null)
    try {
      await apiFetch(`/matter-types/menus/${id}`, { token, method: 'DELETE' })
      await loadHeads()
    } catch (e: any) { setErr(e?.message ?? 'Failed') } finally { setBusy(false) }
  }

  return (
    <div className="stack">
      {err ? <div className="error">{err}</div> : null}

      {/* ── Row 1: head types + sub types ─────────────────────────── */}
      <div className="row" style={{ gap: 24, alignItems: 'flex-start' }}>

        {/* Head matter types */}
        <div className="card" style={{ flex: 1 }}>
          <h3 style={{ marginTop: 0 }}>Head matter types</h3>
          <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
            Head types are defined by Canary and sync from the product seed. Hide a head here if your firm does not use that area of law (it disappears from fee-earner matter pickers but stays in the database for existing matters).
          </p>
          <div className="list">
            {heads.map((h) => (
              <div
                key={h.id}
                className="listCard row"
                style={{
                  justifyContent: 'space-between',
                  cursor: 'pointer',
                  background: selectedHeadId === h.id ? 'rgba(37,99,235,0.1)' : undefined,
                  opacity: h.is_hidden ? 0.72 : undefined,
                }}
                onClick={() => setSelectedHeadId(h.id)}
              >
                <span className="listTitle">
                  {h.name}
                  {h.is_hidden ? <span className="muted" style={{ marginLeft: 8, fontWeight: 400 }}>(hidden)</span> : null}
                </span>
                <label
                  className="row"
                  style={{ gap: 6, alignItems: 'center', fontSize: 13 }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <input
                    type="checkbox"
                    checked={Boolean(h.is_hidden)}
                    disabled={busy}
                    onChange={(e) => void setHeadHidden(h.id, e.target.checked)}
                  />
                  <span>Hidden</span>
                </label>
              </div>
            ))}
            {heads.length === 0 && <div className="muted" style={{ padding: '6px 0' }}>No head types yet.</div>}
          </div>
        </div>

        {/* Sub matter types */}
        <div className="card" style={{ flex: 1 }}>
          <h3 style={{ marginTop: 0 }}>
            Sub matter types{selectedHead ? ` — ${selectedHead.name}` : ''}
          </h3>
          {!selectedHead ? (
            <div className="muted">Select a head type on the left to manage its sub types.</div>
          ) : (
            <>
              <div className="list">
                {selectedHead.sub_types.map((s) => (
                  <div
                    key={s.id}
                    className="listCard row"
                    style={{
                      justifyContent: 'space-between',
                      cursor: 'pointer',
                      background: selectedSubId === s.id ? 'rgba(37,99,235,0.1)' : undefined,
                    }}
                    onClick={() => setSelectedSubId(s.id)}
                  >
                    {editingSubId === s.id ? (
                      <input
                        style={inlineInput}
                        value={editingSubName}
                        onChange={(e) => setEditingSubName(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter') void saveSubRename(s.id); if (e.key === 'Escape') setEditingSubId(null) }}
                        autoFocus
                        disabled={busy}
                        onClick={(e) => e.stopPropagation()}
                      />
                    ) : (
                      <span className="listTitle">{s.name}</span>
                    )}
                    <div className="row" style={{ gap: 4 }} onClick={(e) => e.stopPropagation()}>
                      {editingSubId === s.id ? (
                        <>
                          <button className="btn" style={smallBtn} disabled={busy} onClick={() => void saveSubRename(s.id)}>Save</button>
                          <button className="btn" style={smallBtn} disabled={busy} onClick={() => setEditingSubId(null)}>Cancel</button>
                        </>
                      ) : (
                        <>
                          <button className="btn" style={smallBtn} disabled={busy} onClick={() => { setEditingSubId(s.id); setEditingSubName(s.name) }}>Rename</button>
                          <button className="btn danger" style={smallBtn} disabled={busy} onClick={() => void deleteSub(s.id)}>Delete</button>
                        </>
                      )}
                    </div>
                  </div>
                ))}
                {selectedHead.sub_types.length === 0 && (
                  <div className="muted" style={{ padding: '6px 0' }}>No sub types yet.</div>
                )}
              </div>
              <div className="row" style={{ marginTop: 10, gap: 6 }}>
                <input
                  style={inlineInput}
                  placeholder="New sub type name…"
                  value={newSubName}
                  onChange={(e) => setNewSubName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') void addSub() }}
                  disabled={busy}
                />
                <button className="btn primary" disabled={busy || !newSubName.trim()} onClick={() => void addSub()}>Add</button>
              </div>
            </>
          )}
        </div>

      </div>

      {/* ── Row 2: sub type config (shown when a sub type is selected) ── */}
      {selectedSub && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>
            Sub type config — <span style={{ fontWeight: 400 }}>{selectedSub.name}</span>
          </h3>
          <div className="row" style={{ gap: 24, alignItems: 'flex-start' }}>

            {/* Pre-fix */}
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>Pre-fix</div>
              <div className="muted" style={{ marginBottom: 8, fontSize: '0.9em' }}>
                Pre-filled into the Description field when a user creates a new matter of this type.
              </div>
              <div className="row" style={{ gap: 6 }}>
                <input
                  style={inlineInput}
                  placeholder="Pre-fix text…"
                  value={prefixInput}
                  onChange={(e) => setPrefixInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') void savePrefix() }}
                  disabled={busy}
                />
                <button
                  className="btn primary"
                  disabled={busy || prefixInput === (selectedSub.prefix ?? '')}
                  onClick={() => void savePrefix()}
                >
                  Save
                </button>
              </div>
              {selectedSub.prefix && (
                <div className="muted" style={{ marginTop: 6, fontSize: '0.85em' }}>
                  Current: <em>{selectedSub.prefix}</em>
                </div>
              )}
            </div>

            {/* Default menus */}
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>Default menus</div>
              <div className="muted" style={{ marginBottom: 8, fontSize: '0.9em' }}>
                Additional menus shown on the case page (alongside Contacts).
              </div>
              <div className="list">
                {selectedSub.menus.map((m) => (
                  <div key={m.id} className="listCard row" style={{ justifyContent: 'space-between' }}>
                    {editingMenuId === m.id ? (
                      <input
                        style={inlineInput}
                        value={editingMenuName}
                        onChange={(e) => setEditingMenuName(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter') void saveMenuRename(m.id); if (e.key === 'Escape') setEditingMenuId(null) }}
                        autoFocus
                        disabled={busy}
                      />
                    ) : (
                      <span className="listTitle">{m.name}</span>
                    )}
                    <div className="row" style={{ gap: 4 }}>
                      {editingMenuId === m.id ? (
                        <>
                          <button className="btn" style={smallBtn} disabled={busy} onClick={() => void saveMenuRename(m.id)}>Save</button>
                          <button className="btn" style={smallBtn} disabled={busy} onClick={() => setEditingMenuId(null)}>Cancel</button>
                        </>
                      ) : (
                        <>
                          <button className="btn" style={smallBtn} disabled={busy} onClick={() => { setEditingMenuId(m.id); setEditingMenuName(m.name) }}>Rename</button>
                          <button className="btn danger" style={smallBtn} disabled={busy} onClick={() => void deleteMenu(m.id)}>Remove</button>
                        </>
                      )}
                    </div>
                  </div>
                ))}
                {selectedSub.menus.length === 0 && (
                  <div className="muted" style={{ padding: '6px 0' }}>No additional menus configured.</div>
                )}
              </div>
              <div className="row" style={{ marginTop: 10, gap: 6 }}>
                <select
                  style={inlineInput}
                  value={newMenuName}
                  onChange={(e) => setNewMenuName(e.target.value)}
                  disabled={busy}
                >
                  <option value="">— select menu —</option>
                  {CASE_MENU_OPTIONS.filter(
                    (opt) => !selectedSub.menus.some((m) => m.name === opt)
                  ).map((opt) => (
                    <option key={opt} value={opt}>{opt}</option>
                  ))}
                </select>
                <button className="btn primary" disabled={busy || !newMenuName} onClick={() => void addMenu()}>Add</button>
              </div>
            </div>

          </div>

          <div style={{ marginTop: 24, paddingTop: 20, borderTop: '1px solid var(--border)' }}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>Precedent categories</div>
            <div className="muted" style={{ marginBottom: 8, fontSize: '0.9em' }}>
              Letter, document, and e-mail precedents for cases of this sub-type are grouped under these categories. The first category is selected by default in the precedent picker.
            </div>
            <div className="row" style={{ gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
              <input
                style={{ minWidth: 160, ...inlineInput }}
                placeholder="New category name…"
                value={newPrecCatName}
                onChange={(e) => setNewPrecCatName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    void (async () => {
                      if (!newPrecCatName.trim() || !selectedSubId || busy) return
                      setBusy(true)
                      setErr(null)
                      try {
                        await apiFetch(`/matter-types/sub-types/${selectedSubId}/precedent-categories`, {
                          token,
                          json: { name: newPrecCatName.trim(), sort_order: subPrecCats.length },
                        })
                        setNewPrecCatName('')
                        const next = await apiFetch<PrecedentCategoryOut[]>(
                          `/matter-types/sub-types/${selectedSubId}/precedent-categories`,
                          { token },
                        )
                        setSubPrecCats(next)
                      } catch (e: any) {
                        setErr(e?.message ?? 'Failed to add category')
                      } finally {
                        setBusy(false)
                      }
                    })()
                  }
                }}
                disabled={busy}
              />
              <button
                type="button"
                className="btn primary"
                disabled={busy || !newPrecCatName.trim() || !selectedSubId}
                onClick={async () => {
                  if (!newPrecCatName.trim() || !selectedSubId) return
                  setBusy(true)
                  setErr(null)
                  try {
                    await apiFetch(`/matter-types/sub-types/${selectedSubId}/precedent-categories`, {
                      token,
                      json: { name: newPrecCatName.trim(), sort_order: subPrecCats.length },
                    })
                    setNewPrecCatName('')
                    const next = await apiFetch<PrecedentCategoryOut[]>(
                      `/matter-types/sub-types/${selectedSubId}/precedent-categories`,
                      { token },
                    )
                    setSubPrecCats(next)
                  } catch (e: any) {
                    setErr(e?.message ?? 'Failed to add category')
                  } finally {
                    setBusy(false)
                  }
                }}
              >
                Add category
              </button>
            </div>
            <div className="list" style={{ maxHeight: 200, overflow: 'auto' }}>
              {subPrecCats.map((c) => (
                <div key={c.id} className="listCard row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
                  <span className="listTitle">{c.name}</span>
                  <button
                    type="button"
                    className="btn danger"
                    style={{ fontSize: 12, padding: '4px 10px' }}
                    disabled={busy}
                    onClick={async () => {
                      const ok = await askConfirm({
                        title: 'Remove category',
                        message: `Remove category “${c.name}”? You cannot remove a category that still has precedents.`,
                        danger: true,
                        confirmLabel: 'Remove',
                      })
                      if (!ok) return
                      setBusy(true)
                      setErr(null)
                      try {
                        await apiFetch(`/matter-types/sub-types/${selectedSubId}/precedent-categories/${c.id}`, {
                          token,
                          method: 'DELETE',
                        })
                        const next = await apiFetch<PrecedentCategoryOut[]>(
                          `/matter-types/sub-types/${selectedSubId}/precedent-categories`,
                          { token },
                        )
                        setSubPrecCats(next)
                      } catch (e: any) {
                        setErr(e?.message ?? 'Failed to remove category')
                      } finally {
                        setBusy(false)
                      }
                    }}
                  >
                    Remove
                  </button>
                </div>
              ))}
              {subPrecCats.length === 0 ? (
                <div className="muted" style={{ padding: 8 }}>No categories yet — add one before uploading precedents for this sub-type.</div>
              ) : null}
            </div>
          </div>

        </div>
      )}

    </div>
  )
}

/** Random 6-character lowercase hex for a new custom precedent reference (uniqueness enforced server-side). */
function suggestedPrecedentReferenceHex(): string {
  try {
    const a = new Uint8Array(3)
    crypto.getRandomValues(a)
    return Array.from(a, (b) => b.toString(16).padStart(2, '0')).join('')
  } catch {
    return Array.from({ length: 6 }, () => Math.floor(Math.random() * 16).toString(16)).join('')
  }
}

function PrecedentNamePencilIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
    </svg>
  )
}

function AdminPrecedents({ token }: { token: string }) {
  const { askConfirm } = useDialogs()
  const [items, setItems] = useState<PrecedentOut[]>([])
  const [matterHeads, setMatterHeads] = useState<MatterHeadTypeOut[]>([])
  const [uploadHeadTypeId, setUploadHeadTypeId] = useState('')
  const [uploadSubTypeId, setUploadSubTypeId] = useState('')
  const [uploadCats, setUploadCats] = useState<PrecedentCategoryOut[]>([])
  const [uploadCatsLoading, setUploadCatsLoading] = useState(false)
  const [uploadCatsFetchErr, setUploadCatsFetchErr] = useState<string | null>(null)
  /** Specific category id, or GLOBAL_PRECEDENT_SCOPE for “all categories under sub-type”. */
  const [uploadCategoryId, setUploadCategoryId] = useState(GLOBAL_PRECEDENT_SCOPE)
  const [fileInputKey, setFileInputKey] = useState(0)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [reference, setReference] = useState(() => suggestedPrecedentReferenceHex())
  const [kind, setKind] = useState<'letter' | 'email' | 'document'>('letter')
  const [file, setFile] = useState<File | null>(null)
  const [mergePanelOpen, setMergePanelOpen] = useState(false)
  const [mergeRows, setMergeRows] = useState<MergeCodeCatalogOut[]>([])
  const [mergeLoading, setMergeLoading] = useState(false)
  const [mergeSaving, setMergeSaving] = useState(false)
  const [mergeFilter, setMergeFilter] = useState('')
  const [mergeImportKey, setMergeImportKey] = useState(0)
  const [mergeMsg, setMergeMsg] = useState<string | null>(null)
  const [nameEditId, setNameEditId] = useState<string | null>(null)
  const [nameDraft, setNameDraft] = useState('')
  const precedentNameInputRef = useRef<HTMLInputElement | null>(null)
  const [firmSettings, setFirmSettings] = useState<FirmSettingsOut | null>(null)
  const [lhBusy, setLhBusy] = useState(false)
  const [lhFileKey, setLhFileKey] = useState(0)

  const matterTypeOptions = useMemo(
    () => matterHeads.map((h) => ({ id: h.id, label: h.name })),
    [matterHeads],
  )

  const uploadSubTypeOptions = useMemo(() => {
    if (!uploadHeadTypeId || uploadHeadTypeId === GLOBAL_PRECEDENT_SCOPE) return []
    const h = matterHeads.find((x) => x.id === uploadHeadTypeId)
    return (h?.sub_types ?? []).map((s) => ({ id: s.id, label: s.name }))
  }, [matterHeads, uploadHeadTypeId])

  const headIsGlobal = uploadHeadTypeId === GLOBAL_PRECEDENT_SCOPE
  const scopeFormComplete = useMemo(() => {
    if (!uploadHeadTypeId) return false
    if (headIsGlobal) return true
    if (!uploadSubTypeId) return false
    if (uploadSubTypeId === GLOBAL_PRECEDENT_SCOPE) return true
    return Boolean(uploadCategoryId)
  }, [uploadHeadTypeId, headIsGlobal, uploadSubTypeId, uploadCategoryId])

  const mergeFiltered = useMemo(() => {
    const q = mergeFilter.trim().toLowerCase()
    if (!q) return mergeRows
    return mergeRows.filter(
      (r) => r.code.toLowerCase().includes(q) || r.description.toLowerCase().includes(q),
    )
  }, [mergeRows, mergeFilter])

  useEffect(() => {
    if (
      !uploadSubTypeId ||
      uploadSubTypeId === GLOBAL_PRECEDENT_SCOPE ||
      uploadHeadTypeId === GLOBAL_PRECEDENT_SCOPE
    ) {
      setUploadCats([])
      setUploadCategoryId(GLOBAL_PRECEDENT_SCOPE)
      setUploadCatsFetchErr(null)
      return
    }
    setUploadCatsLoading(true)
    setUploadCatsFetchErr(null)
    void apiFetch<PrecedentCategoryOut[]>(`/matter-types/sub-types/${uploadSubTypeId}/precedent-categories`, { token })
      .then((list) => {
        setUploadCats(list)
        setUploadCategoryId(GLOBAL_PRECEDENT_SCOPE)
      })
      .catch((e: unknown) => {
        setUploadCats([])
        setUploadCategoryId(GLOBAL_PRECEDENT_SCOPE)
        setUploadCatsFetchErr((e as ApiError)?.message ?? 'Could not load precedent categories for this sub-type')
      })
      .finally(() => setUploadCatsLoading(false))
  }, [uploadSubTypeId, uploadHeadTypeId, token])

  async function load() {
    setBusy(true)
    setErr(null)
    try {
      const [data, heads, firm] = await Promise.all([
        apiFetch<PrecedentOut[]>('/precedents', { token }),
        apiFetch<MatterHeadTypeOut[]>('/matter-types', { token }),
        apiFetch<FirmSettingsOut>('/admin/firm-settings', { token }),
      ])
      setItems(data)
      setMatterHeads(heads)
      setFirmSettings(firm)
    } catch (e: any) {
      setErr(e?.message ?? 'Failed to load precedents')
    } finally {
      setBusy(false)
    }
  }

  async function loadMergeCatalog() {
    setMergeLoading(true)
    setMergeMsg(null)
    try {
      const rows = await apiFetch<MergeCodeCatalogOut[]>('/admin/merge-codes', { token })
      setMergeRows(rows)
    } catch (e2: unknown) {
      setErr((e2 as ApiError)?.message ?? 'Could not load merge codes')
    } finally {
      setMergeLoading(false)
    }
  }

  async function saveMergeCatalog() {
    setMergeSaving(true)
    setMergeMsg(null)
    setErr(null)
    try {
      const rows = await apiFetch<MergeCodeCatalogOut[]>('/admin/merge-codes', {
        token,
        method: 'PATCH',
        json: { items: mergeRows.map((r) => ({ code: r.code, description: r.description })) },
      })
      setMergeRows(rows)
      setMergeMsg(`Saved ${rows.length} codes.`)
    } catch (e2: unknown) {
      setErr((e2 as ApiError)?.message ?? 'Save merge codes failed')
    } finally {
      setMergeSaving(false)
    }
  }

  async function exportMergeCatalog() {
    setMergeMsg(null)
    try {
      const auth = String(token ?? '').trim()
      if (!auth) throw new Error('You are not signed in. Refresh the page and log in again.')
      const xh = new Headers()
      applyAuthHeaders(xh, auth)
      const res = await fetch(apiUrl('/admin/merge-codes/export.xlsx'), { headers: xh })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        const msg = typeof body?.detail === 'string' ? body.detail : `Export failed (${res.status})`
        throw new Error(msg)
      }
      const blob = await res.blob()
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = 'canary-merge-codes.xlsx'
      a.click()
      URL.revokeObjectURL(a.href)
      setMergeMsg('Download started.')
    } catch (e2: unknown) {
      setErr((e2 as Error)?.message ?? 'Export failed')
    }
  }

  async function importMergeCatalogFile(f: File) {
    setMergeSaving(true)
    setMergeMsg(null)
    setErr(null)
    try {
      const fd = new FormData()
      fd.append('upload', f)
      const body = await apiFetch<MergeCodeCatalogImportResult>('/admin/merge-codes/import', {
        token,
        method: 'POST',
        body: fd,
      })
      setMergeMsg(
        `Import: updated ${body.updated ?? 0} row(s); ${body.skipped_unknown ?? 0} unknown code(s) skipped.`,
      )
      await loadMergeCatalog()
      setMergeImportKey((k) => k + 1)
    } catch (e2: unknown) {
      setErr((e2 as Error)?.message ?? 'Import failed')
    } finally {
      setMergeSaving(false)
    }
  }

  useEffect(() => {
    void load()
  }, [token])

  useEffect(() => {
    if (mergePanelOpen) void loadMergeCatalog()
  }, [mergePanelOpen, token])

  async function patchLetterheadStyle(next: LetterheadStyle) {
    setLhBusy(true)
    setErr(null)
    try {
      await apiFetch<FirmSettingsOut>('/admin/firm-settings', {
        token,
        method: 'PATCH',
        json: { letterhead_style: next },
      })
      await load()
    } catch (e2: unknown) {
      setErr((e2 as ApiError)?.message ?? 'Could not update letterhead mode')
    } finally {
      setLhBusy(false)
    }
  }

  async function uploadLetterheadFile(f: File) {
    setLhBusy(true)
    setErr(null)
    try {
      const fd = new FormData()
      fd.append('upload', f)
      const body = await apiFetch<FirmSettingsOut>('/admin/firm-settings/letterhead', {
        token,
        method: 'POST',
        body: fd,
      })
      setFirmSettings(body)
      await load()
      setLhFileKey((k) => k + 1)
    } catch (e2: unknown) {
      setErr((e2 as Error)?.message ?? 'Letterhead upload failed')
    } finally {
      setLhBusy(false)
    }
  }

  async function clearLetterheadFile() {
    setLhBusy(true)
    setErr(null)
    try {
      await apiFetch<FirmSettingsOut>('/admin/firm-settings/letterhead', { token, method: 'DELETE' })
      await load()
      setLhFileKey((k) => k + 1)
    } catch (e2: unknown) {
      setErr((e2 as ApiError)?.message ?? 'Could not remove letterhead file')
    } finally {
      setLhBusy(false)
    }
  }

  useEffect(() => {
    if (uploadHeadTypeId === GLOBAL_PRECEDENT_SCOPE) {
      setUploadSubTypeId(GLOBAL_PRECEDENT_SCOPE)
      setUploadCategoryId(GLOBAL_PRECEDENT_SCOPE)
    }
  }, [uploadHeadTypeId])

  useEffect(() => {
    if (!nameEditId) return
    const id = requestAnimationFrame(() => {
      precedentNameInputRef.current?.focus()
      precedentNameInputRef.current?.select()
    })
    return () => cancelAnimationFrame(id)
  }, [nameEditId])

  async function commitPrecedentNameEdit(p: PrecedentOut) {
    const v = nameDraft.trim()
    if (!v) {
      setErr('Name cannot be empty.')
      return
    }
    if (v === p.name) {
      setNameEditId(null)
      return
    }
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/precedents/${p.id}`, {
        token,
        method: 'PATCH',
        json: { name: v },
      })
      setNameEditId(null)
      await load()
    } catch (e2: unknown) {
      setErr((e2 as ApiError)?.message ?? 'Failed to update name')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack">
      <div className="paneHead">
        <h3 style={{ margin: 0 }}>Precedents</h3>
        <button type="button" className="btn" onClick={() => void load()} disabled={busy}>
          Refresh
        </button>
      </div>
      {err ? <div className="error">{err}</div> : null}

      <div className="card" style={{ padding: 12, marginBottom: 16 }}>
        <h4 style={{ marginTop: 0 }}>Letterhead (Letter precedents only)</h4>
        <div className="muted" style={{ marginBottom: 12 }}>
          <strong>Digital</strong> copies the uploaded .docx <strong>headers and footers</strong> into each{' '}
          <strong>Letter</strong> precedent before merge codes run. Keep logos and firm blocks in the header/footer so the
          letter body can sit on page 1 underneath. <strong>Pre-printed</strong> skips any overlay (headed stationery).
          Embedded logos in the uploaded .docx are copied into each composed letter automatically.
        </div>
        {firmSettings ? (
          <div className="stack" style={{ gap: 10 }}>
            <div className="row" style={{ gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
              <label className="row" style={{ gap: 6, alignItems: 'center', cursor: lhBusy ? 'default' : 'pointer' }}>
                <input
                  type="radio"
                  name="letterhead-style"
                  checked={firmSettings.letterhead_style === 'preprinted'}
                  disabled={lhBusy}
                  onChange={() => void patchLetterheadStyle('preprinted')}
                />
                Pre-printed
              </label>
              <label className="row" style={{ gap: 6, alignItems: 'center', cursor: lhBusy ? 'default' : 'pointer' }}>
                <input
                  type="radio"
                  name="letterhead-style"
                  checked={firmSettings.letterhead_style === 'digital'}
                  disabled={lhBusy}
                  onChange={() => void patchLetterheadStyle('digital')}
                />
                Digital
              </label>
            </div>
            {firmSettings.letterhead_style === 'digital' ? (
              <div className="row" style={{ gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                <label className="btn" style={{ cursor: lhBusy ? 'not-allowed' : 'pointer' }}>
                  Browse…
                  <input
                    key={lhFileKey}
                    type="file"
                    accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    disabled={lhBusy}
                    style={{ display: 'none' }}
                    onChange={(ev) => {
                      const f = ev.target.files?.[0]
                      ev.target.value = ''
                      if (f) void uploadLetterheadFile(f)
                    }}
                  />
                </label>
                <span className="muted">
                  {firmSettings.letterhead_original_filename
                    ? `Current file: ${firmSettings.letterhead_original_filename}`
                    : 'No .docx uploaded yet.'}
                </span>
                {firmSettings.letterhead_original_filename ? (
                  <button type="button" className="btn danger" disabled={lhBusy} onClick={() => void clearLetterheadFile()}>
                    Remove letterhead file
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : (
          <div className="muted">Loading letterhead settings…</div>
        )}
      </div>

      <div className="card" style={{ padding: 12 }}>
        <div className="muted" style={{ marginBottom: 8 }}>
          Upload a template. Choose <strong>Global</strong> at any level to widen availability: <strong>Matter type</strong>{' '}
          Global = all cases; <strong>Sub-type</strong> Global = all sub-types under the chosen matter type;{' '}
          <strong>Precedent category</strong> Global = all categories under the chosen sub-type. Otherwise pick a specific
          value. Add named categories under <strong>Admin → Matters</strong> if you need a specific category.
        </div>
        {uploadCatsFetchErr ? <div className="error" style={{ marginBottom: 8 }}>{uploadCatsFetchErr}</div> : null}
        <div className="stack">
          <label className="field">
            <span>Name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="field">
            <span>Reference</span>
            <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <input
                className="mono"
                value={reference}
                onChange={(e) => setReference(e.target.value)}
                maxLength={200}
                required
                aria-required
                autoComplete="off"
                spellCheck={false}
                placeholder="e.g. a1f9c2"
                title="Required. Must be unique among precedents."
              />
              <button
                type="button"
                className="btn"
                disabled={busy}
                title="Replace with another random 6-character hex"
                onClick={() => setReference(suggestedPrecedentReferenceHex())}
              >
                New suggestion
              </button>
            </div>
            <span className="muted" style={{ fontSize: 12, marginTop: 4, display: 'block' }}>
              Required for every custom precedent. A random 6-character hex is suggested; change it if you prefer. Must be
              unique.
            </span>
          </label>
          <label className="field">
            <span>Type</span>
            <select value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
              <option value="letter">Letter</option>
              <option value="email">E-mail</option>
              <option value="document">Document</option>
            </select>
          </label>
          <label className="field">
            <span>Matter type</span>
            <select
              value={uploadHeadTypeId}
              onChange={(e) => {
                const v = e.target.value
                setUploadHeadTypeId(v)
                setUploadSubTypeId('')
                setUploadCategoryId(GLOBAL_PRECEDENT_SCOPE)
              }}
              disabled={busy}
            >
              <option value="">— select —</option>
              <option value={GLOBAL_PRECEDENT_SCOPE}>Global (all cases)</option>
              {matterTypeOptions.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Sub-type</span>
            <select
              value={uploadSubTypeId}
              onChange={(e) => {
                setUploadSubTypeId(e.target.value)
                setUploadCategoryId(GLOBAL_PRECEDENT_SCOPE)
              }}
              disabled={busy || !uploadHeadTypeId || headIsGlobal}
            >
              {!uploadHeadTypeId ? (
                <option value="">Select a matter type first</option>
              ) : headIsGlobal ? (
                <option value={GLOBAL_PRECEDENT_SCOPE}>Global</option>
              ) : uploadSubTypeOptions.length === 0 ? (
                <option value="">No sub-types for this matter type</option>
              ) : (
                <>
                  <option value="">— select —</option>
                  <option value={GLOBAL_PRECEDENT_SCOPE}>Global (all sub-types under this matter type)</option>
                  {uploadSubTypeOptions.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.label}
                    </option>
                  ))}
                </>
              )}
            </select>
          </label>
          {uploadHeadTypeId &&
          !headIsGlobal &&
          uploadSubTypeId &&
          uploadSubTypeId !== GLOBAL_PRECEDENT_SCOPE &&
          uploadCatsLoading ? (
            <div className="muted" style={{ fontSize: 13 }}>
              Loading precedent categories…
            </div>
          ) : null}
          {uploadHeadTypeId &&
          !headIsGlobal &&
          uploadSubTypeId &&
          uploadSubTypeId !== GLOBAL_PRECEDENT_SCOPE &&
          !uploadCatsLoading &&
          !uploadCatsFetchErr &&
          uploadCats.length === 0 ? (
            <div className="error" style={{ fontSize: 13 }}>
              No named precedent categories exist for this sub-type. You can still choose <strong>Global</strong> above
              to apply to all categories, or add categories under <strong>Admin → Matters</strong>.
            </div>
          ) : null}
          {uploadHeadTypeId &&
          !headIsGlobal &&
          uploadSubTypeId &&
          uploadSubTypeId !== GLOBAL_PRECEDENT_SCOPE &&
          !uploadCatsLoading ? (
            <label className="field">
              <span>Precedent category</span>
              <select
                value={uploadCategoryId}
                onChange={(e) => setUploadCategoryId(e.target.value)}
                disabled={busy}
              >
                <option value={GLOBAL_PRECEDENT_SCOPE}>Global (all categories under this sub-type)</option>
                {uploadCats.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <label className="field">
            <span>File</span>
            <input
              key={fileInputKey}
              type="file"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          <button
            type="button"
            className="btn primary"
            disabled={
              busy ||
              uploadCatsLoading ||
              !name.trim() ||
              !reference.trim() ||
              !file ||
              !scopeFormComplete
            }
            onClick={async () => {
              if (!file || !scopeFormComplete) return
              setBusy(true)
              setErr(null)
              try {
                let mh: string = GLOBAL_PRECEDENT_SCOPE
                let ms: string = GLOBAL_PRECEDENT_SCOPE
                let mc: string = GLOBAL_PRECEDENT_SCOPE
                if (uploadHeadTypeId && uploadHeadTypeId !== GLOBAL_PRECEDENT_SCOPE) {
                  mh = uploadHeadTypeId
                  if (uploadSubTypeId && uploadSubTypeId !== GLOBAL_PRECEDENT_SCOPE) {
                    ms = uploadSubTypeId
                    mc = uploadCategoryId || GLOBAL_PRECEDENT_SCOPE
                  } else {
                    ms = GLOBAL_PRECEDENT_SCOPE
                    mc = GLOBAL_PRECEDENT_SCOPE
                  }
                }
                const fd = new FormData()
                fd.set('name', name.trim())
                fd.set('reference', reference.trim())
                fd.set('kind', kind)
                fd.set('matter_head_type_id', mh)
                fd.set('matter_sub_type_id', ms)
                fd.set('category_id', mc)
                fd.set('upload', file)
                if (!String(token ?? '').trim()) {
                  throw new Error('You are not signed in or your session token is empty. Refresh the page and log in again.')
                }
                await apiFetch<PrecedentOut>('/precedents', { token, method: 'POST', body: fd })
                setName('')
                setReference(suggestedPrecedentReferenceHex())
                setFile(null)
                setFileInputKey((k) => k + 1)
                await load()
              } catch (e: unknown) {
                setErr((e as { message?: string }).message ?? 'Upload failed')
              } finally {
                setBusy(false)
              }
            }}
          >
            Upload
          </button>
        </div>
      </div>
      <div className="card" style={{ padding: 12 }}>
        <div
          className="row"
          style={{
            justifyContent: 'space-between',
            alignItems: 'flex-start',
            marginBottom: mergePanelOpen ? 8 : 0,
            gap: 12,
          }}
        >
          <div className="stack" style={{ gap: 10, flex: 1, minWidth: 0 }}>
            <span className="muted" style={{ fontSize: 13 }}>
              Merge codes — stored in the database; edit descriptions here or round-trip via Excel. Codes themselves
              come from Canary releases (sync on startup).
            </span>
            <div
              style={{
                fontSize: 13,
                padding: '10px 12px',
                border: '1px solid var(--border)',
                borderRadius: 6,
                background: 'var(--panel)',
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: 6 }}>Formatting modifiers</div>
              <p className="muted" style={{ margin: '0 0 8px', fontSize: 12 }}>
                Optional prefix before a code in Word templates. Plain <code>[CODE]</code> merges without extra
                formatting.
              </p>
              <table
                className="allow-select"
                style={{ width: '100%', maxWidth: 420, borderCollapse: 'collapse', fontSize: 12 }}
              >
                <thead>
                  <tr>
                    <th
                      style={{
                        textAlign: 'left',
                        padding: '4px 8px 4px 0',
                        borderBottom: '1px solid var(--border)',
                        fontWeight: 600,
                        width: '28%',
                      }}
                    >
                      Modifier
                    </th>
                    <th
                      style={{
                        textAlign: 'left',
                        padding: '4px 0',
                        borderBottom: '1px solid var(--border)',
                        fontWeight: 600,
                      }}
                    >
                      Effect on merged value
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td style={{ padding: '4px 8px 4px 0', fontFamily: 'monospace', verticalAlign: 'top' }}>
                      <code>b:</code>
                    </td>
                    <td style={{ padding: '4px 0', verticalAlign: 'top' }}>Bold</td>
                  </tr>
                  <tr>
                    <td style={{ padding: '4px 8px 4px 0', fontFamily: 'monospace', verticalAlign: 'top' }}>
                      <code>i:</code>
                    </td>
                    <td style={{ padding: '4px 0', verticalAlign: 'top' }}>Italic</td>
                  </tr>
                  <tr>
                    <td style={{ padding: '4px 8px 4px 0', fontFamily: 'monospace', verticalAlign: 'top' }}>
                      <code>u:</code>
                    </td>
                    <td style={{ padding: '4px 0', verticalAlign: 'top' }}>Underline</td>
                  </tr>
                </tbody>
              </table>
              <p className="muted" style={{ margin: '8px 0 0', fontSize: 12 }}>
                Combine modifiers in any order, e.g. <code>[bi:LAST_NAME]</code> (bold + italic) or{' '}
                <code>[biu:MATTER_DESCRIPTION]</code> (all three). Example:{' '}
                <code>Re: [b:MATTER_DESCRIPTION]</code>
              </p>
            </div>
          </div>
          <button
            type="button"
            className="btn"
            style={{ fontSize: 12, flexShrink: 0 }}
            onClick={() => {
              setMergePanelOpen((v) => !v)
              if (mergePanelOpen) setMergeMsg(null)
            }}
          >
            {mergePanelOpen ? 'Hide' : 'View/Edit'}
          </button>
        </div>
        {mergePanelOpen ? (
          <div className="stack" style={{ gap: 10 }}>
            <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <label className="field" style={{ flex: '1 1 220px', marginBottom: 0 }}>
                <span className="muted" style={{ fontSize: 12 }}>
                  Filter
                </span>
                <input
                  value={mergeFilter}
                  onChange={(e) => setMergeFilter(e.target.value)}
                  placeholder="Code or description…"
                  disabled={mergeLoading || mergeSaving}
                />
              </label>
              <button
                type="button"
                className="btn primary"
                disabled={mergeLoading || mergeSaving || mergeRows.length === 0}
                onClick={() => void saveMergeCatalog()}
              >
                Save descriptions
              </button>
              <button
                type="button"
                className="btn"
                disabled={mergeLoading || mergeSaving}
                onClick={() => void exportMergeCatalog()}
              >
                Export Excel
              </button>
              <label className="btn" style={{ cursor: mergeSaving ? 'not-allowed' : 'pointer' }}>
                Import Excel…
                <input
                  key={mergeImportKey}
                  type="file"
                  accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                  disabled={mergeSaving}
                  style={{ display: 'none' }}
                  onChange={(ev) => {
                    const f = ev.target.files?.[0]
                    ev.target.value = ''
                    if (f) void importMergeCatalogFile(f)
                  }}
                />
              </label>
              <button
                type="button"
                className="btn"
                disabled={mergeLoading}
                onClick={() => void loadMergeCatalog()}
              >
                Reload
              </button>
            </div>
            {mergeMsg ? <div className="muted" style={{ fontSize: 13 }}>{mergeMsg}</div> : null}
            {mergeLoading ? (
              <div className="muted">Loading merge codes…</div>
            ) : (
              <div
                style={{
                  maxHeight: 420,
                  overflow: 'auto',
                  border: '1px solid var(--border)',
                  borderRadius: 6,
                  background: 'var(--panel)',
                }}
              >
                <table
                  className="allow-select"
                  style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}
                >
                  <thead style={{ position: 'sticky', top: 0, background: 'var(--panel2)', zIndex: 1 }}>
                    <tr>
                      <th
                        style={{
                          textAlign: 'left',
                          padding: '8px',
                          borderBottom: '1px solid var(--border)',
                          width: '22%',
                          color: 'var(--text)',
                          fontWeight: 600,
                        }}
                      >
                        Code
                      </th>
                      <th
                        style={{
                          textAlign: 'left',
                          padding: '8px',
                          borderBottom: '1px solid var(--border)',
                          color: 'var(--text)',
                          fontWeight: 600,
                        }}
                      >
                        Description (editable)
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {mergeFiltered.map((r) => (
                      <tr key={r.code}>
                        <td
                          style={{
                            padding: '6px 8px',
                            fontFamily: 'monospace',
                            color: 'var(--text)',
                            verticalAlign: 'top',
                            borderBottom: '1px solid var(--border)',
                          }}
                        >
                          {r.code}
                        </td>
                        <td style={{ padding: '4px 8px', borderBottom: '1px solid var(--border)' }}>
                          <textarea
                            value={r.description}
                            rows={2}
                            disabled={mergeSaving}
                            style={{ width: '100%', resize: 'vertical', fontFamily: 'inherit', fontSize: 13 }}
                            onChange={(e) => {
                              const v = e.target.value
                              setMergeRows((prev) => prev.map((x) => (x.code === r.code ? { ...x, description: v } : x)))
                            }}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {mergeFiltered.length === 0 && mergeRows.length > 0 ? (
                  <div className="muted" style={{ padding: 12 }}>
                    No rows match the filter.
                  </div>
                ) : null}
                {!mergeLoading && mergeRows.length === 0 ? (
                  <div className="muted" style={{ padding: 12 }}>
                    No catalog rows yet — ensure the backend has run a migration and restarted so merge codes sync from the
                    server defaults.
                  </div>
                ) : null}
              </div>
            )}
          </div>
        ) : null}
      </div>
      <div className="list">
        {items.map((p) => (
          <div
            key={p.id}
            className="listCard row precedentListCardRow"
            style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}
          >
            <div style={{ flex: '1 1 200px', minWidth: 0 }}>
              {nameEditId === p.id ? (
                <div className="precedentNameRow precedentNameRow--edit">
                  <input
                    ref={precedentNameInputRef}
                    className="precedentAdminNameInput"
                    value={nameDraft}
                    disabled={busy}
                    maxLength={300}
                    aria-label="Precedent name"
                    onChange={(e) => setNameDraft(e.target.value)}
                    onBlur={() => void commitPrecedentNameEdit(p)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        void commitPrecedentNameEdit(p)
                      }
                      if (e.key === 'Escape') {
                        e.preventDefault()
                        setNameEditId(null)
                        setErr(null)
                      }
                    }}
                  />
                </div>
              ) : (
                <div className="precedentNameRow">
                  <span className="listTitle precedentNameText">{p.name}</span>
                  <button
                    type="button"
                    className="btn precedentNameEditBtn"
                    disabled={busy}
                    title="Edit name"
                    aria-label="Edit precedent name"
                    onClick={() => {
                      setNameEditId(p.id)
                      setNameDraft(p.name)
                    }}
                  >
                    <PrecedentNamePencilIcon />
                  </button>
                </div>
              )}
              <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
                <span className="mono">{p.reference}</span> · {p.kind}
              </div>
              <div className="muted" style={{ fontSize: 12 }}>
                {p.original_filename}
              </div>
              <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                {p.scope_summary || p.category_name || '—'}
              </div>
            </div>
            <div className="row" style={{ gap: 8 }}>
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => openOnlyOfficePrecedentEditor(p.id)}
              >
                Edit in OnlyOffice
              </button>
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => {
                  void (async () => {
                    const ok = await askConfirm({
                      title: 'Delete precedent',
                      message: `Delete precedent "${p.name}"?`,
                      danger: true,
                      confirmLabel: 'Delete',
                    })
                    if (!ok) return
                    setBusy(true)
                    apiFetch(`/precedents/${p.id}`, { token, method: 'DELETE' })
                      .then(() => load())
                      .catch((e: any) => setErr(e?.message ?? 'Delete failed'))
                      .finally(() => setBusy(false))
                  })()
                }}
              >
                Remove
              </button>
            </div>
          </div>
        ))}
        {items.length === 0 ? <div className="muted">No precedents yet.</div> : null}
      </div>
    </div>
  )
}

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
  const [accountLoadErr, setAccountLoadErr] = useState<string | null>(null)

  const [passkeys, setPasskeys] = useState<WebAuthnCredentialOut[]>([])
  const [pkErr, setPkErr] = useState<string | null>(null)
  const [pkLabel, setPkLabel] = useState('')

  const [emailPref, setEmailPref] = useState<'desktop' | 'outlook_web'>('desktop')
  const [outlookUrl, setOutlookUrl] = useState(DEFAULT_OUTLOOK_WEB_MAIL_URL)
  const [emailSaveErr, setEmailSaveErr] = useState<string | null>(null)
  const [emailSaveOk, setEmailSaveOk] = useState(false)
  const [emailBusy, setEmailBusy] = useState(false)

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
    setOutlookUrl((account.email_outlook_web_url ?? '').trim() || DEFAULT_OUTLOOK_WEB_MAIL_URL)
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

  async function start2faSetup() {
    setFaErr(null)
    setFaOk(false)
    setSecBusy(true)
    try {
      const res = await apiFetch<{ secret: string; otpauth_uri: string }>('/auth/2fa/setup', { method: 'POST', token })
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
          <h3 style={{ marginTop: 0 }}>Appearance</h3>
          <p className="muted" style={{ marginTop: 0 }}>
            Font, accent colour, page background, and light or dark mode are saved to your account and follow you on any
            device or browser when you sign in.
          </p>
          <div className="stack" style={{ maxWidth: 480, gap: 12 }}>
            <label className="field">
              <span>Font</span>
              <select
                value={appFont}
                onChange={(e) => {
                  setAppFont(e.target.value)
                  setThemeSavedHint(false)
                }}
              >
                {FONT_OPTIONS.map((o) => (
                  <option key={o.label} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
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
              <button
                type="button"
                className="btn primary"
                disabled={busy || secBusy}
                onClick={() => void start2faSetup()}
              >
                Begin 2FA setup
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
            Choose how <strong>New → E-mail</strong> opens compose: your system&apos;s default mail program (
            <code>mailto:</code>) or Outlook on the web. Attach case files with <strong>Compose from matter</strong> in
            the Canary Outlook or Thunderbird add-in after compose opens.
          </p>
          <div className="stack" style={{ maxWidth: 560, gap: 14, marginTop: 12 }}>
            <label className="field">
              <span>Compose with</span>
              <select
                value={emailPref}
                onChange={(e) => {
                  void (async () => {
                    const v = e.target.value as 'desktop' | 'outlook_web'
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
                aria-label="How to open e-mail compose from a matter"
              >
                <option value="desktop">Desktop client (system default)</option>
                <option value="outlook_web">Outlook web</option>
              </select>
            </label>
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

function AdminMatterContacts({ token }: { token: string }) {
  const { askConfirm } = useDialogs()
  const [rows, setRows] = useState<MatterContactTypeOut[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [newSlug, setNewSlug] = useState('')
  const [newLabel, setNewLabel] = useState('')
  const [newSort, setNewSort] = useState(90)

  async function load() {
    setBusy(true)
    setErr(null)
    try {
      const r = await apiFetch<MatterContactTypeOut[]>('/admin/matter-contact-types', { token })
      setRows(r)
    } catch (e: unknown) {
      setErr((e as ApiError)?.message ?? 'Failed to load contact types')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    void load()
  }, [token])

  return (
    <div className="stack">
      <div className="paneHead">
        <h3 style={{ margin: 0 }}>Contacts</h3>
        <button type="button" className="btn" onClick={() => void load()} disabled={busy}>
          Refresh
        </button>
      </div>
      {err ? <div className="error">{err}</div> : null}
      <p className="muted" style={{ marginTop: 0 }}>
        These labels populate the matter contact type dropdown. The four system types (Client, Lawyers, New lender,
        Existing lender) cannot be deleted or renamed.
      </p>
      <div className="card stack" style={{ gap: 10, maxWidth: 720 }}>
        <div className="muted" style={{ fontWeight: 600 }}>
          Add type
        </div>
        <div className="row" style={{ flexWrap: 'wrap', gap: 8, alignItems: 'flex-end' }}>
          <label className="field" style={{ flex: '1 1 140px', marginBottom: 0 }}>
            <span>Slug</span>
            <input
              value={newSlug}
              onChange={(e) => setNewSlug(e.target.value)}
              placeholder="e.g. surveyor"
              disabled={busy}
            />
          </label>
          <label className="field" style={{ flex: '1 1 160px', marginBottom: 0 }}>
            <span>Label</span>
            <input value={newLabel} onChange={(e) => setNewLabel(e.target.value)} disabled={busy} />
          </label>
          <label className="field" style={{ flex: '0 0 80px', marginBottom: 0 }}>
            <span>Sort</span>
            <input type="number" value={newSort} onChange={(e) => setNewSort(Number(e.target.value))} disabled={busy} />
          </label>
          <button
            type="button"
            className="btn primary"
            disabled={busy || !newSlug.trim() || !newLabel.trim()}
            onClick={async () => {
              setBusy(true)
              setErr(null)
              try {
                await apiFetch('/admin/matter-contact-types', {
                  token,
                  method: 'POST',
                  json: { slug: newSlug.trim(), label: newLabel.trim(), sort_order: newSort },
                })
                setNewSlug('')
                setNewLabel('')
                await load()
              } catch (e: unknown) {
                setErr((e as ApiError)?.message ?? 'Could not add contact type')
              } finally {
                setBusy(false)
              }
            }}
          >
            Add
          </button>
        </div>
      </div>
      <div className="list" style={{ marginTop: 12 }}>
        {rows.map((r) => (
          <div
            key={r.id}
            className="listCard row"
            style={{ justifyContent: 'space-between', alignItems: 'center', gap: 12 }}
          >
            <div style={{ minWidth: 0 }}>
              <div className="listTitle">
                {r.label}{' '}
                {r.is_system ? (
                  <span className="muted" style={{ fontSize: 12 }}>
                    (system)
                  </span>
                ) : null}
              </div>
              <div className="muted" style={{ fontSize: 13 }}>
                slug: <span className="mono">{r.slug}</span> · sort {r.sort_order}
              </div>
            </div>
            {!r.is_system ? (
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={async () => {
                  const ok = await askConfirm({
                    title: 'Delete contact type',
                    message: `Remove “${r.label}”? Existing matter contacts keep this slug until edited.`,
                    danger: true,
                    confirmLabel: 'Delete',
                  })
                  if (!ok) return
                  setBusy(true)
                  setErr(null)
                  try {
                    await apiFetch(`/admin/matter-contact-types/${r.id}`, { token, method: 'DELETE' })
                    await load()
                  } catch (e: unknown) {
                    setErr((e as ApiError)?.message ?? 'Delete failed')
                  } finally {
                    setBusy(false)
                  }
                }}
              >
                Delete
              </button>
            ) : (
              <span className="muted" style={{ fontSize: 13 }}>
                Cannot delete
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function AdminConsole({ token, refreshMe }: { token: string; refreshMe: () => Promise<void> }) {
  const [tab, setTab] = useState<
    | 'firm'
    | 'users'
    | 'matters'
    | 'billing'
    | 'email'
    | 'deploy'
    | 'submenus'
    | 'tasks'
    | 'contacts'
    | 'precedents'
    | 'audit'
  >('firm')
  const adminSubtitle =
    tab === 'firm'
      ? 'Trading name, registered name, and firm address for precedent merge codes.'
      : tab === 'email'
      ? 'Org-wide e-mail integration (mailto vs Microsoft 365).'
      : tab === 'deploy'
        ? 'Deploy, updates, and file storage usage.'
        : tab === 'audit'
        ? 'Activity and audit trail.'
        : tab === 'users'
          ? 'User accounts and permission categories.'
          : tab === 'matters'
            ? 'Matter types and defaults.'
            : tab === 'billing'
              ? 'Billing configuration.'
              : tab === 'submenus'
                ? 'Case sub-menu configuration.'
                : tab === 'tasks'
                  ? 'Task templates and defaults.'
                  : tab === 'contacts'
                    ? 'Matter contact types.'
                    : tab === 'precedents'
                      ? 'Precedent library.'
                      : ''
  return (
    <div
      className="mainMenuShell mainMenuShell--surface"
      style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}
    >
      <div className="paneHead">
        <div>
          <h2 style={{ margin: 0 }}>Admin settings</h2>
          <div className="muted" style={{ marginTop: 4 }}>{adminSubtitle}</div>
        </div>
        <div className="row" style={{ alignItems: 'center', flexWrap: 'wrap', gap: 4 }}>
          <button type="button" className={`navBtn ${tab === 'firm' ? 'active' : ''}`} onClick={() => setTab('firm')}>
            Firm details
          </button>
          <button type="button" className={`navBtn ${tab === 'users' ? 'active' : ''}`} onClick={() => setTab('users')}>
            Users
          </button>
          <button type="button" className={`navBtn ${tab === 'matters' ? 'active' : ''}`} onClick={() => setTab('matters')}>
            Matters
          </button>
          <button type="button" className={`navBtn ${tab === 'billing' ? 'active' : ''}`} onClick={() => setTab('billing')}>
            Billing
          </button>
          <button type="button" className={`navBtn ${tab === 'email' ? 'active' : ''}`} onClick={() => setTab('email')}>
            E-mail
          </button>
          <button type="button" className={`navBtn ${tab === 'deploy' ? 'active' : ''}`} onClick={() => setTab('deploy')}>
            Deploy
          </button>
          <button type="button" className={`navBtn ${tab === 'submenus' ? 'active' : ''}`} onClick={() => setTab('submenus')}>
            Sub-Menus
          </button>
          <button type="button" className={`navBtn ${tab === 'tasks' ? 'active' : ''}`} onClick={() => setTab('tasks')}>
            Tasks
          </button>
          <button type="button" className={`navBtn ${tab === 'contacts' ? 'active' : ''}`} onClick={() => setTab('contacts')}>
            Contacts
          </button>
          <button type="button" className={`navBtn ${tab === 'precedents' ? 'active' : ''}`} onClick={() => setTab('precedents')}>
            Precedents
          </button>
          <button type="button" className={`navBtn ${tab === 'audit' ? 'active' : ''}`} onClick={() => setTab('audit')}>
            Audit
          </button>
        </div>
      </div>
      <div style={{ flex: 1, minHeight: 0, marginTop: 12, overflow: 'auto' }}>
        {tab === 'firm' ? (
          <AdminFirmDetails token={token} />
        ) : tab === 'users' ? (
          <AdminUsers token={token} embedded />
        ) : tab === 'matters' ? (
          <AdminMatters token={token} />
        ) : tab === 'billing' ? (
          <AdminBilling token={token} />
        ) : tab === 'email' ? (
          <AdminEmail token={token} onSaved={() => void refreshMe()} />
        ) : tab === 'deploy' ? (
          <AdminDeploy token={token} />
        ) : tab === 'submenus' ? (
          <AdminSubMenus token={token} />
        ) : tab === 'tasks' ? (
          <AdminTasks token={token} />
        ) : tab === 'contacts' ? (
          <AdminMatterContacts token={token} />
        ) : tab === 'precedents' ? (
          <AdminPrecedents token={token} />
        ) : (
          <AdminAudit token={token} embedded />
        )}
      </div>
    </div>
  )
}

function AdminUsers({ token, embedded }: { token: string; embedded?: boolean }) {
  const { askConfirm, alert: showAlert } = useDialogs()
  const [users, setUsers] = useState<AdminUserPublic[]>([])
  const [categories, setCategories] = useState<UserPermissionCategoryOut[]>([])
  const [firmSettings, setFirmSettings] = useState<FirmSettingsOut | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [newInitials, setNewInitials] = useState('')
  const [newJobTitle, setNewJobTitle] = useState('')
  const [newUserCategoryId, setNewUserCategoryId] = useState('')
  const [creatingUser, setCreatingUser] = useState(false)
  const [editingUser, setEditingUser] = useState<AdminUserPublic | null>(null)
  const [editEmail, setEditEmail] = useState('')
  const [editDisplayName, setEditDisplayName] = useState('')
  const [editInitials, setEditInitials] = useState('')
  const [editJobTitle, setEditJobTitle] = useState('')
  const [editRole, setEditRole] = useState<'admin' | 'user'>('user')
  const [editActive, setEditActive] = useState(true)
  const [editCategoryId, setEditCategoryId] = useState('')
  const [editPw, setEditPw] = useState('')
  const [editPw2, setEditPw2] = useState('')
  const [newCatName, setNewCatName] = useState('')
  const [newCat, setNewCat] = useState({
    perm_fee_earner: false,
    perm_post_client: false,
    perm_post_office: false,
    perm_approve_payments: false,
    perm_approve_invoices: false,
    perm_admin: false,
  })
  const [editCatId, setEditCatId] = useState<string | null>(null)
  const [editCatName, setEditCatName] = useState('')
  const [editCat, setEditCat] = useState({
    perm_fee_earner: false,
    perm_post_client: false,
    perm_post_office: false,
    perm_approve_payments: false,
    perm_approve_invoices: false,
    perm_admin: false,
  })

  async function load(): Promise<AdminUserPublic[] | null> {
    setBusy(true)
    setErr(null)
    try {
      const [u, c, f] = await Promise.all([
        apiFetch<AdminUserPublic[]>('/admin/users', { token }),
        apiFetch<UserPermissionCategoryOut[]>('/admin/permission-categories', { token }),
        apiFetch<FirmSettingsOut>('/admin/firm-settings', { token }),
      ])
      setUsers(u)
      setCategories(c)
      setFirmSettings(f)
      return u
    } catch (e: any) {
      setErr(e?.message ?? 'Failed to load users')
      return null
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  function openUserEditor(u: AdminUserPublic) {
    setErr(null)
    setEditingUser(u)
    setEditEmail(u.email)
    setEditDisplayName(u.display_name)
    setEditInitials(u.initials ?? '')
    setEditJobTitle(u.job_title ?? '')
    setEditRole(u.role)
    setEditActive(u.is_active)
    setEditCategoryId(u.permission_category_id ?? '')
    setEditPw('')
    setEditPw2('')
  }

  return (
    <div className="stack">
      <div className="paneHead">
        {embedded ? <h3 style={{ margin: 0 }}>Users</h3> : <h2>Admin · Users</h2>}
        <button type="button" className="btn" onClick={() => void load()}>
          Refresh
        </button>
      </div>
      {err && !editingUser ? <div className="error">{err}</div> : null}
      <div className="card">
        <h3>User categories</h3>
        <p className="muted" style={{ marginTop: 0 }}>
          Assign each user to a category to control ledger posting and approvals. Categories are visible only in the admin
          console.
        </p>
        <div className="stack" style={{ gap: 10, maxWidth: 720 }}>
          <div className="row" style={{ flexWrap: 'wrap', gap: 8, alignItems: 'flex-end' }}>
            <label className="field" style={{ flex: '1 1 200px', marginBottom: 0 }}>
              <span>New category name</span>
              <input value={newCatName} onChange={(e) => setNewCatName(e.target.value)} disabled={busy} />
            </label>
            <button
              type="button"
              className="btn primary"
              disabled={busy || !newCatName.trim()}
              onClick={async () => {
                setBusy(true)
                setErr(null)
                try {
                  await apiFetch('/admin/permission-categories', {
                    token,
                    method: 'POST',
                    json: { name: newCatName.trim(), ...newCat },
                  })
                  setNewCatName('')
                  await load()
                } catch (e: any) {
                  setErr(e?.message ?? 'Could not create category')
                } finally {
                  setBusy(false)
                }
              }}
            >
              Add category
            </button>
          </div>
          <div className="row" style={{ flexWrap: 'wrap', gap: 12 }}>
            {(
              [
                ['perm_fee_earner', 'Fee-earner files'],
                ['perm_post_client', 'Post client'],
                ['perm_post_office', 'Post office'],
                ['perm_approve_payments', 'Approve payments'],
                ['perm_approve_invoices', 'Approve invoices'],
                ['perm_admin', 'Admin'],
              ] as const
            ).map(([k, label]) => (
              <label key={k} className="row" style={{ gap: 6, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={newCat[k]}
                  disabled={busy}
                  onChange={(e) => setNewCat((p) => ({ ...p, [k]: e.target.checked }))}
                />
                <span style={{ fontSize: 13 }}>{label}</span>
              </label>
            ))}
          </div>
        </div>
        <div className="list" style={{ marginTop: 12 }}>
          {categories.map((c) => (
            <div key={c.id} className="listCard stack" style={{ gap: 10 }}>
              {editCatId === c.id ? (
                <div className="stack" style={{ gap: 10 }}>
                  <label className="field" style={{ marginBottom: 0 }}>
                    <span>Category name</span>
                    <input value={editCatName} onChange={(e) => setEditCatName(e.target.value)} disabled={busy} />
                  </label>
                  <div className="row" style={{ flexWrap: 'wrap', gap: 12 }}>
                    {(
                      [
                        ['perm_fee_earner', 'Fee-earner files'],
                        ['perm_post_client', 'Post client'],
                        ['perm_post_office', 'Post office'],
                        ['perm_approve_payments', 'Approve payments'],
                        ['perm_approve_invoices', 'Approve invoices'],
                        ['perm_admin', 'Admin'],
                      ] as const
                    ).map(([k, label]) => (
                      <label key={k} className="row" style={{ gap: 6, cursor: 'pointer' }}>
                        <input
                          type="checkbox"
                          checked={editCat[k]}
                          disabled={busy}
                          onChange={(e) => setEditCat((p) => ({ ...p, [k]: e.target.checked }))}
                        />
                        <span style={{ fontSize: 13 }}>{label}</span>
                      </label>
                    ))}
                  </div>
                  <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                    <button
                      type="button"
                      className="btn primary"
                      disabled={busy || !editCatName.trim()}
                      onClick={async () => {
                        setBusy(true)
                        setErr(null)
                        try {
                          await apiFetch(`/admin/permission-categories/${c.id}`, {
                            token,
                            method: 'PATCH',
                            json: {
                              name: editCatName.trim(),
                              perm_fee_earner: editCat.perm_fee_earner,
                              perm_post_client: editCat.perm_post_client,
                              perm_post_office: editCat.perm_post_office,
                              perm_approve_payments: editCat.perm_approve_payments,
                              perm_approve_invoices: editCat.perm_approve_invoices,
                              perm_admin: editCat.perm_admin,
                            },
                          })
                          setEditCatId(null)
                          await load()
                        } catch (e: any) {
                          setErr(e?.message ?? 'Could not update category')
                        } finally {
                          setBusy(false)
                        }
                      }}
                    >
                      Save changes
                    </button>
                    <button
                      type="button"
                      className="btn"
                      disabled={busy}
                      onClick={() => setEditCatId(null)}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                  <div>
                    <div className="listTitle">{c.name}</div>
                    <div className="muted" style={{ fontSize: 12 }}>
                      {[
                        c.perm_fee_earner ? 'Fee-earner' : null,
                        c.perm_post_client ? 'Client post' : null,
                        c.perm_post_office ? 'Office post' : null,
                        c.perm_approve_payments ? 'Approve payments' : null,
                        c.perm_approve_invoices ? 'Approve invoices' : null,
                        c.perm_admin ? 'Admin' : null,
                      ]
                        .filter(Boolean)
                        .join(' · ') || 'No permissions'}
                    </div>
                  </div>
                  <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                    <button
                      type="button"
                      className="btn"
                      disabled={busy}
                      onClick={() => {
                        setEditCatId(c.id)
                        setEditCatName(c.name)
                        setEditCat({
                          perm_fee_earner: c.perm_fee_earner,
                          perm_post_client: c.perm_post_client,
                          perm_post_office: c.perm_post_office,
                          perm_approve_payments: c.perm_approve_payments,
                          perm_approve_invoices: c.perm_approve_invoices,
                          perm_admin: c.perm_admin ?? false,
                        })
                      }}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="btn danger"
                      disabled={busy}
                      onClick={async () => {
                        const ok = await askConfirm({
                          title: 'Delete category',
                          message: `Delete category “${c.name}”?`,
                          danger: true,
                          confirmLabel: 'Delete',
                        })
                        if (!ok) return
                        setBusy(true)
                        setErr(null)
                        try {
                          await apiFetch(`/admin/permission-categories/${c.id}`, { token, method: 'DELETE' })
                          await load()
                        } catch (e: any) {
                          setErr(e?.message ?? 'Delete failed (is it still assigned to users?)')
                        } finally {
                          setBusy(false)
                        }
                      }}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
          {categories.length === 0 ? <div className="muted">No categories yet.</div> : null}
        </div>
      </div>
      <div className="card">
        <h3>Security</h3>
        <p className="muted" style={{ marginTop: 0 }}>
          Organisation-wide sign-in policy. When enabled, users who are not admins must enable an authenticator app (2FA) or
          register at least one passkey before using matters, tasks, and other areas of the app. Admins should enable 2FA or
          passkeys before turning this on so they can support users who get stuck.
        </p>
        <label className="row" style={{ gap: 10, alignItems: 'center', cursor: firmSettings ? 'pointer' : 'default' }}>
          <input
            type="checkbox"
            checked={Boolean(firmSettings?.mandate_two_factor)}
            disabled={busy || !firmSettings}
            onChange={async (e) => {
              if (!firmSettings) return
              const next = e.target.checked
              setBusy(true)
              setErr(null)
              try {
                const updated = await apiFetch<FirmSettingsOut>('/admin/firm-settings', {
                  token,
                  method: 'PATCH',
                  json: { mandate_two_factor: next },
                })
                setFirmSettings(updated)
              } catch (err: unknown) {
                setErr((err as ApiError).message ?? 'Could not update security settings')
              } finally {
                setBusy(false)
              }
            }}
          />
          <span>Mandate two-factor authentication</span>
        </label>
        <label className="row" style={{ gap: 10, alignItems: 'center', cursor: firmSettings ? 'pointer' : 'default', marginTop: 12 }}>
          <input
            type="checkbox"
            checked={Boolean(firmSettings?.mandate_password_rotation)}
            disabled={busy || !firmSettings}
            onChange={async (e) => {
              if (!firmSettings) return
              const next = e.target.checked
              setBusy(true)
              setErr(null)
              try {
                const updated = await apiFetch<FirmSettingsOut>('/admin/firm-settings', {
                  token,
                  method: 'PATCH',
                  json: next
                    ? {
                        mandate_password_rotation: true,
                        password_rotation_days: firmSettings.password_rotation_days ?? 90,
                      }
                    : { mandate_password_rotation: false, password_rotation_days: null },
                })
                setFirmSettings(updated)
              } catch (err: unknown) {
                setErr((err as ApiError).message ?? 'Could not update security settings')
              } finally {
                setBusy(false)
              }
            }}
          />
          <span>Require periodic password updates</span>
        </label>
        {firmSettings?.mandate_password_rotation ? (
          <label className="field" style={{ marginTop: 12, maxWidth: 280 }}>
            <span>Update every</span>
            <select
              value={String(firmSettings.password_rotation_days ?? 90)}
              disabled={busy}
              onChange={async (e) => {
                const days = Number(e.target.value)
                setBusy(true)
                setErr(null)
                try {
                  const updated = await apiFetch<FirmSettingsOut>('/admin/firm-settings', {
                    token,
                    method: 'PATCH',
                    json: { mandate_password_rotation: true, password_rotation_days: days },
                  })
                  setFirmSettings(updated)
                } catch (err: unknown) {
                  setErr((err as ApiError).message ?? 'Could not update password rotation interval')
                } finally {
                  setBusy(false)
                }
              }}
            >
              <option value="30">30 days</option>
              <option value="60">60 days</option>
              <option value="90">90 days</option>
              <option value="180">180 days</option>
              <option value="365">365 days</option>
            </select>
          </label>
        ) : null}
        <p className="muted" style={{ marginBottom: 0, fontSize: 13 }}>
          When enabled, users must choose a new password after the interval since their last change. Admins are exempt. Password
          reset e-mails require alert notifications under Admin → E-mail.
        </p>
      </div>
      <div className="card">
        <h3>Create user</h3>
        <p className="muted" style={{ marginTop: 0 }}>
          Every new user must be assigned a permission category (create one above if needed).
        </p>
        <div className="row" style={{ flexWrap: 'wrap', gap: 8, alignItems: 'flex-end' }}>
          <input placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
          <input placeholder="Display name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          <input
            placeholder="Initials (unique)"
            value={newInitials ?? ''}
            onChange={(e) => setNewInitials(e.target.value)}
            style={{ maxWidth: 120 }}
            title="Letters, digits, dot, underscore, hyphen; 1–12 characters"
          />
          <input
            placeholder="Job title (optional)"
            value={newJobTitle}
            onChange={(e) => setNewJobTitle(e.target.value)}
            style={{ minWidth: 160 }}
          />
          <input placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <label className="field" style={{ marginBottom: 0, minWidth: 200 }}>
            <span>Category</span>
            <select value={newUserCategoryId} onChange={(e) => setNewUserCategoryId(e.target.value)} disabled={busy}>
              <option value="">— Select category —</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <button
            className="btn primary"
            style={creatingUser ? { cursor: 'wait' } : undefined}
            disabled={
              busy ||
              creatingUser ||
              !email ||
              !displayName ||
              !(newInitials ?? '').trim() ||
              password.length < 12 ||
              !newUserCategoryId
            }
            onClick={async () => {
              setCreatingUser(true)
              setBusy(true)
              setErr(null)
              const prevBodyCursor = document.body.style.cursor
              document.body.style.cursor = 'wait'
              try {
                await apiFetch('/admin/users', {
                  token,
                  json: {
                    email,
                    display_name: displayName,
                    initials: (newInitials ?? '').trim(),
                    job_title: newJobTitle.trim() || null,
                    password,
                    permission_category_id: newUserCategoryId,
                  },
                })
                setEmail('')
                setDisplayName('')
                setNewInitials('')
                setNewJobTitle('')
                setPassword('')
                setNewUserCategoryId('')
                await load()
              } catch (e: unknown) {
                const msg = ((e as ApiError).message ?? '').trim()
                setErr(msg || 'Create failed')
              } finally {
                document.body.style.cursor = prevBodyCursor
                setBusy(false)
                setCreatingUser(false)
              }
            }}
          >
            {creatingUser ? 'Creating…' : 'Create'}
          </button>
        </div>
      </div>
      <div className="card">
        <h3>Users</h3>
        <p className="muted" style={{ marginTop: 0 }}>
          Edit a user to change e-mail, display name, job title, role, category, active state, or set a new password (optional).
        </p>
        <div className="list">
          {users.map((u) => (
            <div key={u.id} className="listCard row" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
              <div style={{ flex: '1 1 220px' }}>
                <div className="listTitle">
                  {u.email} <span className="muted">· {u.role}</span>
                </div>
                <div className="muted">
                  {u.display_name} ({u.initials ?? '—'}) · {u.is_active ? 'active' : 'disabled'} · 2FA{' '}
                  {u.is_2fa_enabled ? 'on' : 'off'}
                </div>
              </div>
              <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                <button type="button" className="btn" disabled={busy} onClick={() => openUserEditor(u)}>
                  Edit
                </button>
                <button
                  className="btn"
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true)
                    setErr(null)
                    try {
                      await apiFetch(`/admin/users/${u.id}`, { token, method: 'PATCH', json: { is_active: !u.is_active } })
                      await load()
                    } catch (e: any) {
                      setErr(e?.message ?? 'Update failed')
                    } finally {
                      setBusy(false)
                    }
                  }}
                >
                  {u.is_active ? 'Disable' : 'Enable'}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {editingUser ? (
        <div
          className="modalOverlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="admin-edit-user-title"
          onClick={() => !busy && setEditingUser(null)}
        >
          <div
            className="modal card modal--scrollBody"
            style={{ maxWidth: 520, width: 'min(520px, 94vw)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="paneHead">
              <div>
                <h2 id="admin-edit-user-title">Edit user</h2>
                <div className="muted" style={{ fontSize: 13 }}>
                  Same fields as create user. Under Sign-in security you can reset authenticator 2FA or set a new password (min 12 characters). Setting a new password clears their authenticator enrolment.
                </div>
              </div>
              <button type="button" className="btn" disabled={busy} onClick={() => setEditingUser(null)}>
                Close
              </button>
            </div>
            <div className="stack modalBodyScroll" style={{ gap: 12, marginTop: 12 }}>
              {err ? (
                <div className="error" role="alert">
                  {err}
                </div>
              ) : null}
              <label className="field" style={{ marginBottom: 0 }}>
                <span>Email</span>
                <input value={editEmail} onChange={(e) => setEditEmail(e.target.value)} disabled={busy} autoComplete="off" />
              </label>
              <label className="field" style={{ marginBottom: 0 }}>
                <span>Display name</span>
                <input value={editDisplayName} onChange={(e) => setEditDisplayName(e.target.value)} disabled={busy} />
              </label>
              <label className="field" style={{ marginBottom: 0 }}>
                <span>Initials (unique)</span>
                <input
                  value={editInitials ?? ''}
                  onChange={(e) => setEditInitials(e.target.value)}
                  disabled={busy}
                  title="Letters, digits, dot, underscore, hyphen; 1–12 characters"
                />
              </label>
              <label className="field" style={{ marginBottom: 0 }}>
                <span>Job title (optional)</span>
                <input value={editJobTitle} onChange={(e) => setEditJobTitle(e.target.value)} disabled={busy} placeholder="Optional" />
              </label>
              <label className="field" style={{ marginBottom: 0 }}>
                <span>Role</span>
                <select value={editRole} onChange={(e) => setEditRole(e.target.value as 'admin' | 'user')} disabled={busy}>
                  <option value="user">User</option>
                  <option value="admin">Admin</option>
                </select>
              </label>
              <label className="field" style={{ marginBottom: 0 }}>
                <span>Permission category</span>
                <select value={editCategoryId} onChange={(e) => setEditCategoryId(e.target.value)} disabled={busy}>
                  <option value="">— None —</option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="row" style={{ gap: 8, cursor: 'pointer' }}>
                <input type="checkbox" checked={editActive} onChange={(e) => setEditActive(e.target.checked)} disabled={busy} />
                <span>Account active</span>
              </label>

              <h4 style={{ margin: '16px 0 8px', fontSize: '1rem', fontWeight: 600 }}>Sign-in security</h4>
              <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
                Authenticator status:{' '}
                <strong>{editingUser.is_2fa_enabled ? 'Enabled' : 'Not enabled'}</strong>. Reset removes their app enrolment so
                they must set up 2FA again in User settings (existing passkeys are unchanged).
              </p>
              <button
                type="button"
                className="btn danger"
                disabled={busy}
                onClick={() =>
                  void (async () => {
                    if (!editingUser) return
                    const ok = await askConfirm({
                      title: 'Reset authenticator (2FA)',
                      message:
                        `Clear authenticator enrolment for ${editingUser.email}? They will need to set up 2FA again under User settings before it applies at sign-in.`,
                      danger: true,
                      confirmLabel: 'Reset 2FA',
                    })
                    if (!ok) return
                    setBusy(true)
                    setErr(null)
                    try {
                      await apiFetch<null>(`/admin/users/${editingUser.id}/disable-2fa`, { method: 'POST', token })
                      const list = await load()
                      const nu = list?.find((x) => x.id === editingUser.id)
                      if (nu) setEditingUser(nu)
                    } catch (e: unknown) {
                      setErr((e as ApiError).message ?? 'Could not reset 2FA')
                    } finally {
                      setBusy(false)
                    }
                  })()
                }
              >
                Reset authenticator (2FA)
              </button>
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() =>
                  void (async () => {
                    if (!editingUser) return
                    setBusy(true)
                    setErr(null)
                    try {
                      const res = await apiFetch<AdminSendPasswordResetResponse>(
                        `/admin/users/${editingUser.id}/send-password-reset-email`,
                        { method: 'POST', token },
                      )
                      await showAlert(res.message ?? 'Password reset e-mail sent.', 'E-mail sent')
                    } catch (e: unknown) {
                      setErr((e as ApiError).message ?? 'Could not send password reset e-mail')
                    } finally {
                      setBusy(false)
                    }
                  })()
                }
              >
                Send password reset e-mail
              </button>

              <label className="field" style={{ marginBottom: 0, marginTop: 14 }}>
                <span>New password (optional, min 12 characters)</span>
                <input
                  type="password"
                  value={editPw}
                  onChange={(e) => setEditPw(e.target.value)}
                  disabled={busy}
                  autoComplete="new-password"
                  placeholder="Leave blank to keep current password"
                />
              </label>
              <label className="field" style={{ marginBottom: 0 }}>
                <span>Confirm new password</span>
                <input
                  type="password"
                  value={editPw2}
                  onChange={(e) => setEditPw2(e.target.value)}
                  disabled={busy}
                  autoComplete="new-password"
                />
              </label>
              <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
                When you set a new password here, this user’s authenticator 2FA enrolment is cleared and they sign in with the
                new password until they enable 2FA again.
              </p>
              <div className="row" style={{ gap: 8, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                <button type="button" className="btn" disabled={busy} onClick={() => setEditingUser(null)}>
                  Cancel
                </button>
                <button
                  type="button"
                  className="btn primary"
                  disabled={
                    busy ||
                    !editEmail.trim() ||
                    !editDisplayName.trim() ||
                    !(editInitials ?? '').trim() ||
                    (editPw.length > 0 && (editPw.length < 12 || editPw !== editPw2))
                  }
                  onClick={async () => {
                    if (!editingUser) return
                    if (editPw.length > 0 && editPw !== editPw2) {
                      setErr('Passwords do not match')
                      return
                    }
                    if (editPw.length > 0 && editPw.length < 12) {
                      setErr('Password must be at least 12 characters')
                      return
                    }
                    setBusy(true)
                    setErr(null)
                    try {
                      const updatedUser = await apiFetch<AdminUserPublic>(`/admin/users/${editingUser.id}`, {
                        token,
                        method: 'PATCH',
                        json: {
                          email: editEmail.trim(),
                          display_name: editDisplayName.trim(),
                          initials: (editInitials ?? '').trim(),
                          job_title: (editJobTitle ?? '').trim() || null,
                          role: editRole,
                          is_active: editActive,
                          permission_category_id: editCategoryId || null,
                        },
                      })
                      if (editPw.length >= 12) {
                        await apiFetch(`/admin/users/${editingUser.id}/set-password`, {
                          token,
                          method: 'POST',
                          json: { password: editPw },
                        })
                      }
                      setEditingUser(null)
                      setEditPw('')
                      setEditPw2('')
                      await load()
                      // Fill in fields from PATCH (not a full spread: set-password may run after PATCH
                      // and load() is the source of truth for 2FA state).
                      setUsers((prev) =>
                        prev.map((u) => {
                          if (u.id !== updatedUser.id) return u
                          return {
                            ...u,
                            email: updatedUser.email,
                            display_name: updatedUser.display_name,
                            initials: updatedUser.initials ?? u.initials,
                            job_title: updatedUser.job_title,
                            role: updatedUser.role,
                            is_active: updatedUser.is_active,
                            permission_category_id: updatedUser.permission_category_id,
                          }
                        }),
                      )
                    } catch (e: unknown) {
                      const msg = ((e as ApiError).message ?? '').trim()
                      setErr(msg || 'Update failed')
                    } finally {
                      setBusy(false)
                    }
                  }}
                >
                  Save changes
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

function AdminAudit({ token, embedded }: { token: string; embedded?: boolean }) {
  const [events, setEvents] = useState<AdminAuditEvent[]>([])
  const [action, setAction] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function load() {
    setBusy(true)
    setErr(null)
    try {
      const qs = new URLSearchParams()
      if (action) qs.set('action', action)
      qs.set('limit', '50')
      const data = await apiFetch<AdminAuditEvent[]>(`/admin/audit-events?${qs.toString()}`, { token })
      setEvents(data)
    } catch (e: any) {
      setErr(e?.message ?? 'Failed to load audit events')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  return (
    <div className="stack">
      <div className="paneHead">
        {embedded ? <h3 style={{ margin: 0 }}>Audit</h3> : <h2>Admin · Audit</h2>}
        <button type="button" className="btn" onClick={() => void load()}>
          Refresh
        </button>
      </div>
      <div className="card">
        <div className="row">
          <input placeholder="Filter by action (e.g. auth.login)" value={action} onChange={(e) => setAction(e.target.value)} />
          <button type="button" className="btn primary" disabled={busy} onClick={() => void load()}>
            Apply
          </button>
        </div>
        {err ? <div className="error">{err}</div> : null}
      </div>
      <div className="card">
        <h3>Recent events</h3>
        <div className="list">
          {events.map((e) => (
            <div key={e.id} className="listCard">
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <div className="listTitle">{e.action}</div>
                <div className="muted">{formatTs(e.created_at)}</div>
              </div>
              <div className="muted">
                {e.entity_type ?? '-'} {e.entity_id ?? ''} · actor {e.actor_user_id ?? '-'}
              </div>
            </div>
          ))}
          {events.length === 0 ? <div className="muted">No events found.</div> : null}
        </div>
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
      const data = await apiFetch<ContactOut[]>('/contacts', { token })
      setContacts(data)
    } catch (e: any) {
      setErr(e?.message ?? 'Failed to load contacts')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    void load()
  }, [token])

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

  const rows = useMemo(() => {
    const s = contactsSearch.trim().toLowerCase()
    let list = contacts
    if (s) {
      list = contacts.filter((c) => {
        const parts = [c.name, c.email ?? '', c.phone ?? '', c.type]
        return parts.join(' ').toLowerCase().includes(s)
      })
    }
    const dir = uiPrefs.contacts_sort_dir === 'asc' ? 1 : -1
    const key = uiPrefs.contacts_sort_key
    return [...list].sort((a, b) => {
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
  }, [contacts, contactsSearch, uiPrefs.contacts_sort_key, uiPrefs.contacts_sort_dir])

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
      <div className="mainMenuFilterBar">
        <div className="row mainMenuFilterRow mainMenuFilterRow--toolbar">
          <div className="mainMenuFilterRowLeft">
            <SearchInput
              placeholder="Search contacts (name, email, phone)…"
              value={contactsSearch}
              onChange={(e) => setContactsSearch(e.target.value)}
              onClear={() => setContactsSearch('')}
              className="mainMenuSearchInput"
              aria-label="Search contacts"
            />
          </div>
          <div className="mainMenuFilterRowRight">
            <button type="button" className="btn" onClick={() => void load()} disabled={busy}>
              Refresh
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => {
                setCreateErr(null)
                setCreateOpen(true)
              }}
            >
              New contact…
            </button>
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
              const payload = contactFieldsModelToPayload(fields)
              if (!payload) return
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
