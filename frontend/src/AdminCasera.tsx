import { useEffect, useState } from 'react'
import { apiFetch } from './api'
import type { ApiError } from './api'
import type { CaseraIntegrationSettingsOut } from './types/casera'

export function AdminCasera({ token }: { token: string }) {
  const [settings, setSettings] = useState<CaseraIntegrationSettingsOut | null>(null)
  const [enabled, setEnabled] = useState(false)
  const [sandbox, setSandbox] = useState(true)
  const [clientId, setClientId] = useState('')
  const [accessToken, setAccessToken] = useState('')
  const [webhookSecret, setWebhookSecret] = useState('')
  const [webhookPathToken, setWebhookPathToken] = useState('')
  const [apiBaseUri, setApiBaseUri] = useState('')
  const [postAnticipated, setPostAnticipated] = useState(false)
  const [addToCompletion, setAddToCompletion] = useState(false)
  const [emailOnResult, setEmailOnResult] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [ok, setOk] = useState(false)

  async function load() {
    setErr(null)
    try {
      const s = await apiFetch<CaseraIntegrationSettingsOut>('/admin/casera/settings', { token })
      setSettings(s)
      setEnabled(s.enabled)
      setSandbox(s.sandbox)
      setClientId(s.client_id ?? '')
      setWebhookPathToken(s.webhook_path_token ?? '')
      setApiBaseUri(s.api_base_uri ?? '')
      setPostAnticipated(Boolean(s.post_anticipated_disbursement))
      setAddToCompletion(Boolean(s.add_to_completion_statement))
      setAccessToken('')
      setWebhookSecret('')
    } catch (e) {
      setSettings(null)
      setErr((e as ApiError).message ?? 'Failed to load Casera settings')
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
        enabled,
        sandbox,
        client_id: clientId.trim() || null,
        webhook_path_token: webhookPathToken.trim() || null,
        api_base_uri: apiBaseUri.trim() || null,
        post_anticipated_disbursement: postAnticipated,
        add_to_completion_statement: addToCompletion,
        email_on_result_ready: emailOnResult,
      }
      if (accessToken.trim()) body.access_token = accessToken.trim()
      if (webhookSecret.trim()) body.webhook_secret = webhookSecret.trim()
      const s = await apiFetch<CaseraIntegrationSettingsOut>('/admin/casera/settings', {
        token,
        method: 'PUT',
        json: body,
      })
      setSettings(s)
      setOk(true)
      setAccessToken('')
      setWebhookSecret('')
    } catch (e) {
      setErr((e as ApiError).message ?? 'Could not save Casera settings')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack" style={{ gap: 16, maxWidth: 720 }}>
      <div>
        <h3 style={{ margin: 0 }}>Casera settings</h3>
        <p className="muted" style={{ margin: '8px 0 0' }}>
          Sandbox uses a Bearer access token from the Casera developer portal. Secrets are stored encrypted.
        </p>
      </div>

      {err ? <div className="err">{err}</div> : null}
      {ok ? <div className="ok">Casera settings saved.</div> : null}

      <label className="row" style={{ gap: 8, alignItems: 'center' }}>
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} disabled={busy} />
        <span>Enable Casera searches</span>
      </label>

      <label className="row" style={{ gap: 8, alignItems: 'center' }}>
        <input type="checkbox" checked={sandbox} onChange={(e) => setSandbox(e.target.checked)} disabled={busy} />
        <span>Sandbox mode</span>
      </label>

      <div className="stack" style={{ gap: 8 }}>
        <label className="stack" style={{ gap: 4 }}>
          <span>Client ID</span>
          <input value={clientId} onChange={(e) => setClientId(e.target.value)} disabled={busy} autoComplete="off" />
        </label>
        <label className="stack" style={{ gap: 4 }}>
          <span>
            Access token {settings?.access_token_configured ? '(configured — paste to replace)' : ''}
          </span>
          <textarea
            value={accessToken}
            onChange={(e) => setAccessToken(e.target.value)}
            disabled={busy}
            rows={3}
            autoComplete="off"
          />
        </label>
        <label className="stack" style={{ gap: 4 }}>
          <span>
            Webhook secret {settings?.webhook_secret_configured ? '(configured — paste to replace)' : ''}
          </span>
          <input
            value={webhookSecret}
            onChange={(e) => setWebhookSecret(e.target.value)}
            disabled={busy}
            autoComplete="off"
            type="password"
          />
        </label>
        <label className="stack" style={{ gap: 4 }}>
          <span>Webhook path token (optional URL segment)</span>
          <input
            value={webhookPathToken}
            onChange={(e) => setWebhookPathToken(e.target.value)}
            disabled={busy}
            autoComplete="off"
            placeholder="e.g. q7q3x40v9y9"
          />
        </label>
        <label className="stack" style={{ gap: 4 }}>
          <span>Casera API base URI (optional — leave blank for default)</span>
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>
            Must be the Casera host, usually <code>https://api.casera.co.uk</code>. Do not paste the Canary webhook
            URL here.
          </p>
          <input
            value={apiBaseUri}
            onChange={(e) => setApiBaseUri(e.target.value)}
            disabled={busy}
            autoComplete="off"
            placeholder="https://api.casera.co.uk"
          />
        </label>
      </div>

      <p className="muted" style={{ margin: 0, fontSize: 13, lineHeight: 1.45 }}>
        Register this <strong>webhook</strong> URL in the Casera developer portal (not the API base field above):{' '}
        <code>{settings?.webhook_url ?? '/api/casera/webhook'}</code>
      </p>

      <div className="stack" style={{ gap: 10, paddingTop: 4 }}>
        <h4 style={{ margin: 0 }}>Finance</h4>
        <label className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
          <input
            type="checkbox"
            checked={postAnticipated}
            onChange={(e) => setPostAnticipated(e.target.checked)}
            disabled={busy}
            style={{ marginTop: 3 }}
          />
          <span>
            Post search costs as anticipated disbursements on the ledger when an order is placed
            <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>
              One office debit per product (requires permission to post anticipated). Stays unapproved until cashier
              approval.
            </div>
          </span>
        </label>
        <label className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
          <input
            type="checkbox"
            checked={addToCompletion}
            onChange={(e) => setAddToCompletion(e.target.checked)}
            disabled={busy}
            style={{ marginTop: 3 }}
          />
          <span>
            Add search costs to the completion statement
            <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>
              Creates a Finance category named <strong>Searches</strong> (if missing) and debit rows for each product
              cost.
            </div>
          </span>
        </label>
      </div>

      <div className="stack" style={{ gap: 10, paddingTop: 4 }}>
        <h4 style={{ margin: 0 }}>Notifications</h4>
        <label className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
          <input
            type="checkbox"
            checked={emailOnResult}
            onChange={(e) => setEmailOnResult(e.target.checked)}
            disabled={busy}
            style={{ marginTop: 3 }}
          />
          <span>
            E-mail matter staff when a search result is ready
            <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>
              Sends when the result file lands (webhook or Sync). Uses the matter’s portal staff recipients, or the fee
              earner. Requires Admin → E-mail → automated alert e-mail.
            </div>
          </span>
        </label>
      </div>

      {settings?.configured ? (
        <p className="muted" style={{ margin: 0 }}>
          Status: configured and ready.
        </p>
      ) : (
        <p className="muted" style={{ margin: 0 }}>
          Status: incomplete — enable, client ID, and access token are required.
        </p>
      )}

      <div className="row" style={{ gap: 8 }}>
        <button type="button" className="btn primary" disabled={busy} onClick={() => void save()}>
          {busy ? 'Saving…' : 'Save Casera settings'}
        </button>
      </div>
    </div>
  )
}
