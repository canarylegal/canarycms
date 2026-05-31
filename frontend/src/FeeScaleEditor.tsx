import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from './api'
import { useDialogs } from './DialogProvider'
import { FeeScaleBandRowModal } from './FeeScaleBandRowModal'
import { TextPromptModal } from './TextPromptModal'
import type {
  FeeScaleAmountKind,
  FeeScaleBandRowOut,
  FeeScaleBandSetOut,
  FeeScaleCategoryOut,
  FeeScaleDetailOut,
  FeeScaleLineKind,
  FeeScaleLineOut,
} from './types'

const SMALL: React.CSSProperties = { padding: '3px 8px', fontSize: '0.82em' }

const LINE_KINDS: { value: FeeScaleLineKind; label: string }[] = [
  { value: 'section_header', label: 'Section header' },
  { value: 'item', label: 'Line item' },
  { value: 'vat', label: 'VAT (calculated)' },
  { value: 'subtotal', label: 'Subtotal (calculated)' },
  { value: 'total', label: 'Grand total (calculated)' },
]

const AMOUNT_KINDS: { value: FeeScaleAmountKind; label: string }[] = [
  { value: 'fixed', label: 'Fixed amount' },
  { value: 'editable', label: 'Editable at quote' },
  { value: 'band', label: 'From value band' },
]

export function poundsToPence(input: string): number | null {
  const t = input.trim().replace(/,/g, '')
  if (!t) return null
  const n = Number(t)
  if (!Number.isFinite(n)) return null
  return Math.round(n * 100)
}

export function penceToPounds(pence: number | null | undefined): string {
  if (pence == null) return ''
  return (pence / 100).toFixed(2)
}

type Props = {
  token: string
  scaleId: string
  setupMode?: boolean
  onBack: () => void
}

type EditorModal =
  | { kind: 'category' }
  | { kind: 'line'; category: FeeScaleCategoryOut }
  | { kind: 'bandSet' }
  | { kind: 'bandRow'; bandSet: FeeScaleBandSetOut }
  | null

export function FeeScaleEditor({ token, scaleId, setupMode, onBack }: Props) {
  const { askConfirm } = useDialogs()
  const [detail, setDetail] = useState<FeeScaleDetailOut | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [vatPct, setVatPct] = useState('20')
  const [modal, setModal] = useState<EditorModal>(null)

  const load = useCallback(async () => {
    setBusy(true)
    setErr(null)
    try {
      const data = await apiFetch<FeeScaleDetailOut>(`/fee-scales/${scaleId}`, { token })
      setDetail(data)
      setVatPct(String((data.vat_rate_bps ?? 2000) / 100))
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not load fee scale')
    } finally {
      setBusy(false)
    }
  }, [scaleId, token])

  useEffect(() => {
    void load()
  }, [load])

  const bandSetOptions = useMemo(
    () => (detail?.band_sets ?? []).map((b) => ({ id: b.id, label: b.name })),
    [detail?.band_sets],
  )

  async function saveVatIfDirty() {
    if (!detail) return
    const bps = Math.round(Number(vatPct) * 100)
    if (!Number.isFinite(bps) || bps < 0) return
    if (bps === (detail.vat_rate_bps ?? 2000)) return
    await apiFetch(`/fee-scales/${detail.id}`, { token, method: 'PATCH', json: { vat_rate_bps: bps } })
    await load()
  }

  async function saveVat() {
    if (!detail) return
    const bps = Math.round(Number(vatPct) * 100)
    if (!Number.isFinite(bps) || bps < 0) return
    setBusy(true)
    try {
      await apiFetch(`/fee-scales/${detail.id}`, { token, method: 'PATCH', json: { vat_rate_bps: bps } })
      await load()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  function hasQuoteLines(d: FeeScaleDetailOut) {
    return d.categories.some((c) => c.lines.length > 0)
  }

  async function saveAndClose() {
    if (!detail) return
    if (setupMode && !hasQuoteLines(detail)) {
      const ok = await askConfirm({
        title: 'Finish setup?',
        message:
          'This fee scale has no quote lines yet. You can add categories and lines later from Fee scales → Edit.',
        confirmLabel: 'Finish anyway',
      })
      if (!ok) return
    }
    setBusy(true)
    setErr(null)
    try {
      await saveVatIfDirty()
      onBack()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  async function handleBack() {
    if (setupMode && detail && !hasQuoteLines(detail)) {
      const ok = await askConfirm({
        title: 'Leave setup?',
        message: 'You have not added any quote lines yet. Leave anyway?',
        confirmLabel: 'Leave',
      })
      if (!ok) return
    }
    onBack()
  }

  async function submitCategory(name: string) {
    if (!detail) return
    setBusy(true)
    try {
      await apiFetch('/fee-scales/categories', {
        token,
        method: 'POST',
        json: { fee_scale_id: detail.id, name: name.trim(), sort_order: detail.categories.length },
      })
      setModal(null)
      await load()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not add category')
    } finally {
      setBusy(false)
    }
  }

  async function submitLine(category: FeeScaleCategoryOut, name: string) {
    setBusy(true)
    try {
      await apiFetch('/fee-scales/lines', {
        token,
        method: 'POST',
        json: {
          category_id: category.id,
          name: name.trim(),
          line_kind: 'item',
          amount_kind: 'fixed',
          default_amount_pence: 0,
          sort_order: category.lines.length,
        },
      })
      setModal(null)
      await load()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not add line')
    } finally {
      setBusy(false)
    }
  }

  async function submitBandSet(name: string) {
    if (!detail) return
    setBusy(true)
    try {
      await apiFetch('/fee-scales/band-sets', {
        token,
        method: 'POST',
        json: { fee_scale_id: detail.id, name: name.trim(), sort_order: detail.band_sets.length },
      })
      setModal(null)
      await load()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not add band set')
    } finally {
      setBusy(false)
    }
  }

  async function submitBandRow(
    set: FeeScaleBandSetOut,
    values: { min_value_pence: number; max_value_pence: number | null; amount_pence: number },
  ) {
    setBusy(true)
    try {
      await apiFetch('/fee-scales/band-rows', {
        token,
        method: 'POST',
        json: {
          band_set_id: set.id,
          min_value_pence: values.min_value_pence,
          max_value_pence: values.max_value_pence,
          amount_pence: values.amount_pence,
          sort_order: set.rows.length,
        },
      })
      setModal(null)
      await load()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not add band row')
    } finally {
      setBusy(false)
    }
  }

  async function updateLine(line: FeeScaleLineOut, patch: Record<string, unknown>) {
    setBusy(true)
    try {
      await apiFetch(`/fee-scales/lines/${line.id}`, { token, method: 'PATCH', json: patch })
      await load()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not update line')
    } finally {
      setBusy(false)
    }
  }

  async function deleteLine(lineId: string) {
    const ok = await askConfirm({ title: 'Delete line', message: 'Remove this line?', danger: true, confirmLabel: 'Delete' })
    if (!ok) return
    setBusy(true)
    try {
      await apiFetch(`/fee-scales/lines/${lineId}`, { token, method: 'DELETE' })
      await load()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Delete failed')
    } finally {
      setBusy(false)
    }
  }

  async function updateBandRow(row: FeeScaleBandRowOut, patch: Record<string, unknown>) {
    setBusy(true)
    try {
      await apiFetch(`/fee-scales/band-rows/${row.id}`, { token, method: 'PATCH', json: patch })
      await load()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not update band')
    } finally {
      setBusy(false)
    }
  }

  async function deleteBandRow(rowId: string) {
    const ok = await askConfirm({ title: 'Delete band', message: 'Remove this band row?', danger: true, confirmLabel: 'Delete' })
    if (!ok) return
    setBusy(true)
    try {
      await apiFetch(`/fee-scales/band-rows/${rowId}`, { token, method: 'DELETE' })
      await load()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Delete failed')
    } finally {
      setBusy(false)
    }
  }

  async function addBandSet() {
    if (!detail) return
    setModal({ kind: 'bandSet' })
  }

  async function addBandRow(set: FeeScaleBandSetOut) {
    setModal({ kind: 'bandRow', bandSet: set })
  }

  if (!detail && busy) return <div className="muted">Loading…</div>
  if (!detail) return <div className="error">{err ?? 'Not found'}</div>

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
        <div>
          <button type="button" className="btn" disabled={busy} onClick={() => void handleBack()}>
            ← Fee scales
          </button>
          <h3 style={{ margin: '8px 0 0' }}>{detail.name}</h3>
          <div className="muted" style={{ fontSize: 12 }}>
            {detail.reference} · {detail.scope_summary}
          </div>
        </div>
        <div className="row" style={{ gap: 8, flexShrink: 0 }}>
          <button type="button" className="btn" disabled={busy} onClick={() => void load()}>
            Refresh
          </button>
          <button type="button" className="btn primary" disabled={busy} onClick={() => void saveAndClose()}>
            {setupMode ? 'Save & finish setup' : 'Save & close'}
          </button>
        </div>
      </div>

      {setupMode ? (
        <div className="card" style={{ padding: 12, borderLeft: '3px solid var(--accent)' }}>
          <strong>Set up your fee scale</strong>
          <p className="muted" style={{ margin: '6px 0 0', fontSize: 13 }}>
            Add at least one category with quote lines. Optionally configure value bands for tiered fees, then click{' '}
            <strong>Save &amp; finish setup</strong> when done. Return here later from Fee scales → Edit to make changes.
          </p>
        </div>
      ) : null}

      {err ? <div className="error">{err}</div> : null}

      {modal?.kind === 'category' ? (
        <TextPromptModal
          title="Add category"
          hint="Categories group related quote lines (e.g. Our Fees, Disbursements)."
          fieldLabel="Category name"
          initial=""
          confirmLabel="Add category"
          busy={busy}
          onCancel={() => setModal(null)}
          onConfirm={(name) => {
            if (name.trim()) void submitCategory(name)
          }}
        />
      ) : null}

      {modal?.kind === 'line' ? (
        <TextPromptModal
          title="Add line"
          fieldLabel="Line label"
          initial=""
          confirmLabel="Add line"
          busy={busy}
          onCancel={() => setModal(null)}
          onConfirm={(name) => {
            if (name.trim()) void submitLine(modal.category, name)
          }}
        />
      ) : null}

      {modal?.kind === 'bandSet' ? (
        <TextPromptModal
          title="Add band set"
          hint="Band sets map property values to fee amounts for line items using “From value band”."
          fieldLabel="Band set name"
          initial=""
          confirmLabel="Add band set"
          busy={busy}
          onCancel={() => setModal(null)}
          onConfirm={(name) => {
            if (name.trim()) void submitBandSet(name)
          }}
        />
      ) : null}

      {modal?.kind === 'bandRow' ? (
        <FeeScaleBandRowModal
          bandSetName={modal.bandSet.name}
          busy={busy}
          onCancel={() => setModal(null)}
          onConfirm={(values) => void submitBandRow(modal.bandSet, values)}
        />
      ) : null}

      <div className="card stack" style={{ padding: 12 }}>
        <h4 style={{ margin: 0 }}>VAT rate</h4>
        <div className="row" style={{ gap: 8, alignItems: 'center' }}>
          <input className="input" style={{ width: 80 }} value={vatPct} onChange={(e) => setVatPct(e.target.value)} />
          <span className="muted">%</span>
          <button type="button" className="btn" disabled={busy} onClick={() => void saveVat()}>
            Save
          </button>
        </div>
      </div>

      <div className="card stack" style={{ padding: 12 }}>
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <h4 style={{ margin: 0 }}>Value bands</h4>
          <button type="button" className="btn" style={SMALL} disabled={busy} onClick={() => void addBandSet()}>
            Add band set
          </button>
        </div>
        <p className="muted" style={{ margin: 0, fontSize: 12 }}>
          Used by line items with amount type “From value band”. Property value is entered when creating a quote.
        </p>
        {detail.band_sets.map((bs) => (
          <div key={bs.id} className="stack" style={{ gap: 6, marginTop: 8 }}>
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <strong>{bs.name}</strong>
              <button type="button" className="btn" style={SMALL} disabled={busy} onClick={() => void addBandRow(bs)}>
                Add band
              </button>
            </div>
            {bs.rows.length === 0 ? (
              <div className="muted" style={{ fontSize: 12 }}>No bands yet.</div>
            ) : (
              <table className="table" style={{ fontSize: 13 }}>
                <thead>
                  <tr>
                    <th>Min (£)</th>
                    <th>Max (£)</th>
                    <th>Fee (£)</th>
                    <th style={{ width: 48 }} />
                  </tr>
                </thead>
                <tbody>
                  {bs.rows.map((r: FeeScaleBandRowOut) => (
                    <BandRowEditor
                      key={r.id}
                      row={r}
                      busy={busy}
                      onUpdate={(patch) => void updateBandRow(r, patch)}
                      onDelete={() => void deleteBandRow(r.id)}
                    />
                  ))}
                </tbody>
              </table>
            )}
          </div>
        ))}
      </div>

      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h4 style={{ margin: 0 }}>Quote lines</h4>
        <button type="button" className="btn primary" style={SMALL} disabled={busy} onClick={() => setModal({ kind: 'category' })}>
          Add category
        </button>
      </div>

      {detail.categories.length === 0 ? (
        <div className="card muted" style={{ padding: 12, fontSize: 13 }}>
          {setupMode
            ? 'Start by adding a category (e.g. “Our Fees”), then add line items inside it.'
            : 'No categories yet — add one to define quote lines.'}
        </div>
      ) : null}

      {detail.categories.map((cat) => (
        <div key={cat.id} className="card stack" style={{ padding: 12, gap: 8 }}>
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <strong>{cat.name}</strong>
            <button type="button" className="btn" style={SMALL} disabled={busy} onClick={() => setModal({ kind: 'line', category: cat })}>
              Add line
            </button>
          </div>
          {cat.lines.length === 0 ? (
            <div className="muted" style={{ fontSize: 12 }}>
              No lines — add section headers, items, VAT, subtotals, and totals in order.
            </div>
          ) : (
            cat.lines.map((line) => (
              <LineEditor
                key={line.id}
                line={line}
                bandSetOptions={bandSetOptions}
                busy={busy}
                onUpdate={(patch) => void updateLine(line, patch)}
                onDelete={() => void deleteLine(line.id)}
              />
            ))
          )}
        </div>
      ))}
    </div>
  )
}

function BandRowEditor({
  row,
  busy,
  onUpdate,
  onDelete,
}: {
  row: FeeScaleBandRowOut
  busy: boolean
  onUpdate: (patch: Record<string, unknown>) => void
  onDelete: () => void
}) {
  const [minStr, setMinStr] = useState(penceToPounds(row.min_value_pence))
  const [maxStr, setMaxStr] = useState(row.max_value_pence != null ? penceToPounds(row.max_value_pence) : '')
  const [feeStr, setFeeStr] = useState(penceToPounds(row.amount_pence))

  useEffect(() => {
    setMinStr(penceToPounds(row.min_value_pence))
    setMaxStr(row.max_value_pence != null ? penceToPounds(row.max_value_pence) : '')
    setFeeStr(penceToPounds(row.amount_pence))
  }, [row.min_value_pence, row.max_value_pence, row.amount_pence])

  function saveField(field: 'min' | 'max' | 'fee') {
    if (field === 'min') {
      const p = poundsToPence(minStr)
      if (p != null) onUpdate({ min_value_pence: p })
    } else if (field === 'max') {
      const p = maxStr.trim() ? poundsToPence(maxStr) : null
      if (!maxStr.trim() || p != null) onUpdate({ max_value_pence: p })
    } else {
      const p = poundsToPence(feeStr)
      if (p != null) onUpdate({ amount_pence: p })
    }
  }

  return (
    <tr>
      <td>
        <input
          className="input"
          style={{ width: 90 }}
          value={minStr}
          disabled={busy}
          onChange={(e) => setMinStr(e.target.value)}
          onBlur={() => saveField('min')}
        />
      </td>
      <td>
        <input
          className="input"
          style={{ width: 90 }}
          value={maxStr}
          disabled={busy}
          placeholder="No max"
          onChange={(e) => setMaxStr(e.target.value)}
          onBlur={() => saveField('max')}
        />
      </td>
      <td>
        <input
          className="input"
          style={{ width: 90 }}
          value={feeStr}
          disabled={busy}
          onChange={(e) => setFeeStr(e.target.value)}
          onBlur={() => saveField('fee')}
        />
      </td>
      <td>
        <button type="button" className="btn danger" style={SMALL} disabled={busy} onClick={onDelete}>
          ✕
        </button>
      </td>
    </tr>
  )
}

function LineEditor({
  line,
  bandSetOptions,
  busy,
  onUpdate,
  onDelete,
}: {
  line: FeeScaleLineOut
  bandSetOptions: { id: string; label: string }[]
  busy: boolean
  onUpdate: (patch: Record<string, unknown>) => void
  onDelete: () => void
}) {
  const [amountStr, setAmountStr] = useState(penceToPounds(line.default_amount_pence))
  const [nameStr, setNameStr] = useState(line.name)

  useEffect(() => {
    setAmountStr(penceToPounds(line.default_amount_pence))
    setNameStr(line.name)
  }, [line.default_amount_pence, line.name])

  return (
    <div className="stack" style={{ gap: 6, padding: 8, background: 'var(--panel2)', borderRadius: 6 }}>
      <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <input
          className="input"
          style={{ flex: 1, minWidth: 160 }}
          value={nameStr}
          disabled={busy}
          onChange={(e) => setNameStr(e.target.value)}
          onBlur={() => {
            if (nameStr.trim() && nameStr !== line.name) onUpdate({ name: nameStr.trim() })
          }}
        />
        <select
          className="input"
          value={line.line_kind}
          disabled={busy}
          onChange={(e) => onUpdate({ line_kind: e.target.value })}
        >
          {LINE_KINDS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <button type="button" className="btn danger" style={SMALL} disabled={busy} onClick={onDelete}>
          Remove
        </button>
      </div>
      {line.line_kind === 'item' ? (
        <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <select
            className="input"
            value={line.amount_kind ?? 'fixed'}
            disabled={busy}
            onChange={(e) => onUpdate({ amount_kind: e.target.value })}
          >
            {AMOUNT_KINDS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          {line.amount_kind !== 'band' ? (
            <>
              <span className="muted" style={{ fontSize: 12 }}>
                £
              </span>
              <input
                className="input"
                style={{ width: 100 }}
                value={amountStr}
                disabled={busy}
                onChange={(e) => setAmountStr(e.target.value)}
                onBlur={() => {
                  const p = poundsToPence(amountStr)
                  if (p != null) onUpdate({ default_amount_pence: p })
                }}
              />
            </>
          ) : (
            <select
              className="input"
              value={line.band_set_id ?? ''}
              disabled={busy}
              onChange={(e) => onUpdate({ band_set_id: e.target.value || null })}
            >
              <option value="">Select band set…</option>
              {bandSetOptions.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.label}
                </option>
              ))}
            </select>
          )}
          <label className="row" style={{ gap: 4, fontSize: 12 }}>
            <input
              type="checkbox"
              checked={line.include_in_vat}
              disabled={busy}
              onChange={(e) => onUpdate({ include_in_vat: e.target.checked })}
            />
            Include in VAT
          </label>
        </div>
      ) : null}
    </div>
  )
}
