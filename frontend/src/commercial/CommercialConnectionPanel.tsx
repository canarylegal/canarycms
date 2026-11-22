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

export function CommercialConnectionPanel({ token, onValidationChange }: { token: string; onValidationChange?: (validated: boolean) => void }) {
  const [status, setStatus] = useState<ConnectionStatus | null>(null)
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [replacing, setReplacing] = useState(false)
  const [error, setError] = useState('')
  const generation = useRef({ value: 0 })
  useEffect(() => {
    const clock = generation.current
    const current = ++clock.value
    setStatus(null)
    setCode('')
    setReplacing(false)
    setError('')
    setBusy(false)
    async function readStatus() {
      try {
        const value = await apiFetch<ConnectionStatus>('/commercial-connection/status', { token })
        if (clock.value === current) setStatus(value)
      } catch {
        if (clock.value === current) setError('Could not read the Commercial connection.')
      }
    }
    void readStatus()
    return () => { clock.value++ }
  }, [token])

  useEffect(() => {
    onValidationChange?.(status?.enabled === true && status.connected === true && !busy && !error)
  }, [status, busy, error, onValidationChange])

  async function change(action: 'activate' | 'disconnect') {
    if (!status || busy) return
    const current = ++generation.current.value
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
      if (generation.current.value === current) { setStatus(next); setReplacing(false) }
    } catch {
      if (generation.current.value === current) {
        setError('Connection change could not be confirmed. Check the status before trying again.')
        try {
          const next = await apiFetch<ConnectionStatus>('/commercial-connection/status', { token })
          if (generation.current.value === current) setStatus(next)
        } catch { /* Preserve last known status; never infer success. */ }
      }
    } finally {
      if (generation.current.value === current) setBusy(false)
    }
  }

  async function refresh() {
    const current = ++generation.current.value
    setBusy(true)
    setError('')
    try {
      const next = await apiFetch<ConnectionStatus>('/commercial-connection/status', { token })
      if (generation.current.value === current) setStatus(next)
    } catch {
      if (generation.current.value === current) setError('Could not check the Commercial connection. Your saved settings have been retained.')
    } finally {
      if (generation.current.value === current) setBusy(false)
    }
  }

  return <section aria-label="Canary Commercial licence" className="card" style={{ padding: 16, marginBottom: 16 }}>
    <h3>Canary Commercial</h3>
    <p>Your firm uses its own provider accounts and is billed directly by those providers.</p>
    {!status ? <p>{error ? 'Connection status unavailable.' : 'Loading licence connection…'}</p> : <>
      <p><strong>{status.connected ? 'Activation recorded on this installation' : 'Not activated'}</strong></p>
      {status.connected && <p>Live subscription details and included integrations are not available yet. Activation does not automatically connect your provider accounts.</p>}
      {!status.enabled && <p>Licence activation is not enabled for this installation.</p>}
      <p>Firm credentials stay in this installation. Existing results and matter records remain accessible if you disconnect.</p>
      {(!status.connected || replacing) && <form onSubmit={event => { event.preventDefault(); void change('activate') }}>
        <label>Canary Commercial licence key <input type="password" autoComplete="off" value={code} maxLength={512} disabled={busy || !status.enabled} onChange={event => setCode(event.target.value)} /></label>
        <button type="submit" style={{ marginTop: 8 }} disabled={busy || !status.enabled || !code.trim()}>{replacing ? 'Replace licence key' : 'Activate licence'}</button>
        {replacing && <button type="button" disabled={busy} onClick={() => { setReplacing(false); setCode('') }}>Cancel</button>}
        <p className="muted">The key is exchanged for a secure local connection and is not displayed or retained afterward.</p>
      </form>}
      {status.connected && <div className="row" style={{ gap: 8 }}>
        {!replacing && <button type="button" disabled={busy || !status.enabled} onClick={() => setReplacing(true)}>Replace licence key</button>}
        <button type="button" disabled={busy} onClick={() => void change('disconnect')}>Disconnect hosted service locally</button>
      </div>}
    </>}
    {error && <p role="alert">{error}</p>}
    <button type="button" disabled={busy} onClick={() => void refresh()}>Refresh connection status</button>
  </section>
}
