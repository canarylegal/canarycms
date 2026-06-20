import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from './api'
import { useDialogs } from './DialogProvider'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import { FeeScaleBandRowModal } from './FeeScaleBandRowModal'
import { TextPromptModal } from './TextPromptModal'
import {
  addBandRowLocal,
  addBandSetLocal,
  addCategoryLocal,
  addLineLocal,
  buildEmptyDraftDetail,
  deleteBandRowLocal,
  deleteLineLocal,
  persistDraftFeeScale,
  setScaleMetaLocal,
  setVatRateLocal,
  updateBandRowLocal,
  updateLineLocal,
  type FeeScaleDraftCreate,
} from './feeScaleDraft'
import { VAT_TREATMENT_OPTIONS, formatVatCell, type FeeScaleVatTreatment } from './feeScaleVat'
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
  /** Existing saved fee scale */
  scaleId?: string
  /** New fee scale — held locally until Save & finish setup */
  draftCreate?: FeeScaleDraftCreate
  /** Pre-built draft content (e.g. clone); defaults to empty scale */
  draftInitialDetail?: FeeScaleDetailOut | null
  setupMode?: boolean
  onBack: () => void
}

type EditorModal =
  | { kind: 'category' }
  | { kind: 'line'; category: FeeScaleCategoryOut }
  | { kind: 'bandSet' }
  | { kind: 'bandRow'; bandSet: FeeScaleBandSetOut }
  | null

export function FeeScaleEditor({ token, scaleId, draftCreate, draftInitialDetail, setupMode, onBack }: Props) {
  const { askConfirm } = useDialogs()
  const isDraft = Boolean(draftCreate) && !scaleId
  const [detail, setDetail] = useState<FeeScaleDetailOut | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [vatPct, setVatPct] = useState('20')
  const [scaleName, setScaleName] = useState('')
  const [scaleReference, setScaleReference] = useState('')
  const [modal, setModal] = useState<EditorModal>(null)

  const load = useCallback(async () => {
    if (!scaleId) return
    setBusy(true)
    setErr(null)
    try {
      const data = await apiFetch<FeeScaleDetailOut>(`/fee-scales/${scaleId}`, { token })
      setDetail(data)
      setVatPct(String((data.vat_rate_bps ?? 2000) / 100))
      setScaleName(data.name)
      setScaleReference(data.reference)
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not load fee scale')
    } finally {
      setBusy(false)
    }
  }, [scaleId, token])

  useEffect(() => {
    if (isDraft && draftCreate) {
      const initial = draftInitialDetail ?? buildEmptyDraftDetail(draftCreate)
      setDetail(initial)
      setVatPct(String((initial.vat_rate_bps ?? 2000) / 100))
      setScaleName(initial.name)
      setScaleReference(initial.reference)
      setErr(null)
      return
    }
    void load()
  }, [isDraft, draftCreate, draftInitialDetail, load])

  const bandSetOptions = useMemo(
    () => (detail?.band_sets ?? []).map((b) => ({ id: b.id, label: b.name })),
    [detail?.band_sets],
  )

  function applyVatRateLocally() {
    if (!detail) return
    const bps = Math.round(Number(vatPct) * 100)
    if (!Number.isFinite(bps) || bps < 0) return
    if (bps === (detail.vat_rate_bps ?? 2000)) return
    setDetail(setVatRateLocal(detail, bps))
  }

  async function saveVat() {
    if (!detail) return
    const bps = Math.round(Number(vatPct) * 100)
    if (!Number.isFinite(bps) || bps < 0) return
    if (isDraft) {
      applyVatRateLocally()
      return
    }
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

  function validatedScaleMeta(): { name: string; reference: string } | null {
    const name = scaleName.trim()
    const reference = scaleReference.trim()
    if (!name) {
      setErr('Enter a name for the fee scale.')
      return null
    }
    if (!reference) {
      setErr('Enter a reference for the fee scale.')
      return null
    }
    return { name, reference }
  }

  async function saveAndClose() {
    if (!detail) return
    const meta = validatedScaleMeta()
    if (!meta) return
    if ((setupMode || isDraft) && !hasQuoteLines(detail)) {
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
      const bps = Math.round(Number(vatPct) * 100)
      let detailToSave = setScaleMetaLocal(detail, meta.name, meta.reference)
      detailToSave =
        Number.isFinite(bps) && bps >= 0 ? setVatRateLocal(detailToSave, bps) : detailToSave
      if (isDraft && draftCreate) {
        await persistDraftFeeScale(token, detailToSave, draftCreate)
      } else {
        const patch: Record<string, unknown> = {}
        if (bps !== (detail.vat_rate_bps ?? 2000) && Number.isFinite(bps) && bps >= 0) {
          patch.vat_rate_bps = bps
        }
        if (meta.name !== detail.name) patch.name = meta.name
        if (meta.reference !== detail.reference) patch.reference = meta.reference
        if (Object.keys(patch).length > 0) {
          await apiFetch(`/fee-scales/${detail.id}`, { token, method: 'PATCH', json: patch })
        }
      }
      onBack()
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  async function handleBack() {
    if (isDraft) {
      const ok = await askConfirm({
        title: 'Cancel fee scale?',
        message: 'Nothing will be saved. Cancel creating this fee scale?',
        confirmLabel: 'Cancel creation',
        danger: true,
      })
      if (!ok) return
      onBack()
      return
    }
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
    if (isDraft) {
      setDetail(addCategoryLocal(detail, name))
      setModal(null)
      return
    }
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
    if (isDraft && detail) {
      setDetail(addLineLocal(detail, category.id, name))
      setModal(null)
      return
    }
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
    if (isDraft) {
      setDetail(addBandSetLocal(detail, name))
      setModal(null)
      return
    }
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
    if (isDraft && detail) {
      setDetail(addBandRowLocal(detail, set.id, values))
      setModal(null)
      return
    }
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
    if (isDraft && detail) {
      setDetail(updateLineLocal(detail, line.id, patch as Partial<FeeScaleLineOut>))
      return
    }
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
    if (isDraft && detail) {
      setDetail(deleteLineLocal(detail, lineId))
      return
    }
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
    if (isDraft && detail) {
      setDetail(updateBandRowLocal(detail, row.id, patch as Partial<FeeScaleBandRowOut>))
      return
    }
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
    if (isDraft && detail) {
      setDetail(deleteBandRowLocal(detail, rowId))
      return
    }
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

  if (!detail && busy && !isDraft) return <div className="muted">Loading…</div>
  if (!detail) return <div className="error">{err ?? 'Not found'}</div>

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
        <div className="stack" style={{ gap: 8, flex: 1, minWidth: 0 }}>
          <label className="field" style={{ margin: 0 }}>
            <span>Name</span>
            <input
              className="input"
              value={scaleName}
              onChange={(e) => {
                setScaleName(e.target.value)
                setErr(null)
              }}
              disabled={busy}
            />
          </label>
          <label className="field" style={{ margin: 0 }}>
            <span>Reference</span>
            <input
              className="input"
              value={scaleReference}
              onChange={(e) => {
                setScaleReference(e.target.value)
                setErr(null)
              }}
              disabled={busy}
            />
          </label>
          <div className="muted" style={{ fontSize: 12 }}>
            {detail.scope_summary}
            {isDraft ? ' · not saved yet' : null}
          </div>
        </div>
        <div className="row" style={{ gap: 8, flexShrink: 0 }}>
          <button type="button" className="btn" disabled={busy} onClick={() => void handleBack()}>
            Back
          </button>
          <button type="button" className="btn primary" disabled={busy} onClick={() => void saveAndClose()}>
            {setupMode || isDraft ? 'Save & finish setup' : 'Save & close'}
          </button>
        </div>
      </div>

      {setupMode || isDraft ? (
        <div className="card" style={{ padding: 12, borderLeft: '3px solid var(--accent)' }}>
          <strong>Set up your fee scale</strong>
          <p className="muted" style={{ margin: '6px 0 0', fontSize: 13 }}>
            Add categories and quote lines as needed. Click <strong>Save &amp; finish setup</strong> to create the fee
            scale, or <strong>Back</strong> to cancel without saving.
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
              No lines — add section headers, items, subtotals, and totals in order.
            </div>
          ) : (
            <table className="finTable feeScaleQuoteTable" style={{ fontSize: 13 }}>
              <colgroup>
                <col className="feeScaleColType" />
                <col className="feeScaleColDesc" />
                <col className="feeScaleColAmount" />
                <col className="feeScaleColVatTreatment" />
                <col className="feeScaleColVat" />
                <col className="feeScaleColAct" />
              </colgroup>
              <thead>
                <tr>
                  <th>Type</th>
                  <th className="feeScaleDescCol">Description</th>
                  <th className="finAmtCell">Amount</th>
                  <th className="feeScaleVatTreatmentCol">VAT treatment</th>
                  <th className="finAmtCell">VAT</th>
                  <th className="finActCell" />
                </tr>
              </thead>
              <tbody>
                {cat.lines.map((line) => (
                  <LineEditor
                    key={line.id}
                    line={line}
                    vatRateBps={detail.vat_rate_bps ?? 2000}
                    bandSetOptions={bandSetOptions}
                    busy={busy}
                    onUpdate={(patch) => void updateLine(line, patch)}
                    onDelete={() => void deleteLine(line.id)}
                  />
                ))}
              </tbody>
            </table>
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
  vatRateBps,
  bandSetOptions,
  busy,
  onUpdate,
  onDelete,
}: {
  line: FeeScaleLineOut
  vatRateBps: number
  bandSetOptions: { id: string; label: string }[]
  busy: boolean
  onUpdate: (patch: Record<string, unknown>) => void
  onDelete: () => void
}) {
  const [amountStr, setAmountStr] = useState(penceToPounds(line.default_amount_pence))
  const [nameStr, setNameStr] = useState(line.name)
  const treatment = (line.vat_treatment ?? 'included') as FeeScaleVatTreatment
  const isItem = line.line_kind === 'item'
  const vatDisplay = isItem
    ? formatVatCell(line.default_amount_pence, treatment, vatRateBps)
    : '—'

  useEffect(() => {
    setAmountStr(penceToPounds(line.default_amount_pence))
    setNameStr(line.name)
  }, [line.default_amount_pence, line.name])

  return (
    <tr className="finRow">
      <td className="feeScaleTypeCell">
        <SingleSelectDropdown
          hideLabel
          label="Line type"
          options={LINE_KINDS}
          value={line.line_kind}
          disabled={busy}
          onChange={(v) => onUpdate({ line_kind: v })}
        />
      </td>
      <td className="feeScaleDescCol">
        <div
          className="feeScaleLineCells"
          style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'nowrap', minWidth: 0 }}
        >
          <input
            className="input feeScaleLineName"
            value={nameStr}
            disabled={busy}
            onChange={(e) => setNameStr(e.target.value)}
            onBlur={() => {
              if (nameStr.trim() && nameStr !== line.name) onUpdate({ name: nameStr.trim() })
            }}
          />
          {isItem ? (
            <>
              <div className="feeScaleLineAmountKind">
                <SingleSelectDropdown
                  hideLabel
                  label="Amount kind"
                  options={AMOUNT_KINDS}
                  value={line.amount_kind ?? 'fixed'}
                  disabled={busy}
                  onChange={(v) => onUpdate({ amount_kind: v })}
                />
              </div>
              {line.amount_kind === 'band' ? (
                <div className="feeScaleLineBandSet">
                  <SingleSelectDropdown
                    hideLabel
                    label="Band set"
                    options={[
                      { value: '', label: 'Band set…' },
                      ...bandSetOptions.map((b) => ({ value: b.id, label: b.label })),
                    ]}
                    value={line.band_set_id ?? ''}
                    disabled={busy}
                    onChange={(v) => onUpdate({ band_set_id: v || null })}
                  />
                </div>
              ) : null}
            </>
          ) : null}
        </div>
      </td>
      <td className="finAmtCell">
        {isItem && line.amount_kind !== 'band' ? (
          <input
            className="input"
            style={{ width: '100%', textAlign: 'right' }}
            value={amountStr}
            disabled={busy}
            onChange={(e) => setAmountStr(e.target.value)}
            onBlur={() => {
              const p = poundsToPence(amountStr)
              if (p != null) onUpdate({ default_amount_pence: p })
            }}
          />
        ) : (
          <span className="muted">—</span>
        )}
      </td>
      <td className="feeScaleVatTreatmentCol">
        {isItem ? (
          <SingleSelectDropdown
            hideLabel
            label="VAT treatment"
            options={VAT_TREATMENT_OPTIONS}
            value={treatment}
            disabled={busy}
            onChange={(v) => onUpdate({ vat_treatment: v })}
          />
        ) : (
          <span className="muted">—</span>
        )}
      </td>
      <td className="finAmtCell" style={{ textAlign: 'right' }}>
        <span className="muted">{vatDisplay}</span>
      </td>
      <td className="finActCell">
        <button type="button" className="btn danger" style={SMALL} disabled={busy} onClick={onDelete}>
          Remove
        </button>
      </td>
    </tr>
  )
}
