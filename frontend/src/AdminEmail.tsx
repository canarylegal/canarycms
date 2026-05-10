import { useEffect, useState } from 'react'
import { apiFetch } from './api'
import type { ApiError } from './api'
import type { EmailIntegrationSettingsOut } from './types'

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

  async function load() {
    setErr(null)
    try {
      const s = await apiFetch<EmailIntegrationSettingsOut>('/admin/email/settings', { token })
      setSettings(s)
      setIntegrationMode(s.integration_mode)
      setTenantId(s.graph_tenant_id ?? '')
      setClientId(s.graph_client_id ?? '')
      setClientSecret('')
      setOwaBase(s.outlook_web_mail_base ?? '')
    } catch (e) {
      setSettings(null)
      setErr((e as ApiError).message ?? 'Failed to load settings')
    }
  }

  useEffect(() => {
    void load()
  }, [token])

  async function save() {
    setBusy(true)
    setErr(null)
    setOk(false)
    try {
      const body: Record<string, unknown> = {
        integration_mode: integrationMode,
        graph_tenant_id: tenantId.trim() || null,
        graph_client_id: clientId.trim() || null,
        outlook_web_mail_base: owaBase.trim() || null,
      }
      if (clientSecret.trim()) {
        body.graph_client_secret = clientSecret.trim()
      }
      const s = await apiFetch<EmailIntegrationSettingsOut>('/admin/email/settings', {
        token,
        method: 'PUT',
        json: body,
      })
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

  return (
    <div className="stack" style={{ maxWidth: 640 }}>
      {err ? <div className="error">{err}</div> : null}
      {ok ? <div className="muted">Saved.</div> : null}

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Sending e-mail from Canary</h3>
        <p className="muted" style={{ marginTop: 8, lineHeight: 1.5 }}>
          Choose how <strong>New → E-mail</strong> opens: the desktop <code>mailto:</code> handler, or an Outlook draft via{' '}
          <strong>Microsoft Graph</strong> (requires Entra app registration, application permissions, and admin consent).
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
              <strong>Desktop mailto</strong> — open the default mail program with subject and body (no Microsoft API).
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
              <strong>Microsoft 365 (Entra / Graph)</strong> — create a draft in the user&apos;s Outlook mailbox.
            </span>
          </label>
        </div>
      </div>

      {integrationMode === 'microsoft_graph' ? (
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
            <span>Outlook on the web base (compose links)</span>
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
      ) : null}

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
