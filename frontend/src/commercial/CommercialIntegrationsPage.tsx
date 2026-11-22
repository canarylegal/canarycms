import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch } from '../api'
import { commercialPackageActive, type CommercialPackageStatus } from '../types/commercial'
import { CommercialConnectionPanel } from './CommercialConnectionPanel'
import { CommercialAdminIntegrationsSlot } from './CommercialSlotHosts'

/** Licence overview is always available, including Core-only installations. */
export function CommercialIntegrationsPage({ token }: { token: string }) {
  return <IntegrationsSession key={token} token={token} />
}

function IntegrationsSession({ token }: { token: string }) {
  const [validated, setValidated] = useState(false)
  const [tab, setTab] = useState<'overview' | 'providers'>('overview')
  const [pkg, setPackage] = useState<CommercialPackageStatus | null>(null)
  const [error, setError] = useState(false)
  const [loading, setLoading] = useState(true)
  const generation = useRef({ value: 0 })
  const load = useCallback(async () => {
    const current = ++generation.current.value
    setLoading(true)
    setError(false)
    try {
      const value = await apiFetch<CommercialPackageStatus>('/commercial-package/status', { token })
      if (generation.current.value === current) setPackage(value)
    } catch {
      // Keep previously confirmed local provider settings accessible during an outage.
      if (generation.current.value === current) setError(true)
    } finally {
      if (generation.current.value === current) setLoading(false)
    }
  }, [token])
  useEffect(() => {
    void load()
    const clock = generation.current
    return () => { clock.value++ }
  }, [load])
  const available = commercialPackageActive(pkg)
  const providersEnabled = available && validated
  const providersOpen = tab === 'providers' && providersEnabled
  const onValidationChange = useCallback((value: boolean) => {
    setValidated(value)
    if (!value) setTab('overview')
  }, [])
  return <div className="stack" style={{ gap: 12 }}>
    <div className="adminTabStrip adminTabStrip--nested" role="tablist" aria-label="Commercial sections">
      <button type="button" role="tab" aria-selected={!providersOpen} className={`adminTab${!providersOpen ? ' is-active' : ''}`} onClick={() => setTab('overview')}>Overview</button>
      {available && <button type="button" role="tab" disabled={!providersEnabled} aria-selected={providersOpen} style={!providersEnabled ? { opacity: 0.45, cursor: 'not-allowed' } : undefined} className={`adminTab${providersOpen ? ' is-active' : ''}`} onClick={() => { if (providersEnabled) setTab('providers') }}>Provider settings</button>}
    </div>
    {error && <p role="alert">Could not check available integrations. <button type="button" disabled={loading} onClick={() => void load()}>Retry integrations</button></p>}
    <div hidden={providersOpen}>
      <CommercialConnectionPanel token={token} onValidationChange={onValidationChange} />
      {loading && !pkg && <p className="muted">Checking available integrations…</p>}
      {available ? !validated && <p>Validate your licence key to access Provider settings.</p>
        : pkg && !error ? <p>{pkg.fault ? 'The integration package needs attention before provider settings can be opened.' : 'No provider settings are available in this installation yet.'} Activating a licence does not connect your provider accounts automatically.</p> : null}
    </div>
    {providersOpen && <CommercialAdminIntegrationsSlot token={token} />}
  </div>
}
