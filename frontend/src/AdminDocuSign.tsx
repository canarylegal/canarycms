import { useEffect, useState } from 'react'
import { apiFetch } from './api'
import type { ApiError } from './api'
import type { DocusignIntegrationSettingsOut } from './types'

export function AdminDocuSign({ token }: { token: string }) {
  const [settings, setSettings] = useState<DocusignIntegrationSettingsOut | null>(null)
  const [enabled, setEnabled] = useState(false)
  const [useDemo, setUseDemo] = useState(true)
  const [allowTierA, setAllowTierA] = useState(true)
  const [allowTierB, setAllowTierB] = useState(false)
  const [allowTierC, setAllowTierC] = useState(false)
  const [allowWes, setAllowWes] = useState(true)
  const [allowQes, setAllowQes] = useState(false)
  const [accountId, setAccountId] = useState('')
  const [integrationKey, setIntegrationKey] = useState('')
  const [userId, setUserId] = useState('')
  const [apiBaseUri, setApiBaseUri] = useState('')
  const [rsaPrivateKey, setRsaPrivateKey] = useState('')
  const [connectHmacSecret, setConnectHmacSecret] = useState('')
  const [costStandard, setCostStandard] = useState('')
  const [costWes, setCostWes] = useState('')
  const [costQes, setCostQes] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [ok, setOk] = useState(false)

  async function load() {
    setErr(null)
    try {
      const s = await apiFetch<DocusignIntegrationSettingsOut>('/admin/docusign/settings', { token })
      setSettings(s)
      setEnabled(s.enabled)
      setUseDemo(s.use_demo)
      setAllowTierA(s.allow_tier_a)
      setAllowTierB(s.allow_tier_b)
      setAllowTierC(s.allow_tier_c)
      setAllowWes(s.allow_wes)
      setAllowQes(s.allow_qes)
      setAccountId(s.account_id ?? '')
      setIntegrationKey(s.integration_key ?? '')
      setUserId(s.user_id ?? '')
      setApiBaseUri(s.api_base_uri ?? '')
      setCostStandard(s.cost_standard_pence != null ? (s.cost_standard_pence / 100).toFixed(2) : '')
      setCostWes(s.cost_wes_pence != null ? (s.cost_wes_pence / 100).toFixed(2) : '')
      setCostQes(s.cost_qes_pence != null ? (s.cost_qes_pence / 100).toFixed(2) : '')
      setRsaPrivateKey('')
      setConnectHmacSecret('')
    } catch (e) {
      setSettings(null)
      setErr((e as ApiError).message ?? 'Failed to load DocuSign settings')
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
        use_demo: useDemo,
        allow_tier_a: allowTierA,
        allow_tier_b: allowTierB,
        allow_tier_c: allowTierC,
        allow_wes: allowWes,
        allow_qes: allowQes,
        account_id: accountId.trim() || null,
        integration_key: integrationKey.trim() || null,
        user_id: userId.trim() || null,
        api_base_uri: apiBaseUri.trim() || null,
      }
      if (rsaPrivateKey.trim()) body.rsa_private_key = rsaPrivateKey.trim()
      if (connectHmacSecret.trim()) body.connect_hmac_secret = connectHmacSecret.trim()
      const parseCost = (s: string) => {
        const t = s.trim()
        if (!t) return null
        const pence = Math.round(parseFloat(t) * 100)
        return Number.isNaN(pence) || pence <= 0 ? null : pence
      }
      body.cost_standard_pence = parseCost(costStandard)
      body.cost_wes_pence = parseCost(costWes)
      body.cost_qes_pence = parseCost(costQes)
      const s = await apiFetch<DocusignIntegrationSettingsOut>('/admin/docusign/settings', {
        token,
        method: 'PUT',
        json: body,
      })
      setSettings(s)
      setOk(true)
      setRsaPrivateKey('')
      setConnectHmacSecret('')
    } catch (e) {
      setErr((e as ApiError).message ?? 'Could not save DocuSign settings')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack" style={{ gap: 16, maxWidth: 720 }}>
      <div>
        <h2 style={{ margin: 0 }}>DocuSign</h2>
        <p className="muted" style={{ margin: '8px 0 0' }}>
          Connect your firm&apos;s DocuSign account. Credentials are stored encrypted. Use demo mode while testing.
        </p>
      </div>

      {err ? <div className="err">{err}</div> : null}
      {ok ? <div className="ok">DocuSign settings saved.</div> : null}

      <label className="row" style={{ gap: 8, alignItems: 'center' }}>
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} disabled={busy} />
        <span>Enable DocuSign integration</span>
      </label>

      <label className="row" style={{ gap: 8, alignItems: 'center' }}>
        <input type="checkbox" checked={useDemo} onChange={(e) => setUseDemo(e.target.checked)} disabled={busy} />
        <span>Use DocuSign demo environment</span>
      </label>

      <fieldset className="stack" style={{ gap: 8, border: '1px solid var(--border)', padding: 12 }}>
        <legend>Document tiers available to senders</legend>
        <label className="row" style={{ gap: 8 }}>
          <input type="checkbox" checked={allowTierA} onChange={(e) => setAllowTierA(e.target.checked)} disabled={busy} />
          <span>Tier A — client care, terms, questionnaires</span>
        </label>
        <label className="row" style={{ gap: 8 }}>
          <input type="checkbox" checked={allowTierB} onChange={(e) => setAllowTierB(e.target.checked)} disabled={busy} />
          <span>Tier B — contractual (non-lodged)</span>
        </label>
        <label className="row" style={{ gap: 8 }}>
          <input type="checkbox" checked={allowTierC} onChange={(e) => setAllowTierC(e.target.checked)} disabled={busy} />
          <span>Tier C — Land Registry deeds</span>
        </label>
      </fieldset>

      <fieldset className="stack" style={{ gap: 8, border: '1px solid var(--border)', padding: 12 }}>
        <legend>Signature levels available to senders</legend>
        <label className="row" style={{ gap: 8 }}>
          <input type="checkbox" checked={allowWes} onChange={(e) => setAllowWes(e.target.checked)} disabled={busy} />
          <span>Witnessed e-sign (WES)</span>
        </label>
        <label className="row" style={{ gap: 8 }}>
          <input type="checkbox" checked={allowQes} onChange={(e) => setAllowQes(e.target.checked)} disabled={busy} />
          <span>Qualified e-sign (QES)</span>
        </label>
      </fieldset>

      <fieldset className="stack" style={{ gap: 8, border: '1px solid var(--border)', padding: 12 }}>
        <legend>Forecast envelope costs (office ledger)</legend>
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>
          When staff send for signature, Canary posts an anticipated office debit on the matter for the matching
          amount. Cashiers can edit the amount when reconciling against the DocuSign invoice. Leave blank to skip
          auto-posting.
        </p>
        <label className="stack" style={{ gap: 4 }}>
          <span>Standard eSignature (£)</span>
          <input
            className="input"
            value={costStandard}
            onChange={(e) => setCostStandard(e.target.value)}
            disabled={busy}
            inputMode="decimal"
            placeholder="e.g. 1.50"
          />
        </label>
        <label className="stack" style={{ gap: 4 }}>
          <span>Witnessed (WES) (£)</span>
          <input
            className="input"
            value={costWes}
            onChange={(e) => setCostWes(e.target.value)}
            disabled={busy}
            inputMode="decimal"
            placeholder="e.g. 2.00"
          />
        </label>
        <label className="stack" style={{ gap: 4 }}>
          <span>Qualified (QES) (£)</span>
          <input
            className="input"
            value={costQes}
            onChange={(e) => setCostQes(e.target.value)}
            disabled={busy}
            inputMode="decimal"
            placeholder="e.g. 5.00"
          />
        </label>
      </fieldset>

      <div className="stack" style={{ gap: 8 }}>
        <label className="stack" style={{ gap: 4 }}>
          <span>Account ID</span>
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>
            Use the API Account ID (GUID) from Apps and Keys — not the numeric account number shown in the DocuSign
            sidebar. Leave blank to auto-detect from the API sender after JWT consent.
          </p>
          <input value={accountId} onChange={(e) => setAccountId(e.target.value)} disabled={busy} autoComplete="off" placeholder="e.g. 95f7383e-…" />
        </label>
        <label className="stack" style={{ gap: 4 }}>
          <span>Integration key (client ID)</span>
          <input value={integrationKey} onChange={(e) => setIntegrationKey(e.target.value)} disabled={busy} autoComplete="off" />
        </label>
        <label className="stack" style={{ gap: 4 }}>
          <span>User ID (API sender)</span>
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>
            DocuSign Admin → Users → open the sender profile → API User ID (GUID). Must be a user in the same
            environment (demo vs production) as the integration key.
          </p>
          <input value={userId} onChange={(e) => setUserId(e.target.value)} disabled={busy} autoComplete="off" />
        </label>
        <label className="stack" style={{ gap: 4 }}>
          <span>API base URI (optional — usually auto-detected)</span>
          <input value={apiBaseUri} onChange={(e) => setApiBaseUri(e.target.value)} disabled={busy} autoComplete="off" placeholder="https://demo.docusign.net/restapi" />
        </label>
        <label className="stack" style={{ gap: 4 }}>
          <span>RSA private key {settings?.rsa_private_key_configured ? '(configured — paste to replace)' : ''}</span>
          <textarea value={rsaPrivateKey} onChange={(e) => setRsaPrivateKey(e.target.value)} disabled={busy} rows={4} autoComplete="off" />
        </label>
        <label className="stack" style={{ gap: 4 }}>
          <span>Connect HMAC secret {settings?.connect_hmac_secret_configured ? '(configured — paste to replace)' : ''}</span>
          <input value={connectHmacSecret} onChange={(e) => setConnectHmacSecret(e.target.value)} disabled={busy} autoComplete="off" type="password" />
        </label>
      </div>

      <p className="muted" style={{ margin: 0, fontSize: 13 }}>
        Webhook URL for DocuSign Connect: <code>/api/docusign/connect</code> (append to your public Canary URL).
      </p>

      {settings?.configured ? (
        <p className="muted" style={{ margin: 0 }}>Status: configured and ready.</p>
      ) : (
        <p className="muted" style={{ margin: 0 }}>Status: incomplete — account ID, integration key, user ID, and private key are required.</p>
      )}

      <div className="row" style={{ gap: 8 }}>
        <button type="button" className="btn primary" disabled={busy} onClick={() => void save()}>
          {busy ? 'Saving…' : 'Save DocuSign settings'}
        </button>
      </div>
    </div>
  )
}
