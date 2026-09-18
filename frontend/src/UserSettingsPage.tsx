import { useEffect, useState } from 'react'
import {
  startRegistration,
  type PublicKeyCredentialCreationOptionsJSON,
} from '@simplewebauthn/browser'
import { apiFetch, type ApiError } from './api'
import { useDialogs } from './DialogProvider'
import {
  accentForChromeStyle,
  CHROME_STYLE_OPTIONS,
  chromeStyleFromAccent,
  DEFAULT_ACCENT,
  FONT_OPTIONS,
  SLATE_CHROME_ACCENT,
} from './theme'
import { persistUserAppearance, useAppearanceFormState } from './useServerAppearance'
import { resetMenuColumnWidths } from './userUiPreferences'
import {
  DEFAULT_OUTLOOK_WEB_MAIL_URL,
  isOrgMicrosoftGraphConfigured,
  OUTLOOK_WEB_WITHOUT_GRAPH_CONFIRM_MESSAGE,
} from './emailLauncher'
import { copyTextToClipboard } from './copyToClipboard'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import { TextPromptModal } from './TextPromptModal'
import type {
  ChangePasswordResponse,
  TokenResponse,
  UserCalDAVProvisionOut,
  UserCalDAVStatusOut,
  UserPublic,
  Verify2FASessionResponse,
  WebAuthnCredentialOut,
} from './types'

function formatTs(s: string) {
  try {
    return new Date(s).toLocaleString()
  } catch {
    return s
  }
}

export function UserSettingsPage({
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
    setAppPageBg,
    appMode,
    setAppMode,
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
  const [caldavRevealOpen, setCaldavRevealOpen] = useState(false)

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
          <h3 className="mutedFlush">Signature image</h3>
          <p className="muted mutedFlush">
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
          <div className="row wrap gap8">
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
          <h3 className="mutedFlush">Appearance</h3>
          <p className="muted mutedFlush">
            Font, navigation colour, and light or dark mode are saved to your account and follow you on any device when
            you sign in.
          </p>
          <div className="stack" style={{ maxWidth: 520, gap: 12 }}>
            <SingleSelectDropdown
              label="Font"
              options={FONT_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
              value={appFont}
              onChange={(v) => {
                setAppFont(v)
                setThemeSavedHint(false)
              }}
            />
            <fieldset className="field" style={{ border: 'none', margin: 0, padding: 0 }}>
              <legend style={{ marginBottom: 6 }}>Navigation colour</legend>
              <p className="mutedSm" style={{ marginBottom: 8 }}>
                {appMode === 'dark'
                  ? 'Dark mode always uses slate for sidebar and ribbons. Primary buttons stay Canary yellow.'
                  : 'Sidebar and ribbons. Primary buttons stay Canary yellow.'}
              </p>
              <div className="stack" style={{ gap: 10 }}>
                {(appMode === 'dark' ? CHROME_STYLE_OPTIONS.filter((o) => o.id === 'slate') : CHROME_STYLE_OPTIONS).map(
                  (opt) => {
                  const selected =
                    appMode === 'dark' ? opt.id === 'slate' : chromeStyleFromAccent(appAccent) === opt.id
                  return (
                    <label
                      key={opt.id}
                      className="row"
                      style={{
                        gap: 8,
                        cursor: 'pointer',
                        padding: '8px 10px',
                        borderRadius: 10,
                        border: selected ? '2px solid var(--primary)' : '2px solid var(--border)',
                        background: selected ? 'rgba(var(--primary-rgb), 0.1)' : 'transparent',
                        width: '100%',
                        boxSizing: 'border-box',
                        alignItems: 'flex-start',
                      }}
                    >
                      <input
                        type="radio"
                        name="canary-chrome"
                        checked={selected}
                        disabled={appMode === 'dark'}
                        onChange={() => {
                          setAppAccent(accentForChromeStyle(opt.id))
                          setThemeSavedHint(false)
                        }}
                        style={{ marginTop: 3 }}
                      />
                      <span
                        aria-hidden
                        style={{
                          width: 18,
                          height: 18,
                          borderRadius: 4,
                          background: opt.swatch,
                          border: '1px solid rgba(15, 23, 42, 0.2)',
                          flexShrink: 0,
                          marginTop: 2,
                        }}
                      />
                      <span>
                        <span style={{ display: 'block', fontWeight: 650 }}>{opt.label}</span>
                        <span className="muted textXs">
                          {opt.hint}
                        </span>
                      </span>
                    </label>
                  )
                },
                )}
              </div>
            </fieldset>
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
                      setAppAccent(SLATE_CHROME_ACCENT)
                      setThemeSavedHint(false)
                    }}
                  />
                  Dark
                </label>
              </div>
            </fieldset>
            {themeSaveErr ? <div className="error">{themeSaveErr}</div> : null}
            {themeSavedHint ? <div className="muted">Appearance saved.</div> : null}
            <div className="row gap8">
              <button
                type="button"
                className="btn primary"
                disabled={busy}
                onClick={() => {
                  void (async () => {
                    setThemeSaveErr(null)
                    setBusy(true)
                    try {
                      await persistUserAppearance(token, {
                        font: appFont,
                        accent: appMode === 'dark' ? SLATE_CHROME_ACCENT : appAccent,
                        mode: appMode,
                        pageBg: '',
                      })
                      if (appMode === 'dark') setAppAccent(SLATE_CHROME_ACCENT)
                      setAppPageBg('')
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
              <div className="muted" style={{ marginBottom: 8 }}>
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
                        await resetMenuColumnWidths(token, account?.id)
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
          <h3 className="mutedFlush">
            {passwordChangeRequiredOnly ? 'New password' : securitySetupOnly ? 'Authenticator & passkeys' : 'Password & two-factor authentication'}
          </h3>
          <p className="muted mutedFlush">
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
                <div className="muted">
                  At least 12 characters.
                </div>
                {pwdErr ? <div className="error">{pwdErr}</div> : null}
                {pwdOk ? <div className="muted">Password updated.</div> : null}
                <div className="row gap8">
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
          <p className="muted mutedFlush">
            Status:{' '}
            <strong>{account?.is_2fa_enabled ? 'Enabled' : 'Not enabled'}</strong>
          </p>

          {faErr ? <div className="error">{faErr}</div> : null}
          {faOk ? <div className="muted">2FA updated.</div> : null}

          {account?.is_2fa_enabled ? (
            <div className="stack" style={{ maxWidth: 480, gap: 10, marginTop: 8 }}>
              <p className="mutedSm">
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
              <p className="mutedSm">
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
              <p className="mutedSm">
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
                    <input readOnly value={faSetup.secret} className="monoSm" />
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
              <p className="mutedSm textXs">
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
              <div className="row wrap gap8">
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
                    <span className="muted textXs">
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
          <p className="muted mutedFlush">
            Passkeys let you sign in with your device (Face ID, Touch ID, Windows Hello, or a security key). You can register
            several and remove ones you no longer use.
          </p>
          {pkErr ? <div className="error">{pkErr}</div> : null}
          <div className="stack" style={{ maxWidth: 520, gap: 10, marginTop: 8 }}>
            <label className="field">
              <span className="muted textXs">
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
          <h3 className="mutedFlush">E-mail</h3>
          <p className="muted mutedFlush">
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
              <p className="mutedSm">
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
            <div className="row gap8">
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
          <h3 className="mutedFlush">Calendar (CalDAV)</h3>
          <p className="muted mutedFlush">
            Subscribe in Apple Calendar, Thunderbird, etc. Use the CalDAV app password — not your Canary login. You can show
            the app password again anytime by confirming your Canary password. Extra calendars and sharing are managed in
            your client and on the server (Radicale).
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
                <input readOnly value={caldav.caldav_url} className="monoSm" />
              </label>
              <label className="field">
                <span>CalDAV username</span>
                <input readOnly value={caldav.caldav_username} className="monoSm" />
              </label>
              <div className="row wrap gap8">
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
              <div style={{ fontWeight: 600, marginBottom: 8 }}>CalDAV app password</div>
              <p className="muted mutedFlush">
                {caldavProvision.note}
              </p>
              <label className="field">
                <span>Password</span>
                <input readOnly value={caldavProvision.caldav_password} className="monoSm" />
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
                  Hide
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
                    setCaldavRevealOpen(true)
                  }}
                >
                  Show app password
                </button>
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
          {caldavRevealOpen ? (
            <TextPromptModal
              title="Show CalDAV password"
              hint="Enter your Canary login password to display the CalDAV app password."
              fieldLabel="Canary password"
              inputType="password"
              autoComplete="current-password"
              initial=""
              confirmLabel="Show password"
              busy={caldavBusy}
              onCancel={() => {
                if (caldavBusy) return
                setCaldavRevealOpen(false)
              }}
              onConfirm={(pwd) => {
                const currentPassword = pwd.trim()
                if (!currentPassword) {
                  setCaldavActionErr('Enter your Canary password.')
                  return
                }
                setCaldavActionErr(null)
                setCaldavCopyHint(null)
                setCaldavBusy(true)
                apiFetch<UserCalDAVProvisionOut>('/users/me/calendar/reveal-password', {
                  method: 'POST',
                  token,
                  json: { current_password: currentPassword },
                })
                  .then((p) => {
                    setCaldavProvision(p)
                    setCaldavRevealOpen(false)
                  })
                  .catch((e: unknown) =>
                    setCaldavActionErr((e as ApiError).message ?? 'Could not show CalDAV password'),
                  )
                  .finally(() => setCaldavBusy(false))
              }}
            />
          ) : null}
        </section>
        ) : null}
      </div>
    </div>
  )
}



