import { useEffect, useRef, useState } from 'react'
import { apiFetch } from '../api'

export type ConnectionStatus = {
  enabled: boolean
  connected: boolean
  version: number
  installation_id: string | null
  tenant_id: string | null
  contract_version: string
}

export function CommercialConnectionPanel({ token }: { token: string }) {
  const [status, setStatus] = useState<ConnectionStatus | null>(null)
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const generation = useRef(0)
  useEffect(() => {
    const current = ++generation.current
    setStatus(null)
    setCode('')
    setError('')
    setBusy(false)
    void apiFetch<ConnectionStatus>('/commercial-connection/status', { token })
      .then(value => { if (generation.current === current) setStatus(value) })
      .catch(() => { if (generation.current === current) setError('Could not read the Commercial connection.') })
    return () => { generation.current = current + 1 }
  }, [token])

  async function change(action: 'activate' | 'disconnect') {
    if (!status || busy) return
    const current = generation.current
    setBusy(true)
    setError('')
    const activationCode = code
    setCode('')
    try {
      const next = await apiFetch<ConnectionStatus>('/commercial-connection/' + action, {
        token, method: 'POST', json: {
          expected_version: status.version,
          ...(action === 'activate' ? { activation_code: activationCode } : {}),
        },
      })
      if (generation.current === current) setStatus(next)
    } catch {
      if (generation.current === current) {
        setError('Connection change could not be confirmed. Check the status before trying again.')
        try {
          const next = await apiFetch<ConnectionStatus>('/commercial-connection/status', { token })
          if (generation.current === current) setStatus(next)
        } catch { /* Preserve last known status; never infer success. */ }
      }
    } finally {
      if (generation.current === current) setBusy(false)
    }
  }

  if (!status?.enabled && !status?.connected) return error ? <p role="alert">{error}</p> : null
  return <section aria-label="Hosted Commercial connection" className="card" style={{ padding: 16, marginBottom: 16 }}>
    <h3>Hosted Commercial connection</h3>
    <p>{status.connected ? 'Connected' : 'Not connected'}{!status.enabled ? ' — outbound connection disabled' : ''}</p>
    <p>Firm credentials and existing matter records stay in this installation. Existing integrations continue to use their current connections.</p>
    {status.installation_id && <p>Installation: {status.installation_id}</p>}
    {status.enabled && !status.connected && <form onSubmit={event => { event.preventDefault(); void change('activate') }}>
      <label>Commercial activation code <input type="password" autoComplete="off" value={code} maxLength={512} disabled={busy} onChange={event => setCode(event.target.value)} /></label>
      <button type="submit" disabled={busy || !code.trim()}>Connect Commercial</button>
    </form>}
    {status.connected && <button type="button" disabled={busy} onClick={() => void change('disconnect')}>Disconnect hosted service locally</button>}
    {error && <p role="alert">{error}</p>}
  </section>
}
