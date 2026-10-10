import { useEffect, useState } from 'react'
import { apiFetch } from './api'
import type { ApiError } from './api'
import { AdminCasera } from './AdminCasera'
import type { SearchIntegrationSettingsOut } from './types/searches'

export function AdminSearches({ token }: { token: string }) {
  const [settings, setSettings] = useState<SearchIntegrationSettingsOut | null>(null)
  const [provider, setProvider] = useState('none')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [ok, setOk] = useState(false)

  async function load() {
    setErr(null)
    try {
      const s = await apiFetch<SearchIntegrationSettingsOut>('/admin/searches/settings', { token })
      setSettings(s)
      setProvider(s.provider || 'none')
    } catch (e) {
      setSettings(null)
      setErr((e as ApiError).message ?? 'Failed to load Searches settings')
    }
  }

  useEffect(() => {
    void load()
  }, [token])

  async function saveProvider(next: string) {
    setBusy(true)
    setErr(null)
    setOk(false)
    try {
      const s = await apiFetch<SearchIntegrationSettingsOut>('/admin/searches/settings', {
        token,
        method: 'PUT',
        json: { provider: next },
      })
      setSettings(s)
      setProvider(s.provider || 'none')
      setOk(true)
    } catch (e) {
      setErr((e as ApiError).message ?? 'Could not save search provider')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack" style={{ gap: 16, maxWidth: 720 }}>
      <div>
        <h2 style={{ margin: 0 }}>Searches</h2>
        <p className="muted" style={{ margin: '8px 0 0' }}>
          Choose which search provider powers the matter Searches menu. Only one provider can be active.
        </p>
      </div>

      {err ? <div className="err">{err}</div> : null}
      {ok ? <div className="ok">Search provider saved.</div> : null}

      <label className="stack" style={{ gap: 4 }}>
        <span>Search provider</span>
        <select
          className="input"
          value={provider}
          disabled={busy || !settings}
          onChange={(e) => {
            const next = e.target.value
            setProvider(next)
            void saveProvider(next)
          }}
        >
          <option value="none">None</option>
          {(settings?.available_providers ?? []).map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
      </label>

      {provider === 'none' ? (
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>
          Matter Searches will show that no search provider is configured until you choose one.
        </p>
      ) : null}

      {provider === 'casera' ? (
        <div
          style={{
            borderTop: '1px solid var(--border)',
            paddingTop: 16,
          }}
        >
          <AdminCasera token={token} />
        </div>
      ) : null}
    </div>
  )
}
