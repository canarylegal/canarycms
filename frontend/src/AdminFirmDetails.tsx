import { useEffect, useState } from 'react'
import { apiFetch } from './api'
import type { ApiError } from './api'
import type { FirmSettingsOut } from './types'

export function AdminFirmDetails({ token }: { token: string }) {
  const [row, setRow] = useState<FirmSettingsOut | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const [tradingName, setTradingName] = useState('')
  const [registeredName, setRegisteredName] = useState('')
  const [addr1, setAddr1] = useState('')
  const [addr2, setAddr2] = useState('')
  const [town, setTown] = useState('')
  const [county, setCounty] = useState('')
  const [postcode, setPostcode] = useState('')
  const [clientBankName, setClientBankName] = useState('')
  const [clientBankSort, setClientBankSort] = useState('')
  const [clientBankLast4, setClientBankLast4] = useState('')

  async function load() {
    setErr(null)
    setSaved(false)
    try {
      const data = await apiFetch<FirmSettingsOut>('/admin/firm-settings', { token })
      setRow(data)
      setTradingName(data.trading_name ?? '')
      setRegisteredName(data.registered_company_name ?? '')
      setAddr1(data.addr_line1 ?? '')
      setAddr2(data.addr_line2 ?? '')
      setTown(data.town_city ?? '')
      setCounty(data.county ?? '')
      setPostcode(data.postcode ?? '')
      setClientBankName(data.client_bank_account_name ?? '')
      setClientBankSort(data.client_bank_sort_code ?? '')
      setClientBankLast4(data.client_bank_account_number_last4 ?? '')
    } catch (e) {
      setErr((e as ApiError).message ?? 'Failed to load firm details')
    }
  }

  useEffect(() => {
    void load()
  }, [token])

  async function save() {
    setBusy(true)
    setErr(null)
    setSaved(false)
    try {
      const data = await apiFetch<FirmSettingsOut>('/admin/firm-settings', {
        token,
        method: 'PATCH',
        json: {
          trading_name: tradingName.trim(),
          registered_company_name: registeredName.trim() || null,
          addr_line1: addr1.trim() || null,
          addr_line2: addr2.trim() || null,
          town_city: town.trim() || null,
          county: county.trim() || null,
          postcode: postcode.trim() || null,
          client_bank_account_name: clientBankName.trim() || null,
          client_bank_sort_code: clientBankSort.trim() || null,
          client_bank_account_number_last4: clientBankLast4.trim() || null,
        },
      })
      setRow(data)
      setSaved(true)
    } catch (e) {
      setErr((e as ApiError).message ?? 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack">
      <div className="paneHead">
        <h3 style={{ margin: 0 }}>Firm details</h3>
        <button type="button" className="btn" onClick={() => void load()} disabled={busy}>
          Reload
        </button>
      </div>
      <div className="muted" style={{ marginBottom: 8 }}>
        Used as precedent merge codes (<code>[FIRM_*]</code>) and shown when composing letters. Letterhead layout for{' '}
        <strong>Letter</strong> precedents is configured under <strong>Admin → Precedents</strong>.
      </div>
      {err ? <div className="error">{err}</div> : null}
      {saved ? <div className="muted">Saved.</div> : null}

      <div className="card" style={{ padding: 16 }}>
        {!row ? (
          <div className="muted">Loading…</div>
        ) : (
          <div className="stack" style={{ gap: 12 }}>
            <label className="field">
              <span>Firm trading name</span>
              <input value={tradingName} onChange={(e) => setTradingName(e.target.value)} disabled={busy} />
            </label>
            <label className="field">
              <span>Registered company name (optional)</span>
              <input value={registeredName} onChange={(e) => setRegisteredName(e.target.value)} disabled={busy} />
            </label>
            <div style={{ fontWeight: 600, marginTop: 8 }}>Firm address</div>
            <label className="field">
              <span>Address line 1</span>
              <input value={addr1} onChange={(e) => setAddr1(e.target.value)} disabled={busy} />
            </label>
            <label className="field">
              <span>Address line 2</span>
              <input value={addr2} onChange={(e) => setAddr2(e.target.value)} disabled={busy} />
            </label>
            <label className="field">
              <span>Town / city</span>
              <input value={town} onChange={(e) => setTown(e.target.value)} disabled={busy} />
            </label>
            <label className="field">
              <span>County</span>
              <input value={county} onChange={(e) => setCounty(e.target.value)} disabled={busy} />
            </label>
            <label className="field">
              <span>Postcode</span>
              <input value={postcode} onChange={(e) => setPostcode(e.target.value)} disabled={busy} />
            </label>
            <div style={{ fontWeight: 600, marginTop: 8 }}>Client bank account (for reconcile report)</div>
            <div className="muted" style={{ fontSize: 13, marginBottom: 4 }}>
              Display only — used on the client account reconcile report. Do not enter the full account number.
            </div>
            <label className="field">
              <span>Account name</span>
              <input value={clientBankName} onChange={(e) => setClientBankName(e.target.value)} disabled={busy} />
            </label>
            <label className="field">
              <span>Sort code</span>
              <input value={clientBankSort} onChange={(e) => setClientBankSort(e.target.value)} disabled={busy} placeholder="12-34-56" />
            </label>
            <label className="field">
              <span>Account number (last 4 digits)</span>
              <input
                value={clientBankLast4}
                onChange={(e) => setClientBankLast4(e.target.value.replace(/\D/g, '').slice(0, 4))}
                disabled={busy}
                maxLength={4}
                inputMode="numeric"
              />
            </label>
            <button type="button" className="btn primary" onClick={() => void save()} disabled={busy}>
              Save firm details
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
