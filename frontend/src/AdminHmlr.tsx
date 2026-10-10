import { useEffect, useState } from 'react'
import { apiFetch } from './api'
import type { ApiError } from './api'
import type { HmlrIntegrationSettingsOut } from './types/hmlr'

export function AdminHmlr({ token }: { token: string }) {
  const [settings, setSettings] = useState<HmlrIntegrationSettingsOut | null>(null)
  const [enabled, setEnabled] = useState(false)
  const [sandbox, setSandbox] = useState(true)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [customerReference, setCustomerReference] = useState('')
  const [contactName, setContactName] = useState('')
  const [contactPhone, setContactPhone] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [ok, setOk] = useState(false)

  async function load() {
    setErr(null)
    try {
      const s = await apiFetch<HmlrIntegrationSettingsOut>('/admin/hmlr/settings', { token })
      setSettings(s)
      setEnabled(s.enabled)
      setSandbox(s.sandbox)
      setUsername(s.username ?? '')
      setCustomerReference(s.customer_reference ?? '')
      setContactName(s.contact_name ?? '')
      setContactPhone(s.contact_phone ?? '')
      setPassword('')
    } catch (e) {
      setSettings(null)
      setErr((e as ApiError).message ?? 'Failed to load Land Registry settings')
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
        username: username.trim() || null,
        customer_reference: customerReference.trim() || null,
        contact_name: contactName.trim() || null,
        contact_phone: contactPhone.trim() || null,
      }
      if (password.trim()) body.password = password.trim()
      const s = await apiFetch<HmlrIntegrationSettingsOut>('/admin/hmlr/settings', {
        token,
        method: 'PUT',
        json: body,
      })
      setSettings(s)
      setOk(true)
      setPassword('')
    } catch (e) {
      setErr((e as ApiError).message ?? 'Could not save Land Registry settings')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack" style={{ gap: 16, maxWidth: 720 }}>
      <div>
        <h3 style={{ margin: 0 }}>HM Land Registry</h3>
        <p className="muted" style={{ margin: '8px 0 0' }}>
          Business Gateway integration for official copies. Separate from Searches / Casera. Use the customer test
          (sandbox) environment until live access is arranged — no real official-copy charges on the stub.
        </p>
      </div>

      {err ? <div className="err">{err}</div> : null}
      {ok ? <div className="ok">Land Registry settings saved.</div> : null}

      <label className="row" style={{ gap: 8, alignItems: 'center' }}>
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} disabled={busy} />
        <span>Enable Land Registry on matters</span>
      </label>

      <label className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
        <input
          type="checkbox"
          checked={sandbox}
          onChange={(e) => setSandbox(e.target.checked)}
          disabled={busy}
          style={{ marginTop: 3 }}
        />
        <span>
          Sandbox / customer test
          <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>
            Uses HMLR stub endpoints (<code>bgtest.landregistry.gov.uk</code>). Until the test SSL client certificate
            arrives from Channel Partners, Canary runs a local mock that returns sample PDFs so the matter UI can be
            developed.
          </div>
        </span>
      </label>

      <div className="stack" style={{ gap: 8 }}>
        <label className="stack" style={{ gap: 4 }}>
          <span>Business Gateway username</span>
          <input value={username} onChange={(e) => setUsername(e.target.value)} disabled={busy} autoComplete="off" />
        </label>
        <label className="stack" style={{ gap: 4 }}>
          <span>Password {settings?.password_configured ? '(configured — paste to replace)' : ''}</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={busy}
            autoComplete="new-password"
          />
        </label>
        <label className="stack" style={{ gap: 4 }}>
          <span>Customer reference (optional)</span>
          <input
            value={customerReference}
            onChange={(e) => setCustomerReference(e.target.value)}
            disabled={busy}
            autoComplete="off"
          />
        </label>
        <label className="stack" style={{ gap: 4 }}>
          <span>Contact name (optional)</span>
          <input value={contactName} onChange={(e) => setContactName(e.target.value)} disabled={busy} autoComplete="off" />
        </label>
        <label className="stack" style={{ gap: 4 }}>
          <span>Contact phone (optional)</span>
          <input value={contactPhone} onChange={(e) => setContactPhone(e.target.value)} disabled={busy} autoComplete="off" />
        </label>
      </div>

      {settings?.mock_mode ? (
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>
          Status: sandbox mock active (no Gateway HTTPS call yet). Enable above, then use the Land Registry matter
          menu.
        </p>
      ) : settings?.configured ? (
        <p className="muted" style={{ margin: 0 }}>
          Status: configured for Gateway calls.
        </p>
      ) : (
        <p className="muted" style={{ margin: 0 }}>
          Status: incomplete — enable, and for live Gateway calls add username and password.
        </p>
      )}

      <div className="row" style={{ gap: 8 }}>
        <button type="button" className="btn primary" disabled={busy} onClick={() => void save()}>
          {busy ? 'Saving…' : 'Save Land Registry settings'}
        </button>
      </div>
    </div>
  )
}
