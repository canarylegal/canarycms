import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch, apiUrl, applyAuthHeaders, type ApiError } from './api'
import type {
  BankReconciliationOut,
  BankStatementLineOut,
  ClientAccountEomOut,
  FirmBankAccountOut,
  InterMatterJournalOut,
  UnpresentedLedgerLegOut,
  XeroExportOut,
  XeroSettingsOut,
} from './types/bank'
import { defaultPeriodEndDate, formatMoneyPence, parsePoundsToPence } from './reports/utils'

function pence(p: number) {
  return formatMoneyPence(p)
}

function formatLegLabel(u: UnpresentedLedgerLegOut): string {
  const date = u.posted_at.slice(0, 10)
  const matter = u.case_number || u.case_id.slice(0, 8)
  const amt = `${u.direction === 'debit' ? '-' : '+'}${pence(u.amount_pence)}`
  const desc = (u.description || '').trim() || 'Ledger entry'
  return `${date} · ${matter} · ${desc} · ${amt}`
}

export function AccountsBankingPanel({
  token,
  busy,
  setBusy,
  setErr,
  active,
}: {
  token: string
  busy: boolean
  setBusy: (v: boolean) => void
  setErr: (v: string | null) => void
  active: boolean
}) {
  const [banks, setBanks] = useState<FirmBankAccountOut[]>([])
  const [bankId, setBankId] = useState('')
  const [lines, setLines] = useState<BankStatementLineOut[]>([])
  const [unpresented, setUnpresented] = useState<UnpresentedLedgerLegOut[]>([])
  const [recons, setRecons] = useState<BankReconciliationOut[]>([])
  const [eoms, setEoms] = useState<ClientAccountEomOut[]>([])
  const [journals, setJournals] = useState<InterMatterJournalOut[]>([])
  const [periodEnd, setPeriodEnd] = useState(defaultPeriodEndDate)
  const [bankPounds, setBankPounds] = useState('')
  const [matchPairId, setMatchPairId] = useState('')
  const [xero, setXero] = useState<XeroSettingsOut | null>(null)
  const [exports, setExports] = useState<XeroExportOut[]>([])
  const [xeroFrom, setXeroFrom] = useState('')
  const [xeroTo, setXeroTo] = useState('')
  const [journalFrom, setJournalFrom] = useState('')
  const [journalTo, setJournalTo] = useState('')
  const [journalAmt, setJournalAmt] = useState('')
  const [journalDesc, setJournalDesc] = useState('')
  const [msg, setMsg] = useState<string | null>(null)

  const selectedLeg = useMemo(
    () => unpresented.find((u) => u.pair_id === matchPairId) ?? null,
    [unpresented, matchPairId],
  )

  const load = useCallback(async () => {
    setErr(null)
    try {
      const b = await apiFetch<FirmBankAccountOut[]>('/accounts/banking/bank-accounts?kind=client', { token })
      setBanks(b)
      const id = bankId && b.some((x) => x.id === bankId) ? bankId : b.find((x) => x.is_default)?.id || b[0]?.id || ''
      if (id !== bankId) setBankId(id)
      if (!id) {
        setLines([])
        setUnpresented([])
        setRecons([])
        setEoms([])
        return
      }
      const [l, u, r, e, j, xs, xe] = await Promise.all([
        apiFetch<BankStatementLineOut[]>(
          `/accounts/banking/statements/lines?firm_bank_account_id=${id}&unmatched_only=false`,
          { token },
        ),
        apiFetch<UnpresentedLedgerLegOut[]>(`/accounts/banking/unpresented?firm_bank_account_id=${id}`, {
          token,
        }),
        apiFetch<BankReconciliationOut[]>(`/accounts/banking/reconciliations?firm_bank_account_id=${id}`, {
          token,
        }),
        apiFetch<ClientAccountEomOut[]>(`/accounts/banking/eom?firm_bank_account_id=${id}`, { token }),
        apiFetch<InterMatterJournalOut[]>('/accounts/banking/journals', { token }),
        apiFetch<XeroSettingsOut>('/accounts/banking/xero/settings', { token }),
        apiFetch<XeroExportOut[]>('/accounts/banking/xero/exports', { token }),
      ])
      setLines(l)
      setUnpresented(u)
      setRecons(r)
      setEoms(e)
      setJournals(j)
      setXero(xs)
      setExports(xe)
    } catch (e) {
      setErr((e as ApiError).message ?? 'Could not load banking')
    }
  }, [token, bankId, setErr])

  useEffect(() => {
    if (!active) return
    void load()
  }, [active, load])

  async function importFile(file: File) {
    if (!bankId) return
    setBusy(true)
    setErr(null)
    setMsg(null)
    try {
      const fd = new FormData()
      fd.append('firm_bank_account_id', bankId)
      fd.append('file', file)
      const headers = new Headers()
      applyAuthHeaders(headers, token)
      const res = await fetch(apiUrl('/accounts/banking/statements/import'), {
        method: 'POST',
        headers,
        body: fd,
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw { status: res.status, message: body.detail || res.statusText }
      }
      setMsg(`Imported ${file.name}`)
      await load()
    } catch (e) {
      setErr((e as ApiError).message ?? 'Import failed')
    } finally {
      setBusy(false)
    }
  }

  async function matchLine(lineId: string) {
    if (!matchPairId.trim()) {
      setErr('Select a ledger transaction to match')
      return
    }
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/accounts/banking/statements/lines/${lineId}/match`, {
        token,
        method: 'POST',
        json: { ledger_pair_id: matchPairId.trim() },
      })
      setMatchPairId('')
      await load()
    } catch (e) {
      setErr((e as ApiError).message ?? 'Match failed')
    } finally {
      setBusy(false)
    }
  }

  async function createRecon() {
    if (!bankId) return
    const bal = parsePoundsToPence(bankPounds)
    if (bal == null) {
      setErr('Enter a valid statement balance')
      return
    }
    setBusy(true)
    setErr(null)
    try {
      await apiFetch('/accounts/banking/reconciliations', {
        token,
        method: 'POST',
        json: {
          firm_bank_account_id: bankId,
          period_end_date: periodEnd,
          statement_balance_pence: bal,
        },
      })
      await load()
    } catch (e) {
      setErr((e as ApiError).message ?? 'Reconciliation failed')
    } finally {
      setBusy(false)
    }
  }

  async function approveRecon(id: string) {
    setBusy(true)
    setErr(null)
    try {
      await apiFetch(`/accounts/banking/reconciliations/${id}/approve`, { token, method: 'POST' })
      await load()
    } catch (e) {
      setErr((e as ApiError).message ?? 'Approve failed')
    } finally {
      setBusy(false)
    }
  }

  async function runEom() {
    if (!bankId) return
    setBusy(true)
    setErr(null)
    try {
      await apiFetch('/accounts/banking/eom', {
        token,
        method: 'POST',
        json: { firm_bank_account_id: bankId, period_end_date: periodEnd },
      })
      await load()
    } catch (e) {
      setErr((e as ApiError).message ?? 'EOM failed')
    } finally {
      setBusy(false)
    }
  }

  async function createJournal() {
    const amt = parsePoundsToPence(journalAmt)
    if (!journalFrom || !journalTo || amt === null || !journalDesc.trim()) {
      setErr('Journal needs from/to matter ids, amount, and description')
      return
    }
    setBusy(true)
    setErr(null)
    try {
      await apiFetch('/accounts/banking/journals', {
        token,
        method: 'POST',
        json: {
          from_case_id: journalFrom.trim(),
          to_case_id: journalTo.trim(),
          amount_pence: amt,
          description: journalDesc.trim(),
          firm_bank_account_id: bankId || null,
        },
      })
      setJournalDesc('')
      setJournalAmt('')
      await load()
    } catch (e) {
      setErr((e as ApiError).message ?? 'Journal failed')
    } finally {
      setBusy(false)
    }
  }

  async function saveXero() {
    if (!xero) return
    setBusy(true)
    try {
      const s = await apiFetch<XeroSettingsOut>('/accounts/banking/xero/settings', {
        token,
        method: 'PUT',
        json: xero,
      })
      setXero(s)
      setMsg('Xero settings saved')
    } catch (e) {
      setErr((e as ApiError).message ?? 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  async function runXeroExport() {
    if (!xeroFrom || !xeroTo) {
      setErr('Set Xero export period')
      return
    }
    setBusy(true)
    try {
      const row = await apiFetch<XeroExportOut>('/accounts/banking/xero/exports', {
        token,
        method: 'POST',
        json: { period_from: xeroFrom, period_to: xeroTo },
      })
      setMsg(`Xero CSV ready (${row.row_count} rows)`)
      await load()
    } catch (e) {
      setErr((e as ApiError).message ?? 'Export failed')
    } finally {
      setBusy(false)
    }
  }

  async function downloadXero(id: string, filename: string) {
    const headers = new Headers()
    applyAuthHeaders(headers, token)
    const res = await fetch(apiUrl(`/accounts/banking/xero/exports/${id}/download`), { headers })
    if (!res.ok) return
    const blob = await res.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = filename
    a.click()
    URL.revokeObjectURL(a.href)
  }

  async function downloadEom(id: string, filename: string) {
    const headers = new Headers()
    applyAuthHeaders(headers, token)
    const res = await fetch(apiUrl(`/accounts/banking/eom/${id}/download`), { headers })
    if (!res.ok) {
      setErr('Download failed')
      return
    }
    const blob = await res.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = filename
    a.click()
    URL.revokeObjectURL(a.href)
  }

  if (!active) return null

  return (
    <div className="stack" style={{ gap: 20 }}>
      {msg ? <div className="ok">{msg}</div> : null}

      <div className="row" style={{ gap: 12, flexWrap: 'wrap', alignItems: 'end' }}>
        <label className="stack" style={{ gap: 4 }}>
          <span>Client bank</span>
          <select className="input" value={bankId} onChange={(e) => setBankId(e.target.value)} disabled={busy}>
            {banks.length === 0 ? <option value="">No banks configured</option> : null}
            {banks.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        </label>
        <label className="stack" style={{ gap: 4 }}>
          <span>Import statement (CSV/OFX)</span>
          <input
            type="file"
            accept=".csv,.ofx,.qfx,text/csv"
            disabled={busy || !bankId}
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) void importFile(f)
              e.target.value = ''
            }}
          />
        </label>
      </div>

      <section className="stack" style={{ gap: 8 }}>
        <h3 style={{ margin: 0 }}>Match ledger transaction</h3>
        <p className="muted" style={{ margin: 0 }}>
          Choose the ledger entry that corresponds to a bank statement line, then click Match on that line.
        </p>
        <label className="stack" style={{ gap: 4, maxWidth: 720 }}>
          <span>Selected ledger entry</span>
          <select
            className="input"
            value={matchPairId}
            onChange={(e) => setMatchPairId(e.target.value)}
            disabled={busy}
          >
            <option value="">Select by date, matter, description and amount…</option>
            {unpresented.map((u) => (
              <option key={u.pair_id + u.posted_at} value={u.pair_id}>
                {formatLegLabel(u)}
              </option>
            ))}
          </select>
        </label>
        {selectedLeg ? (
          <div className="muted" style={{ fontSize: 13 }}>
            Selected: {formatLegLabel(selectedLeg)}
            {selectedLeg.reference ? ` · Ref ${selectedLeg.reference}` : ''}
          </div>
        ) : null}
      </section>

      <section className="stack" style={{ gap: 8 }}>
        <h3 style={{ margin: 0 }}>Statement lines</h3>
        <div className="ledgerTableWrap" style={{ flex: 'none', maxHeight: 360 }}>
          <table className="table reportsTable" style={{ minWidth: 640 }}>
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col">Description</th>
                <th scope="col" style={{ textAlign: 'right' }}>
                  Amount
                </th>
                <th scope="col">Status</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {lines.slice(0, 80).map((l) => (
                <tr key={l.id}>
                  <td>{l.statement_date}</td>
                  <td>{l.description}</td>
                  <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{pence(l.amount_pence)}</td>
                  <td>
                    {l.ignored
                      ? 'Ignored'
                      : l.matched_pair_id
                        ? 'Matched'
                        : 'Open'}
                  </td>
                  <td className="row" style={{ gap: 6 }}>
                    {!l.matched_pair_id && !l.ignored ? (
                      <button type="button" className="btn primary" disabled={busy} onClick={() => void matchLine(l.id)}>
                        Match
                      </button>
                    ) : null}
                    {l.matched_pair_id ? (
                      <button
                        type="button"
                        className="btn"
                        disabled={busy}
                        onClick={() =>
                          void apiFetch(`/accounts/banking/statements/lines/${l.id}/unmatch`, {
                            token,
                            method: 'POST',
                          }).then(load)
                        }
                      >
                        Unmatch
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
              {lines.length === 0 ? (
                <tr>
                  <td colSpan={5} className="muted">
                    No statement lines — import a CSV/OFX.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="stack" style={{ gap: 8 }}>
        <h3 style={{ margin: 0 }}>Unpresented ledger</h3>
        <div className="ledgerTableWrap" style={{ flex: 'none', maxHeight: 320 }}>
          <table className="table reportsTable" style={{ minWidth: 640 }}>
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col">Matter</th>
                <th scope="col">Description</th>
                <th scope="col" style={{ textAlign: 'right' }}>
                  Amount
                </th>
                <th scope="col">Select</th>
              </tr>
            </thead>
            <tbody>
              {unpresented.slice(0, 40).map((u) => (
                <tr key={u.pair_id + u.posted_at} className={matchPairId === u.pair_id ? 'active' : undefined}>
                  <td>{u.posted_at.slice(0, 10)}</td>
                  <td>{u.case_number || u.case_id.slice(0, 8)}</td>
                  <td>{u.description}</td>
                  <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                    {u.direction === 'debit' ? '-' : '+'}
                    {pence(u.amount_pence)}
                  </td>
                  <td>
                    <button
                      type="button"
                      className={`btn${matchPairId === u.pair_id ? ' primary' : ''}`}
                      onClick={() => setMatchPairId(u.pair_id)}
                    >
                      {matchPairId === u.pair_id ? 'Selected' : 'Select'}
                    </button>
                  </td>
                </tr>
              ))}
              {unpresented.length === 0 ? (
                <tr>
                  <td colSpan={5} className="muted">
                    None
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="stack" style={{ gap: 8 }}>
        <h3 style={{ margin: 0 }}>Line reconciliation &amp; EOM</h3>
        <div className="row" style={{ gap: 12, flexWrap: 'wrap', alignItems: 'end' }}>
          <label className="stack" style={{ gap: 4 }}>
            <span>Period end</span>
            <input type="date" className="input" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />
          </label>
          <label className="stack" style={{ gap: 4 }}>
            <span>Statement balance (£)</span>
            <input className="input" value={bankPounds} onChange={(e) => setBankPounds(e.target.value)} />
          </label>
          <button type="button" className="btn primary" disabled={busy || !bankId} onClick={() => void createRecon()}>
            Save recon draft
          </button>
          <button type="button" className="btn" disabled={busy || !bankId} onClick={() => void runEom()}>
            Generate EOM pack
          </button>
        </div>
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {recons.map((r) => (
            <li key={r.id}>
              {r.period_end_date} — {r.status} — diff {pence(r.difference_pence)}{' '}
              {r.status === 'draft' ? (
                <button type="button" className="btn" disabled={busy} onClick={() => void approveRecon(r.id)}>
                  Approve
                </button>
              ) : null}
            </li>
          ))}
        </ul>
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {eoms.map((e) => (
            <li key={e.id}>
              {e.period_end_date} — {e.filename}{' '}
              <button type="button" className="btn" onClick={() => void downloadEom(e.id, e.filename)}>
                Download
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="stack" style={{ gap: 8 }}>
        <h3 style={{ margin: 0 }}>Inter-matter client journal</h3>
        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
          <input
            className="input"
            placeholder="From case id"
            value={journalFrom}
            onChange={(e) => setJournalFrom(e.target.value)}
          />
          <input
            className="input"
            placeholder="To case id"
            value={journalTo}
            onChange={(e) => setJournalTo(e.target.value)}
          />
          <input
            className="input"
            placeholder="Amount £"
            value={journalAmt}
            onChange={(e) => setJournalAmt(e.target.value)}
          />
          <input
            className="input"
            placeholder="Description"
            value={journalDesc}
            onChange={(e) => setJournalDesc(e.target.value)}
          />
          <button type="button" className="btn primary" disabled={busy} onClick={() => void createJournal()}>
            Post journal
          </button>
        </div>
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {journals.slice(0, 20).map((j) => (
            <li key={j.id}>
              {pence(j.amount_pence)} — {j.description} ({j.from_case_id.slice(0, 8)} → {j.to_case_id.slice(0, 8)})
            </li>
          ))}
        </ul>
      </section>

      <section className="stack" style={{ gap: 8 }}>
        <h3 style={{ margin: 0 }}>Xero journal export</h3>
        <p className="muted" style={{ margin: 0 }}>
          Exports office ledger activity as a CSV for manual import into Xero (nominal codes below).
        </p>
        {xero ? (
          <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
            <input
              className="input"
              placeholder="Income code"
              value={xero.office_income_code || ''}
              onChange={(e) => setXero({ ...xero, office_income_code: e.target.value })}
            />
            <input
              className="input"
              placeholder="Bank code"
              value={xero.office_bank_code || ''}
              onChange={(e) => setXero({ ...xero, office_bank_code: e.target.value })}
            />
            <input
              className="input"
              placeholder="VAT code"
              value={xero.vat_code || ''}
              onChange={(e) => setXero({ ...xero, vat_code: e.target.value })}
            />
            <button type="button" className="btn" disabled={busy} onClick={() => void saveXero()}>
              Save codes
            </button>
          </div>
        ) : null}
        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
          <input type="date" className="input" value={xeroFrom} onChange={(e) => setXeroFrom(e.target.value)} />
          <input type="date" className="input" value={xeroTo} onChange={(e) => setXeroTo(e.target.value)} />
          <button type="button" className="btn primary" disabled={busy} onClick={() => void runXeroExport()}>
            Generate CSV
          </button>
        </div>
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {exports.map((x) => (
            <li key={x.id}>
              {x.period_from} → {x.period_to} ({x.row_count} rows){' '}
              <button type="button" className="btn" onClick={() => void downloadXero(x.id, x.filename)}>
                Download
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
