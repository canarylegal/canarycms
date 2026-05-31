import { useEffect, useState } from 'react'
import { apiFetch } from './api'
import type { ApiError } from './api'
import type { EmailIntegrationSettingsOut, SmtpNotificationSettingsOut } from './types'

export function AdminEmail({ token, onSaved }: { token: string; onSaved?: () => void }) {
  const [settings, setSettings] = useState<EmailIntegrationSettingsOut | null>(null)
  const [integrationMode, setIntegrationMode] = useState<'mailto' | 'microsoft_graph'>('microsoft_graph')
  const [tenantId, setTenantId] = useState('')
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [owaBase, setOwaBase] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [ok, setOk] = useState(false)

  const [smtp, setSmtp] = useState<SmtpNotificationSettingsOut | null>(null)
  const [smtpEnabled, setSmtpEnabled] = useState(false)
  const [smtpHost, setSmtpHost] = useState('')
  const [smtpPort, setSmtpPort] = useState('587')
  const [smtpTls, setSmtpTls] = useState(true)
  const [smtpUser, setSmtpUser] = useState('')
  const [smtpPass, setSmtpPass] = useState('')
  const [smtpFrom, setSmtpFrom] = useState('')
  const [smtpFromName, setSmtpFromName] = useState('')
  const [smtpTestTo, setSmtpTestTo] = useState('')
  const [smtpErr, setSmtpErr] = useState<string | null>(null)
  const [smtpOk, setSmtpOk] = useState(false)

  const [alertsEnabled, setAlertsEnabled] = useState(false)
  const [graphSendMailbox, setGraphSendMailbox] = useState('')
  const [graphSendFromName, setGraphSendFromName] = useState('')
  const [alertTestTo, setAlertTestTo] = useState('')
  const [alertErr, setAlertErr] = useState<string | null>(null)
  const [alertOk, setAlertOk] = useState(false)

  async function load() {
    setErr(null)
    try {
      const [s, sm] = await Promise.all([
        apiFetch<EmailIntegrationSettingsOut>('/admin/email/settings', { token }),
        apiFetch<SmtpNotificationSettingsOut>('/admin/email/smtp-settings', { token }),
      ])
      setSettings(s)
      setIntegrationMode(s.integration_mode)
      setTenantId(s.graph_tenant_id ?? '')
      setClientId(s.graph_client_id ?? '')
      setClientSecret('')
      setOwaBase(s.outlook_web_mail_base ?? '')
      setAlertsEnabled(s.alerts_enabled)
      setGraphSendMailbox(s.graph_send_mailbox ?? '')
      setGraphSendFromName(s.graph_send_from_name ?? '')
      setAlertErr(null)
      setAlertOk(false)
      setSmtp(sm)
      setSmtpEnabled(sm.enabled)
      setSmtpHost(sm.host ?? '')
      setSmtpPort(String(sm.port ?? 587))
      setSmtpTls(sm.use_tls !== false)
      setSmtpUser(sm.username ?? '')
      setSmtpPass('')
      setSmtpFrom(sm.from_email ?? '')
      setSmtpFromName(sm.from_name ?? '')
      setSmtpErr(null)
      setSmtpOk(false)
    } catch (e) {
      setSettings(null)
      setSmtp(null)
      setErr((e as ApiError).message ?? 'Failed to load settings')
    }
  }

  useEffect(() => {
    void load()
  }, [token])

  async function persistSettings(): Promise<EmailIntegrationSettingsOut> {
    const body: Record<string, unknown> = {
      integration_mode: integrationMode,
      graph_tenant_id: tenantId.trim() || null,
      graph_client_id: clientId.trim() || null,
      outlook_web_mail_base: owaBase.trim() || null,
      alerts_enabled: alertsEnabled,
      alert_transport: integrationMode === 'microsoft_graph' ? 'auto' : 'smtp',
      graph_send_mailbox: integrationMode === 'microsoft_graph' ? graphSendMailbox.trim() || null : null,
      graph_send_from_name: integrationMode === 'microsoft_graph' ? graphSendFromName.trim() || null : null,
    }
    if (clientSecret.trim()) {
      body.graph_client_secret = clientSecret.trim()
    }
    return apiFetch<EmailIntegrationSettingsOut>('/admin/email/settings', {
      token,
      method: 'PUT',
      json: body,
    })
  }

  async function save() {
    setBusy(true)
    setErr(null)
    setOk(false)
    try {
      const s = await persistSettings()
      setSettings(s)
      setClientSecret('')
      setOk(true)
      await load()
      onSaved?.()
    } catch (e) {
      setErr((e as ApiError).message ?? 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  async function clearEntraSecret() {
    if (!window.confirm('Remove the stored client secret? Graph calls will use the server environment variable if set.')) {
      return
    }
    setBusy(true)
    setErr(null)
    setOk(false)
    try {
      await apiFetch<EmailIntegrationSettingsOut>('/admin/email/settings', {
        token,
        method: 'PUT',
        json: { graph_client_secret: '' },
      })
      setClientSecret('')
      setOk(true)
      await load()
      onSaved?.()
    } catch (e) {
      setErr((e as ApiError).message ?? 'Failed to clear secret')
    } finally {
      setBusy(false)
    }
  }

  async function saveSmtp() {
    setBusy(true)
    setSmtpErr(null)
    setSmtpOk(false)
    try {
      const body: Record<string, unknown> = {
        enabled: smtpEnabled,
        host: smtpHost.trim() || null,
        port: parseInt(smtpPort, 10) || 587,
        use_tls: smtpTls,
        username: smtpUser.trim() || null,
        from_email: smtpFrom.trim() || null,
        from_name: smtpFromName.trim() || null,
      }
      if (smtpPass.trim()) {
        body.password = smtpPass.trim()
      }
      const sm = await apiFetch<SmtpNotificationSettingsOut>('/admin/email/smtp-settings', {
        token,
        method: 'PUT',
        json: body,
      })
      setSmtp(sm)
      setSmtpPass('')
      setSmtpOk(true)
      onSaved?.()
    } catch (e) {
      setSmtpErr((e as ApiError).message ?? 'SMTP save failed')
    } finally {
      setBusy(false)
    }
  }

  async function sendAlertTest() {
    const to = alertTestTo.trim()
    if (!to) {
      setAlertErr('Enter a destination address for the test.')
      return
    }
    if (integrationMode === 'microsoft_graph' && !graphSendMailbox.trim()) {
      setAlertErr('Enter a Graph send mailbox before testing.')
      return
    }
    setBusy(true)
    setAlertErr(null)
    setAlertOk(false)
    setErr(null)
    try {
      const s = await persistSettings()
      setSettings(s)
      setClientSecret('')
      await apiFetch('/admin/email/alerts-test', {
        token,
        method: 'POST',
        json: { to_email: to },
      })
      setAlertOk(true)
      onSaved?.()
    } catch (e) {
      setAlertErr((e as ApiError).message ?? 'Alert test send failed')
    } finally {
      setBusy(false)
    }
  }

  async function sendSmtpTest() {
    const to = smtpTestTo.trim()
    if (!to) {
      setSmtpErr('Enter a destination address for the test.')
      return
    }
    setBusy(true)
    setSmtpErr(null)
    setSmtpOk(false)
    try {
      await apiFetch('/admin/email/smtp-test', {
        token,
        method: 'POST',
        json: { to_email: to },
      })
      setSmtpOk(true)
    } catch (e) {
      setSmtpErr((e as ApiError).message ?? 'Test send failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack" style={{ maxWidth: 640 }}>
      {err ? <div className="error">{err}</div> : null}
      {ok ? <div className="muted">Saved.</div> : null}

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Sending e-mail from Canary</h3>
        <p className="muted" style={{ marginTop: 8, lineHeight: 1.5 }}>
          <strong>New → E-mail</strong> always opens compose with merged To, subject, and body (<code>mailto:</code> or
          Outlook web — see Profile → E-mail). Case file attachments use the Canary add-in{' '}
          <strong>Compose from matter</strong>, not this page. Optional Microsoft Graph below adds OWA links for filed
          mail and Outlook category helpers (Entra app + admin consent).
        </p>

        <div className="stack" style={{ marginTop: 16, gap: 14 }}>
          <label
            style={{
              display: 'flex',
              gap: 10,
              alignItems: 'flex-start',
              cursor: 'pointer',
              lineHeight: 1.45,
            }}
          >
            <input
              type="radio"
              name="emailMode"
              checked={integrationMode === 'mailto'}
              onChange={() => setIntegrationMode('mailto')}
              style={{ marginTop: '0.2em', flexShrink: 0 }}
            />
            <span style={{ flex: 1, minWidth: 0 }}>
              <strong>No Microsoft Graph</strong> — compose and attachments rely on the mail program and Canary add-ins;
              automated alerts use SMTP.
            </span>
          </label>
          <label
            style={{
              display: 'flex',
              gap: 10,
              alignItems: 'flex-start',
              cursor: 'pointer',
              lineHeight: 1.45,
            }}
          >
            <input
              type="radio"
              name="emailMode"
              checked={integrationMode === 'microsoft_graph'}
              onChange={() => setIntegrationMode('microsoft_graph')}
              style={{ marginTop: '0.2em', flexShrink: 0 }}
            />
            <span style={{ flex: 1, minWidth: 0 }}>
              <strong>Microsoft 365 (Entra / Graph)</strong> — OWA deep links for filed e-mail, Outlook category helpers,
              and automated alert e-mail via Graph.
            </span>
          </label>
        </div>
      </div>

      {integrationMode === 'microsoft_graph' ? (
        <>
          <div className="card">
            <h3 style={{ marginTop: 0 }}>Entra app (optional — overrides .env)</h3>
            <p className="muted" style={{ lineHeight: 1.5 }}>
              Values below are stored encrypted on the server (except identifiers) and override{' '}
              <code>CANARY_MS_GRAPH_*</code> when set. Leave fields empty to keep using environment variables. The client
              secret is never shown again after save.
            </p>
            {settings?.graph_client_secret_configured ? (
              <div className="muted" style={{ marginBottom: 12 }}>
                A client secret is stored. Enter a new secret to replace it, or clear it.
              </div>
            ) : null}

            <label className="field">
              <span>Directory (tenant) ID</span>
              <input
                type="text"
                autoComplete="off"
                value={tenantId}
                onChange={(e) => setTenantId(e.target.value)}
                placeholder="e.g. from Entra → Overview"
              />
            </label>
            <label className="field">
              <span>Application (client) ID</span>
              <input
                type="text"
                autoComplete="off"
                value={clientId}
                onChange={(e) => setClientId(e.target.value)}
              />
            </label>
            <label className="field">
              <span>Client secret (value, not secret ID)</span>
              <input
                type="password"
                autoComplete="new-password"
                value={clientSecret}
                onChange={(e) => setClientSecret(e.target.value)}
                placeholder={settings?.graph_client_secret_configured ? '•••••••• (unchanged if empty)' : ''}
              />
            </label>
            <label className="field">
              <span>Outlook on the web base (filed mail links)</span>
              <input
                type="text"
                value={owaBase}
                onChange={(e) => setOwaBase(e.target.value)}
                placeholder="https://outlook.office.com/mail"
              />
            </label>
            <div className="row" style={{ gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
              {settings?.graph_client_secret_configured ? (
                <button type="button" className="btn" disabled={busy} onClick={() => void clearEntraSecret()}>
                  Clear stored secret
                </button>
              ) : null}
            </div>
          </div>

          <div className="card" style={{ marginTop: 16 }}>
            <h3 style={{ marginTop: 0 }}>Automated alert e-mail</h3>
            <p className="muted" style={{ marginTop: 8, lineHeight: 1.5 }}>
              Outbound mail for calendar reminders and staff alerts (e.g. portal uploads). Client-facing e-mails are sent
              only when a user chooses to notify a contact. Alerts are sent via Microsoft Graph from the mailbox below.
            </p>
            {alertErr ? <div className="error" style={{ marginTop: 8 }}>{alertErr}</div> : null}
            {alertOk ? <div className="muted" style={{ marginTop: 8 }}>Alert test sent.</div> : null}
            <div className="stack" style={{ marginTop: 14, gap: 12 }}>
              <label className="row" style={{ gap: 8, alignItems: 'center', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={alertsEnabled}
                  disabled={busy}
                  onChange={(e) => setAlertsEnabled(e.target.checked)}
                />
                <span>Enable automated alert e-mail</span>
              </label>
              {settings ? (
                <p className="muted" style={{ margin: 0, lineHeight: 1.5 }}>
                  {settings.graph_alert_ready
                    ? 'Microsoft Graph alert sending is configured.'
                    : 'Configure the Entra app above and a send mailbox to enable alerts.'}
                  {!settings.graph_tenant_id && !settings.graph_client_secret_configured && settings.graph_alert_ready ? (
                    <>
                      {' '}
                      Entra credentials are loaded from <code>CANARY_MS_GRAPH_*</code> in the server environment (GUI fields optional).
                    </>
                  ) : null}
                </p>
              ) : null}
              <label className="field">
                <span>Graph send mailbox</span>
                <input
                  type="email"
                  value={graphSendMailbox}
                  disabled={busy}
                  onChange={(e) => setGraphSendMailbox(e.target.value)}
                  placeholder="alerts@firm.example"
                />
              </label>
              <p className="muted" style={{ margin: 0, lineHeight: 1.5 }}>
                The Entra app needs <strong>Mail.Send</strong> (application) with admin consent, and permission to send
                as this mailbox (e.g. Application Access Policy or mailbox delegation).
              </p>
              <label className="field">
                <span>Graph from display name (optional)</span>
                <input
                  value={graphSendFromName}
                  disabled={busy}
                  onChange={(e) => setGraphSendFromName(e.target.value)}
                  placeholder="Your firm name"
                />
              </label>
              <div className="field">
                <span>Test alert send</span>
                <p className="muted" style={{ margin: '4px 0 0', lineHeight: 1.45 }}>
                  Saves alert settings above, then sends a test message.
                </p>
                <div className="row" style={{ gap: 8, marginTop: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                  <input
                    style={{ flex: '1 1 200px', minWidth: 0 }}
                    type="email"
                    value={alertTestTo}
                    disabled={busy}
                    onChange={(e) => setAlertTestTo(e.target.value)}
                    placeholder="your@email"
                  />
                  <button type="button" className="btn" disabled={busy} onClick={() => void sendAlertTest()}>
                    Send alert test
                  </button>
                </div>
              </div>
            </div>
          </div>
        </>
      ) : (
        <>
          <div className="card" style={{ marginTop: 16 }}>
            <h3 style={{ marginTop: 0 }}>Automated alert e-mail (SMTP)</h3>
            <p className="muted" style={{ marginTop: 8, lineHeight: 1.5 }}>
              Outbound mail for calendar reminders, staff alerts, and optional client notifications when a user chooses
              to send them. Configure SMTP below.
            </p>
            {alertErr ? <div className="error" style={{ marginTop: 8 }}>{alertErr}</div> : null}
            {alertOk ? <div className="muted" style={{ marginTop: 8 }}>Alert test sent.</div> : null}
            <div className="stack" style={{ marginTop: 14, gap: 12 }}>
              <label className="row" style={{ gap: 8, alignItems: 'center', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={alertsEnabled}
                  disabled={busy}
                  onChange={(e) => setAlertsEnabled(e.target.checked)}
                />
                <span>Enable automated alert e-mail</span>
              </label>
              {settings ? (
                <p className="muted" style={{ margin: 0, lineHeight: 1.5 }}>
                  {settings.smtp_alert_ready
                    ? 'SMTP alert sending is configured.'
                    : 'Enable and save SMTP settings below to send alerts.'}
                </p>
              ) : null}
              <div className="field">
                <span>Test alert send</span>
                <p className="muted" style={{ margin: '4px 0 0', lineHeight: 1.45 }}>
                  Saves alert settings above, then sends a test message.
                </p>
                <div className="row" style={{ gap: 8, marginTop: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                  <input
                    style={{ flex: '1 1 200px', minWidth: 0 }}
                    type="email"
                    value={alertTestTo}
                    disabled={busy}
                    onChange={(e) => setAlertTestTo(e.target.value)}
                    placeholder="your@email"
                  />
                  <button type="button" className="btn" disabled={busy} onClick={() => void sendAlertTest()}>
                    Send alert test
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div className="card" style={{ marginTop: 16 }}>
            <h3 style={{ marginTop: 0 }}>SMTP</h3>
            <p className="muted" style={{ marginTop: 8, lineHeight: 1.5 }}>
              Outbound SMTP for automated alerts and test sends.
            </p>
            {smtpErr ? <div className="error" style={{ marginTop: 8 }}>{smtpErr}</div> : null}
            {smtpOk ? <div className="muted" style={{ marginTop: 8 }}>SMTP action completed.</div> : null}
            {smtp ? (
              <div className="stack" style={{ marginTop: 14, gap: 12 }}>
                <label className="row" style={{ gap: 8, alignItems: 'center', cursor: 'pointer' }}>
                  <input type="checkbox" checked={smtpEnabled} disabled={busy} onChange={(e) => setSmtpEnabled(e.target.checked)} />
                  <span>Enable outbound SMTP</span>
                </label>
                <label className="field">
                  <span>Host</span>
                  <input value={smtpHost} disabled={busy} onChange={(e) => setSmtpHost(e.target.value)} placeholder="smtp.example.com" />
                </label>
                <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
                  <label className="field" style={{ flex: '1 1 120px' }}>
                    <span>Port</span>
                    <input value={smtpPort} disabled={busy} onChange={(e) => setSmtpPort(e.target.value)} />
                  </label>
                  <label className="row" style={{ gap: 8, alignItems: 'center', marginTop: 22, cursor: 'pointer' }}>
                    <input type="checkbox" checked={smtpTls} disabled={busy} onChange={(e) => setSmtpTls(e.target.checked)} />
                    <span>TLS (STARTTLS, or SSL on port 465)</span>
                  </label>
                </div>
                <label className="field">
                  <span>Username (optional)</span>
                  <input value={smtpUser} disabled={busy} autoComplete="off" onChange={(e) => setSmtpUser(e.target.value)} />
                </label>
                <label className="field">
                  <span>Password (optional)</span>
                  <input
                    type="password"
                    value={smtpPass}
                    disabled={busy}
                    autoComplete="new-password"
                    onChange={(e) => setSmtpPass(e.target.value)}
                    placeholder={smtp.password_configured ? '•••••••• (leave blank to keep)' : ''}
                  />
                </label>
                <label className="field">
                  <span>From address</span>
                  <input value={smtpFrom} disabled={busy} onChange={(e) => setSmtpFrom(e.target.value)} placeholder="alerts@firm.example" />
                </label>
                <label className="field">
                  <span>From display name (optional)</span>
                  <input value={smtpFromName} disabled={busy} onChange={(e) => setSmtpFromName(e.target.value)} placeholder="Canary" />
                </label>
                <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                  <button type="button" className="btn primary" disabled={busy} onClick={() => void saveSmtp()}>
                    Save SMTP
                  </button>
                </div>
                <div className="field" style={{ marginTop: 8 }}>
                  <span>Test send</span>
                  <div className="row" style={{ gap: 8, marginTop: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                    <input
                      style={{ flex: '1 1 200px', minWidth: 0 }}
                      type="email"
                      value={smtpTestTo}
                      disabled={busy}
                      onChange={(e) => setSmtpTestTo(e.target.value)}
                      placeholder="your@email"
                    />
                    <button type="button" className="btn" disabled={busy} onClick={() => void sendSmtpTest()}>
                      Send test
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <p className="muted" style={{ marginTop: 8 }}>
                Load settings to configure SMTP.
              </p>
            )}
          </div>
        </>
      )}

      <div className="row" style={{ gap: 8 }}>
        <button type="button" className="btn primary" disabled={busy} onClick={() => void save()}>
          {busy ? 'Saving…' : 'Save'}
        </button>
        <button type="button" className="btn" disabled={busy} onClick={() => void load()}>
          Reload
        </button>
      </div>
    </div>
  )
}
