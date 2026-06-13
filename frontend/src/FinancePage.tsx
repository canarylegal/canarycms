import { useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch } from './api'
import { canaryDocumentTitle } from './tabTitle'
import type { ApiError } from './api'
import { useDialogs } from './DialogProvider'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import type { CaseOut, FinanceCategoryOut, FinanceItemOut, FinanceOut } from './types'
import { openOnlyOfficeCaseEditor } from './onlyofficeEditorWindow'

const FIN_DIRECTION_OPTIONS = [
  { value: 'debit', label: 'Debit' },
  { value: 'credit', label: 'Credit' },
] as const

interface Props {
  caseId: string
  token: string
  /** When provided (modal mode): renders Save and Close / Discard buttons in a header. */
  onClose?: () => void
  /** In the case documents panel: show full-page totals and no duplicate modal title bar. */
  embedded?: boolean
}

type ItemDraft = { name: string; direction: 'debit' | 'credit'; amountStr: string; vatStr: string }

function pence(p: number): string {
  return `£${(p / 100).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function FinancePage({ caseId, token, onClose, embedded = false }: Props) {
  const { askConfirm, alert } = useDialogs()
  const [finance, setFinance] = useState<FinanceOut | null>(null)
  const [drafts, setDrafts] = useState<Record<string, ItemDraft>>({})
  const [catDrafts, setCatDrafts] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [genBusy, setGenBusy] = useState(false)

  // Add item form state per category
  const [addItemCatId, setAddItemCatId] = useState<string | null>(null)
  const [addItemName, setAddItemName] = useState('')
  const [addItemDir, setAddItemDir] = useState<'debit' | 'credit'>('debit')

  // Add category form
  const [addCatOpen, setAddCatOpen] = useState(false)
  const [addCatName, setAddCatName] = useState('')
  const addCatRef = useRef<HTMLInputElement>(null)

  function initDrafts(data: FinanceOut) {
    const d: Record<string, ItemDraft> = {}
    const c: Record<string, string> = {}
    for (const cat of data.categories) {
      c[cat.id] = cat.name
      for (const item of cat.items) {
        d[item.id] = {
          name: item.name,
          direction: cat.credit_only ? 'credit' : item.direction,
          amountStr: item.amount_pence != null ? (item.amount_pence / 100).toFixed(2) : '',
          vatStr: item.vat_pence != null ? (item.vat_pence / 100).toFixed(2) : '',
        }
      }
    }
    setDrafts(d)
    setCatDrafts(c)
  }

  const financeUsesPreset = useMemo(
    () =>
      Boolean(
        finance?.has_finance_preset || finance?.categories.some((c) => c.template_category_id),
      ),
    [finance],
  )
  const showApplyQuote = Boolean(finance?.has_quote_snapshot && financeUsesPreset)

  async function load() {
    setBusy(true); setError(null)
    try {
      const data = await apiFetch<FinanceOut>(`/cases/${caseId}/finance`, { token })
      setFinance(data)
      initDrafts(data)
    } catch (e) {
      setError((e as ApiError).message ?? 'Failed to load finance')
    } finally { setBusy(false) }
  }

  async function applyQuote() {
    if (!finance?.has_quote_snapshot) return
    const ok = await askConfirm({
      title: 'Apply quote',
      message:
        'Apply amounts from the most recent quote to this finance sheet? Existing line amounts with matching names will be overwritten.',
      confirmLabel: 'Apply quote',
    })
    if (!ok) return
    setBusy(true)
    setError(null)
    try {
      const data = await apiFetch<FinanceOut>(`/cases/${caseId}/finance/apply-quote`, { token, method: 'POST' })
      setFinance(data)
      initDrafts(data)
      await alert('Quote amounts applied to the finance sheet.', 'Apply quote')
    } catch (e) {
      setError((e as ApiError).message ?? 'Failed to apply quote')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => { void load() }, [caseId])

  useEffect(() => {
    if (addCatOpen) setTimeout(() => addCatRef.current?.focus(), 50)
  }, [addCatOpen])

  // ── Draft helpers ─────────────────────────────────────────────────────────

  function setDraft(itemId: string, patch: Partial<ItemDraft>) {
    setDrafts((prev) => ({ ...prev, [itemId]: { ...prev[itemId], ...patch } }))
  }

  function setCatDraft(catId: string, name: string) {
    setCatDrafts((prev) => ({ ...prev, [catId]: name }))
  }

  async function saveCategoryName(catId: string) {
    if (!finance) return
    const cat = finance.categories.find((c) => c.id === catId)
    const trimmed = (catDrafts[catId] ?? cat?.name ?? '').trim()
    if (!cat || !trimmed || cat.name === trimmed) {
      if (cat && trimmed !== catDrafts[catId]) setCatDraft(catId, cat.name)
      return
    }
    try {
      await apiFetch(`/cases/${caseId}/finance/categories/${catId}`, {
        token,
        method: 'PATCH',
        json: { name: trimmed },
      })
      setFinance((prev) =>
        prev
          ? {
              ...prev,
              categories: prev.categories.map((c) => (c.id === catId ? { ...c, name: trimmed } : c)),
            }
          : prev,
      )
      setCatDraft(catId, trimmed)
    } catch (e) {
      setError((e as ApiError).message ?? 'Failed to save category name')
      setCatDraft(catId, cat.name)
    }
  }

  async function savePendingChanges() {
    if (!finance) return
    for (const cat of finance.categories) {
      const catName = (catDrafts[cat.id] ?? cat.name).trim()
      if (catName && catName !== cat.name) {
        await apiFetch(`/cases/${caseId}/finance/categories/${cat.id}`, {
          token,
          method: 'PATCH',
          json: { name: catName },
        })
      }
      for (const item of cat.items) {
        const d = drafts[item.id]
        if (!d) continue
        const amtPence = d.amountStr.trim() ? Math.round(parseFloat(d.amountStr) * 100) : null
        const vatPence = d.vatStr.trim() ? Math.round(parseFloat(d.vatStr) * 100) : null
        const nameChanged = d.name !== item.name
        const dirChanged = !cat.credit_only && d.direction !== item.direction
        const amtChanged = amtPence !== item.amount_pence
        const vatChanged = vatPence !== (item.vat_pence ?? null)
        if (nameChanged || dirChanged || amtChanged || vatChanged) {
          await apiFetch(`/cases/${caseId}/finance/items/${item.id}`, {
            token, method: 'PATCH',
            json: {
              name: d.name || item.name,
              direction: cat.credit_only ? 'credit' : d.direction,
              amount_pence: amtPence,
              vat_pence: vatPence,
            },
          })
        }
      }
    }
  }

  // ── Save all ──────────────────────────────────────────────────────────────

  async function saveAll() {
    if (!finance) { onClose?.(); return }
    setBusy(true); setError(null)
    try {
      await savePendingChanges()
      onClose?.()
    } catch (e) {
      setError((e as ApiError).message ?? 'Failed to save')
      setBusy(false)
    }
  }

  function discardChanges() {
    if (finance) initDrafts(finance)
    onClose?.()
  }

  async function generateCompletionStatement() {
    if (!finance) return
    setGenBusy(true); setError(null)
    try {
      await savePendingChanges()
      const res = await apiFetch<{ id: string }>(`/cases/${caseId}/finance/completion-statement`, {
        token, method: 'POST',
      })
      openOnlyOfficeCaseEditor(caseId, res.id)
    } catch (e: any) {
      setError(e?.message ?? 'Failed to generate completion statement')
    } finally {
      setGenBusy(false)
    }
  }

  // ── Structural mutations (immediate) ─────────────────────────────────────

  async function deleteItem(itemId: string) {
    const ok = await askConfirm({
      title: 'Remove item',
      message: 'Remove this item?',
      danger: true,
      confirmLabel: 'Remove',
    })
    if (!ok) return
    setBusy(true)
    try {
      await apiFetch(`/cases/${caseId}/finance/items/${itemId}`, { token, method: 'DELETE' })
      await load()
    } catch (e) { setError((e as ApiError).message ?? 'Failed') } finally { setBusy(false) }
  }

  async function addItem(catId: string) {
    if (!addItemName.trim()) return
    const cat = finance?.categories.find((c) => c.id === catId)
    setBusy(true)
    try {
      const order = cat?.items.length ?? 0
      await apiFetch(`/cases/${caseId}/finance/items`, {
        token, method: 'POST',
        json: {
          category_id: catId,
          name: addItemName.trim(),
          direction: cat?.credit_only ? 'credit' : addItemDir,
          sort_order: order,
        },
      })
      setAddItemCatId(null); setAddItemName(''); setAddItemDir('debit')
      await load()
    } catch (e) { setError((e as ApiError).message ?? 'Failed') } finally { setBusy(false) }
  }

  async function addCategory() {
    if (!addCatName.trim()) return
    setBusy(true)
    try {
      const order = finance?.categories.length ?? 0
      await apiFetch(`/cases/${caseId}/finance/categories`, {
        token, method: 'POST',
        json: { name: addCatName.trim(), sort_order: order },
      })
      setAddCatOpen(false); setAddCatName('')
      await load()
    } catch (e) { setError((e as ApiError).message ?? 'Failed') } finally { setBusy(false) }
  }

  async function deleteCategory(catId: string) {
    const ok = await askConfirm({
      title: 'Delete category',
      message: 'Delete this category and all its items?',
      danger: true,
      confirmLabel: 'Delete',
    })
    if (!ok) return
    setBusy(true)
    try {
      await apiFetch(`/cases/${caseId}/finance/categories/${catId}`, { token, method: 'DELETE' })
      await load()
    } catch (e) { setError((e as ApiError).message ?? 'Failed') } finally { setBusy(false) }
  }

  // ── Derived totals ────────────────────────────────────────────────────────

  const allItems = finance?.categories.flatMap((c) => c.items) ?? []
  function itemLineTotal(i: FinanceItemOut): number {
    const d = drafts[i.id]
    const amt = d
      ? d.amountStr.trim()
        ? Math.round(parseFloat(d.amountStr) * 100)
        : null
      : i.amount_pence
    const vat = d
      ? d.vatStr.trim()
        ? Math.round(parseFloat(d.vatStr) * 100)
        : null
      : i.vat_pence ?? null
    if (amt == null || isNaN(amt)) return 0
    const v = vat != null && !isNaN(vat) ? vat : 0
    return amt + v
  }

  const grandDr = allItems.reduce((s, i) => {
    const dir = drafts[i.id]?.direction ?? i.direction
    return dir === 'debit' ? s + itemLineTotal(i) : s
  }, 0)
  const grandCr = allItems.reduce((s, i) => {
    const dir = drafts[i.id]?.direction ?? i.direction
    return dir === 'credit' ? s + itemLineTotal(i) : s
  }, 0)
  const balance = grandCr - grandDr

  const showModalTitleBar = Boolean(onClose && !embedded)
  const showTotals = !onClose || embedded

  return (
    <div className="finShell">
      {showModalTitleBar ? (
        <div className="paneHead" style={{ marginBottom: 12 }}>
          <h2 style={{ margin: 0, fontSize: 18 }}>Finance</h2>
          <div className="row" style={{ gap: 8 }}>
            <button type="button" className="btn" disabled={busy} onClick={discardChanges}>
              Discard changes
            </button>
            <button
              type="button"
              className="btn"
              style={{ background: 'var(--primary)', color: '#fff', borderColor: 'var(--primary)' }}
              disabled={busy}
              onClick={() => void saveAll()}
            >
              Save and close
            </button>
          </div>
        </div>
      ) : null}

      {embedded && onClose ? (
        <div className="row" style={{ justifyContent: 'flex-end', flexWrap: 'wrap', gap: 8, marginBottom: 4 }}>
          <button type="button" className="btn" disabled={busy} onClick={discardChanges}>
            Discard changes
          </button>
          <button
            type="button"
            className="btn"
            style={{ background: 'var(--primary)', color: '#fff', borderColor: 'var(--primary)' }}
            disabled={busy}
            onClick={() => void saveAll()}
          >
            Save and close
          </button>
        </div>
      ) : null}

      {/* Totals + utility buttons */}
      <div className="finHeader">
        {showTotals ? (
          <div className="finTotals">
            <div className="finTotalCard">
              <span className="finTotalLabel">Total debits</span>
              <span className="finTotalValue finTotalDr">{pence(grandDr)}</span>
            </div>
            <div className="finTotalCard">
              <span className="finTotalLabel">Total credits</span>
              <span className="finTotalValue finTotalCr">{pence(grandCr)}</span>
            </div>
            <div className="finTotalCard">
              <span className="finTotalLabel">Balance</span>
              <span className={`finTotalValue${balance < 0 ? ' finTotalDr' : ' finTotalCr'}`}>
                {balance === 0 ? '£0.00' : `${pence(Math.abs(balance))}${balance > 0 ? ' CR' : ''}`}
              </span>
            </div>
          </div>
        ) : null}
        <div
          className={`finActions${showModalTitleBar ? ' finActions--modalToolbar' : ''}`}
          style={{ flexWrap: 'wrap', gap: 8 }}
        >
          <button type="button" className="btn" disabled={busy || genBusy} onClick={() => void load()}>Refresh</button>
          {showApplyQuote ? (
            <button
              type="button"
              className="btn"
              disabled={busy || genBusy}
              onClick={() => void applyQuote()}
              title="Fill finance line amounts from the most recent quote on this case"
            >
              Apply quote
            </button>
          ) : null}
          <button type="button" className="btn finAddCatBtn" disabled={busy || genBusy} onClick={() => setAddCatOpen(true)}>
            + Category
          </button>
          <button
            type="button"
            className="btn"
            style={{ background: 'var(--primary)', color: '#fff', borderColor: 'var(--primary)' }}
            disabled={busy || genBusy || !finance}
            onClick={() => void generateCompletionStatement()}
            title="Save current values and generate a completion statement in Word format"
          >
            {genBusy ? 'Generating…' : 'Generate completion statement'}
          </button>
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      {finance && financeUsesPreset && !finance.has_quote_snapshot ? (
        <div className="muted" style={{ marginBottom: 8 }}>
          Create a quote on this case to enable Apply quote.
        </div>
      ) : null}

      {!finance && busy && <div className="empty">Loading…</div>}

      {finance && finance.categories.length === 0 && (
        <div className="empty">No finance items yet. Add a category to get started.</div>
      )}

      {finance && finance.categories.map((cat: FinanceCategoryOut) => (
          <div key={cat.id} className="finCategoryBlock">
            <div className="finCategoryHead">
              <input
                className="input finCategoryNameInput"
                value={catDrafts[cat.id] ?? cat.name}
                onChange={(e) => setCatDraft(cat.id, e.target.value)}
                onBlur={() => void saveCategoryName(cat.id)}
                disabled={busy}
                aria-label="Category name"
              />
              <button
                type="button"
                className="btn finCatDeleteBtn"
                disabled={busy}
                onClick={() => void deleteCategory(cat.id)}
                title="Delete category"
              >
                ✕
              </button>
            </div>

            <table className="finTable">
              <thead>
                <tr>
                  <th style={{ width: 100 }}>Type</th>
                  <th>Description</th>
                  <th className="finAmtCell">Amount</th>
                  <th className="finAmtCell">VAT</th>
                  <th className="finActCell" />
                </tr>
              </thead>
              <tbody>
                {cat.items.map((item: FinanceItemOut) => {
                  const d = drafts[item.id] ?? {
                    name: item.name,
                    direction: item.direction,
                    amountStr: '',
                    vatStr: '',
                  }
                  return (
                    <tr key={item.id} className="finRow">
                      <td>
                        {cat.credit_only ? (
                          <span className="finDirBadge finDirBadge--credit">Credit</span>
                        ) : (
                          <div className="finDirSelect">
                            <SingleSelectDropdown
                              hideLabel
                              label="Direction"
                              options={[...FIN_DIRECTION_OPTIONS]}
                              value={d.direction}
                              onChange={(v) => setDraft(item.id, { direction: v as 'debit' | 'credit' })}
                              disabled={busy}
                            />
                          </div>
                        )}
                      </td>
                      <td>
                        <input
                          className="input"
                          style={{ width: '100%' }}
                          value={d.name}
                          onChange={(e) => setDraft(item.id, { name: e.target.value })}
                          disabled={busy}
                        />
                      </td>
                      <td className="finAmtCell">
                        <input
                          className="input"
                          type="number"
                          min="0"
                          step="0.01"
                          placeholder="0.00"
                          style={{ width: 110, textAlign: 'right' }}
                          value={d.amountStr}
                          onChange={(e) => setDraft(item.id, { amountStr: e.target.value })}
                          disabled={busy}
                        />
                      </td>
                      <td className="finAmtCell">
                        <input
                          className="input"
                          type="number"
                          min="0"
                          step="0.01"
                          placeholder="—"
                          style={{ width: 110, textAlign: 'right' }}
                          value={d.vatStr}
                          onChange={(e) => setDraft(item.id, { vatStr: e.target.value })}
                          disabled={busy || cat.credit_only}
                        />
                      </td>
                      <td className="finActCell">
                        <button
                          type="button"
                          className="btn danger finRowBtn"
                          onClick={() => void deleteItem(item.id)}
                          disabled={busy}
                          title="Remove item"
                        >
                          ✕
                        </button>
                      </td>
                    </tr>
                  )
                })}
                {cat.items.length === 0 && (
                  <tr><td colSpan={5} className="muted" style={{ padding: '8px 10px', fontStyle: 'italic' }}>No items.</td></tr>
                )}
              </tbody>
            </table>

            {/* Add item row */}
            {addItemCatId === cat.id ? (
              <div className="finAddItemRow">
                {cat.credit_only ? (
                  <span className="finDirBadge finDirBadge--credit">Credit</span>
                ) : (
                  <div className="finDirSelect">
                    <SingleSelectDropdown
                      hideLabel
                      label="Direction"
                      options={[...FIN_DIRECTION_OPTIONS]}
                      value={addItemDir}
                      onChange={(v) => setAddItemDir(v as 'debit' | 'credit')}
                      disabled={busy}
                    />
                  </div>
                )}
                <input
                  className="input"
                  style={{ flex: 1 }}
                  placeholder="Item description…"
                  value={addItemName}
                  autoFocus
                  onChange={(e) => setAddItemName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void addItem(cat.id)
                    if (e.key === 'Escape') { setAddItemCatId(null); setAddItemName('') }
                  }}
                  disabled={busy}
                />
                <button
                  className="btn"
                  style={{ background: 'var(--primary)', color: '#fff', borderColor: 'var(--primary)' }}
                  disabled={busy || !addItemName.trim()}
                  onClick={() => void addItem(cat.id)}
                >
                  Add
                </button>
                <button className="btn" disabled={busy} onClick={() => { setAddItemCatId(null); setAddItemName('') }}>
                  Cancel
                </button>
              </div>
            ) : (
              <button
                type="button"
                className="btn finAddItemBtn"
                disabled={busy}
                onClick={() => {
                  setAddItemCatId(cat.id)
                  setAddItemName('')
                  setAddItemDir(cat.credit_only ? 'credit' : 'debit')
                }}
              >
                + Add item
              </button>
            )}
          </div>
      ))}

      {/* Add category form */}
      {addCatOpen && (
        <div className="finAddCatRow">
          <input
            ref={addCatRef}
            className="input"
            style={{ flex: 1, maxWidth: 320 }}
            placeholder="New category name…"
            value={addCatName}
            onChange={(e) => setAddCatName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void addCategory()
              if (e.key === 'Escape') { setAddCatOpen(false); setAddCatName('') }
            }}
            disabled={busy}
          />
          <button
            className="btn"
            style={{ background: 'var(--primary)', color: '#fff', borderColor: 'var(--primary)' }}
            disabled={busy || !addCatName.trim()}
            onClick={() => void addCategory()}
          >
            Add category
          </button>
          <button className="btn" disabled={busy} onClick={() => { setAddCatOpen(false); setAddCatName('') }}>
            Cancel
          </button>
        </div>
      )}
    </div>
  )
}

/**
 * Standalone wrapper rendered when the app opens with ?finance=<caseId>.
 */
export function FinanceStandalone({ caseId, token }: { caseId: string; token: string }) {
  const [caseRef, setCaseRef] = useState<string | null>(null)

  useEffect(() => {
    apiFetch<CaseOut>(`/cases/${caseId}`, { token })
      .then((c) => {
        const label = [c.case_number, c.client_name].filter(Boolean).join(' — ')
        setCaseRef(label || caseId)
        document.title = canaryDocumentTitle(`Finance — ${label || caseId}`)
      })
      .catch(() => {
        document.title = canaryDocumentTitle('Finance')
      })
  }, [caseId, token])

  return (
    <div className="ledgerStandaloneShell">
      <div className="ledgerStandaloneBar">
        <span className="ledgerStandaloneLogo">Canary</span>
        {caseRef && <span className="ledgerStandaloneCase">{caseRef}</span>}
        <span className="ledgerStandaloneTitle">Finance</span>
      </div>
      <div className="ledgerStandaloneBody">
        <FinancePage caseId={caseId} token={token} />
      </div>
    </div>
  )
}
