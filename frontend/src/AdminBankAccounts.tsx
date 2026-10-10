import { useEffect, useState } from 'react'
import { apiFetch, type ApiError } from './api'
import type { FirmBankAccountOut } from './types/bank'

export function AdminBankAccounts({ token }: { token: string }) {
  const [rows, setRows] = useState<FirmBankAccountOut[]>([])
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [name, setName] = useState('Client account')
  const [kind, setKind] = useState<'client' | 'office'>('client')
  const [sortCode, setSortCode] = useState('')
  const [accountNumber, setAccountNumber] = useState('')
  const [isDefault, setIsDefault] = useState(true)

  async function load() {
    setErr(null)
    try {
      const data = await apiFetch<FirmBankAccountOut[]>('/admin/bank-accounts', { token })
      setRows(data)
    } catch (e) {
      setErr((e as ApiError).message ?? 'Failed to load bank accounts')
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload when token changes
  }, [token])

  async function create() {
    setBusy(true)
    setErr(null)
    try {
      await apiFetch<FirmBankAccountOut>('/admin/bank-accounts', {
        token,
        method: 'POST',
        json: {
          name: name.trim(),
          account_kind: kind,
          sort_code: sortCode.trim() || null,
          account_number: accountNumber.trim() || null,
          is_default: isDefault,
          is_active: true,
        },
      })
      setAccountNumber('')
      await load()
    } catch (e) {
      setErr((e as ApiError).message ?? 'Could not create bank account')
    } finally {
      setBusy(false)
    }
  }

  async function toggleActive(row: FirmBankAccountOut) {
    setBusy(true)
    try {
      await apiFetch(`/admin/bank-accounts/${row.id}`, {
        token,
        method: 'PATCH',
        json: { is_active: !row.is_active },
      })
      await load()
    } catch (e) {
      setErr((e as ApiError).message ?? 'Could not update')
    } finally {
      setBusy(false)
    }
  }

  async function makeDefault(row: FirmBankAccountOut) {
    setBusy(true)
    try {
      await apiFetch(`/admin/bank-accounts/${row.id}`, {
        token,
        method: 'PATCH',
        json: { is_default: true },
      })
      await load()
    } catch (e) {
      setErr((e as ApiError).message ?? 'Could not update')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack" style={{ gap: 16, maxWidth: 820 }}>
      <div>
        <h3 style={{ margin: 0 }}>Bank accounts</h3>
        <p className="muted" style={{ margin: '8px 0 0' }}>
          Client bank accounts are required on actual client ledger postings and power statement
          reconciliation and end-of-month packs.
        </p>
      </div>
      {err ? <div className="err">{err}</div> : null}

      <table className="table" style={{ width: '100%' }}>
        <thead>
          <tr>
            <th>Name</th>
            <th>Kind</th>
            <th>Sort code</th>
            <th>Account</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>
                {r.name}
                {r.is_default ? ' (default)' : ''}
                {!r.is_active ? ' — inactive' : ''}
              </td>
              <td>{r.account_kind}</td>
              <td>{r.sort_code || '—'}</td>
              <td>{r.account_number_last4 ? `•••• ${r.account_number_last4}` : '—'}</td>
              <td className="row" style={{ gap: 8 }}>
                {!r.is_default && r.is_active ? (
                  <button type="button" className="btn" disabled={busy} onClick={() => void makeDefault(r)}>
                    Default
                  </button>
                ) : null}
                <button type="button" className="btn" disabled={busy} onClick={() => void toggleActive(r)}>
                  {r.is_active ? 'Deactivate' : 'Activate'}
                </button>
              </td>
            </tr>
          ))}
          {rows.length === 0 ? (
            <tr>
              <td colSpan={5} className="muted">
                No bank accounts yet — add a client account below.
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>

      <div className="stack" style={{ gap: 10, maxWidth: 480 }}>
        <h4 style={{ margin: 0 }}>Add account</h4>
        <label className="stack" style={{ gap: 4 }}>
          <span>Name</span>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="stack" style={{ gap: 4 }}>
          <span>Kind</span>
          <select className="input" value={kind} onChange={(e) => setKind(e.target.value as 'client' | 'office')}>
            <option value="client">Client</option>
            <option value="office">Office</option>
          </select>
        </label>
        <label className="stack" style={{ gap: 4 }}>
          <span>Sort code</span>
          <input className="input" value={sortCode} onChange={(e) => setSortCode(e.target.value)} />
        </label>
        <label className="stack" style={{ gap: 4 }}>
          <span>Account number</span>
          <input className="input" value={accountNumber} onChange={(e) => setAccountNumber(e.target.value)} />
        </label>
        <label className="row" style={{ gap: 8 }}>
          <input type="checkbox" checked={isDefault} onChange={(e) => setIsDefault(e.target.checked)} />
          <span>Default for this kind</span>
        </label>
        <button type="button" className="btn primary" disabled={busy || !name.trim()} onClick={() => void create()}>
          {busy ? 'Saving…' : 'Add bank account'}
        </button>
      </div>
    </div>
  )
}
