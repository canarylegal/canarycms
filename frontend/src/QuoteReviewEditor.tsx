import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch } from './api'
import { poundsToPence, penceToPounds } from './FeeScaleEditor'
import { useDialogs } from './DialogProvider'
import type {
  FeeScaleDetailOut,
  FeeScaleLineKind,
  QuoteDraftCategory,
  QuoteDraftLine,
  QuotePreviewOut,
} from './types'

const LINE_KIND_OPTIONS: { value: FeeScaleLineKind; label: string }[] = [
  { value: 'section_header', label: 'Section header' },
  { value: 'item', label: 'Line item' },
  { value: 'vat', label: 'VAT (calculated)' },
  { value: 'subtotal', label: 'Subtotal (calculated)' },
  { value: 'total', label: 'Grand total (calculated)' },
]

function newKey(): string {
  return crypto.randomUUID()
}

export function buildDraftFromDetail(detail: FeeScaleDetailOut): QuoteDraftCategory[] {
  return detail.categories.map((cat, ci) => ({
    key: cat.id,
    category_id: cat.id,
    name: cat.name,
    sort_order: ci,
    lines: cat.lines.map((ln, li) => ({
      key: ln.id,
      line_id: ln.id,
      name: ln.name,
      line_kind: ln.line_kind,
      amount_kind: ln.amount_kind,
      amount_pence: ln.default_amount_pence,
      include_in_vat: ln.include_in_vat,
      band_set_id: ln.band_set_id,
      sort_order: li,
    })),
  }))
}

type Props = {
  token: string
  feeScaleId: string
  propertyValueStr: string
  onPropertyValueChange: (v: string) => void
  onPreviewChange: (preview: QuotePreviewOut | null) => void
  onComposeDataChange?: (data: {
    draft: QuoteDraftCategory[]
    amountOverrides: Record<string, string>
    preview: QuotePreviewOut | null
  }) => void
}

export function QuoteReviewEditor({
  token,
  feeScaleId,
  propertyValueStr,
  onPropertyValueChange,
  onPreviewChange,
  onComposeDataChange,
}: Props) {
  const { askConfirm } = useDialogs()
  const [draft, setDraft] = useState<QuoteDraftCategory[]>([])
  const [preview, setPreview] = useState<QuotePreviewOut | null>(null)
  const [amountOverrides, setAmountOverrides] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [addCatOpen, setAddCatOpen] = useState(false)
  const [addCatName, setAddCatName] = useState('')
  const [addLineCatKey, setAddLineCatKey] = useState<string | null>(null)
  const [addLineName, setAddLineName] = useState('')
  const previewChangeRef = useRef(onPreviewChange)
  const composeDataRef = useRef(onComposeDataChange)
  previewChangeRef.current = onPreviewChange
  composeDataRef.current = onComposeDataChange

  const [previewBusy, setPreviewBusy] = useState(false)
  const initRef = useRef(false)

  const loadDetail = useCallback(async () => {
    setLoading(true)
    try {
      const detail = await apiFetch<FeeScaleDetailOut>(`/fee-scales/${feeScaleId}`, { token })
      setDraft(buildDraftFromDetail(detail))
      setAmountOverrides({})
      initRef.current = true
    } finally {
      setLoading(false)
    }
  }, [feeScaleId, token])

  useEffect(() => {
    initRef.current = false
    void loadDetail()
  }, [loadDetail])

  useEffect(() => {
    if (!initRef.current || draft.length === 0) return
    const pv = poundsToPence(propertyValueStr)
    const overrides: Record<string, number> = {}
    for (const [key, s] of Object.entries(amountOverrides)) {
      const p = poundsToPence(s)
      if (p != null) overrides[key] = p
    }
    let cancelled = false
    setPreviewBusy(true)
    const timer = window.setTimeout(() => {
      void apiFetch<QuotePreviewOut>(`/fee-scales/${feeScaleId}/preview`, {
        token,
        method: 'POST',
        json: {
          property_value_pence: pv,
          amount_overrides: overrides,
          draft,
        },
      })
        .then((data) => {
          if (!cancelled) {
            setPreview(data)
            previewChangeRef.current(data)
            composeDataRef.current?.({ draft, amountOverrides, preview: data })
          }
        })
        .catch(() => {
          if (!cancelled) {
            setPreview(null)
            previewChangeRef.current(null)
            composeDataRef.current?.({ draft, amountOverrides, preview: null })
          }
        })
        .finally(() => {
          if (!cancelled) setPreviewBusy(false)
        })
    }, 350)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [draft, amountOverrides, propertyValueStr, feeScaleId, token])

  function previewLine(key: string) {
    return preview?.lines.find((ln) => ln.key === key)
  }

  function setCatName(catKey: string, name: string) {
    setDraft((prev) => prev.map((c) => (c.key === catKey ? { ...c, name } : c)))
  }

  function setLineField(catKey: string, lineKey: string, patch: Partial<QuoteDraftLine>) {
    setDraft((prev) =>
      prev.map((c) =>
        c.key !== catKey
          ? c
          : {
              ...c,
              lines: c.lines.map((ln) => (ln.key === lineKey ? { ...ln, ...patch } : ln)),
            },
      ),
    )
  }

  function moveCategory(catKey: string, dir: -1 | 1) {
    setDraft((prev) => {
      const sorted = [...prev].sort((a, b) => a.sort_order - b.sort_order)
      const idx = sorted.findIndex((c) => c.key === catKey)
      const swap = idx + dir
      if (idx < 0 || swap < 0 || swap >= sorted.length) return prev
      const next = sorted.map((c, i) => {
        if (i === idx) return { ...sorted[swap], sort_order: idx }
        if (i === swap) return { ...sorted[idx], sort_order: swap }
        return { ...c, sort_order: i }
      })
      return next
    })
  }

  function moveLine(catKey: string, lineKey: string, dir: -1 | 1) {
    setDraft((prev) =>
      prev.map((c) => {
        if (c.key !== catKey) return c
        const sorted = [...c.lines].sort((a, b) => a.sort_order - b.sort_order)
        const idx = sorted.findIndex((ln) => ln.key === lineKey)
        const swap = idx + dir
        if (idx < 0 || swap < 0 || swap >= sorted.length) return c
        const reordered = sorted.map((ln, i) => {
          if (i === idx) return { ...sorted[swap], sort_order: idx }
          if (i === swap) return { ...sorted[idx], sort_order: swap }
          return { ...ln, sort_order: i }
        })
        return { ...c, lines: reordered }
      }),
    )
  }

  async function deleteCategory(catKey: string) {
    const ok = await askConfirm({
      title: 'Remove category',
      message: 'Remove this category and all its lines from this quote?',
      danger: true,
      confirmLabel: 'Remove',
    })
    if (!ok) return
    setDraft((prev) => prev.filter((c) => c.key !== catKey).map((c, i) => ({ ...c, sort_order: i })))
  }

  async function deleteLine(catKey: string, lineKey: string) {
    const ok = await askConfirm({
      title: 'Remove line',
      message: 'Remove this line from the quote?',
      danger: true,
      confirmLabel: 'Remove',
    })
    if (!ok) return
    setDraft((prev) =>
      prev.map((c) =>
        c.key !== catKey
          ? c
          : {
              ...c,
              lines: c.lines.filter((ln) => ln.key !== lineKey).map((ln, i) => ({ ...ln, sort_order: i })),
            },
      ),
    )
    setAmountOverrides((prev) => {
      const next = { ...prev }
      delete next[lineKey]
      return next
    })
  }

  function addCategory() {
    if (!addCatName.trim()) return
    const key = newKey()
    setDraft((prev) => [
      ...prev,
      { key, category_id: null, name: addCatName.trim(), sort_order: prev.length, lines: [] },
    ])
    setAddCatName('')
    setAddCatOpen(false)
  }

  function addLine(catKey: string) {
    if (!addLineName.trim()) return
    const key = newKey()
    setDraft((prev) =>
      prev.map((c) =>
        c.key !== catKey
          ? c
          : {
              ...c,
              lines: [
                ...c.lines,
                {
                  key,
                  line_id: null,
                  name: addLineName.trim(),
                  line_kind: 'item' as FeeScaleLineKind,
                  amount_kind: 'editable',
                  amount_pence: null,
                  include_in_vat: false,
                  band_set_id: null,
                  sort_order: c.lines.length,
                },
              ],
            },
      ),
    )
    setAddLineCatKey(null)
    setAddLineName('')
  }

  if (loading) return <div className="muted quoteReviewLoading">Loading fee scale…</div>

  return (
    <div className="quoteReviewShell finShell">
      <div className="quoteReviewToolbar">
        {preview?.needs_property_value ? (
          <div className="quoteReviewPropertyBlock">
            <label className="quoteReviewPropertyLabel" htmlFor="quote-property-value">
              Property value (£)
            </label>
            <div className="quoteReviewPropertyRow">
              <input
                id="quote-property-value"
                className="input quoteReviewPropertyInput"
                value={propertyValueStr}
                onChange={(e) => onPropertyValueChange(e.target.value)}
                placeholder="e.g. 320000"
              />
              <div className="quoteReviewToolbarActions">
                <button type="button" className="btn finAddCatBtn" onClick={() => setAddCatOpen(true)}>
                  + Category
                </button>
                {previewBusy ? <span className="muted quoteReviewUpdating">Updating…</span> : null}
              </div>
            </div>
          </div>
        ) : (
          <div className="quoteReviewToolbarMain">
            <p className="muted quoteReviewHint">
              Adjust line descriptions and amounts below. VAT and totals recalculate automatically.
            </p>
            <div className="quoteReviewToolbarActions">
              <button type="button" className="btn finAddCatBtn" onClick={() => setAddCatOpen(true)}>
                + Category
              </button>
              {previewBusy ? <span className="muted quoteReviewUpdating">Updating…</span> : null}
            </div>
          </div>
        )}
      </div>

      <div className="quoteReviewCategories stack" style={{ gap: 14 }}>
        {[...draft]
          .sort((a, b) => a.sort_order - b.sort_order)
          .map((cat) => (
          <div key={cat.key} className="finCategoryBlock quoteReviewCategory">
            <div className="finCategoryHead">
              <input
                className="input finCategoryNameInput"
                value={cat.name}
                onChange={(e) => setCatName(cat.key, e.target.value)}
                aria-label="Category name"
              />
              <div className="row" style={{ gap: 4 }}>
                <button type="button" className="btn finRowBtn" title="Move up" onClick={() => moveCategory(cat.key, -1)}>
                  ↑
                </button>
                <button type="button" className="btn finRowBtn" title="Move down" onClick={() => moveCategory(cat.key, 1)}>
                  ↓
                </button>
                <button
                  type="button"
                  className="btn finCatDeleteBtn"
                  onClick={() => void deleteCategory(cat.key)}
                  title="Remove category"
                >
                  ✕
                </button>
              </div>
            </div>

            <table className="finTable quoteReviewTable">
              <thead>
                <tr>
                  <th style={{ width: 130 }}>Type</th>
                  <th>Description</th>
                  <th className="finAmtCell" style={{ width: 120 }}>
                    Amount
                  </th>
                  <th className="finActCell" style={{ width: 88 }} />
                </tr>
              </thead>
              <tbody>
                {[...cat.lines]
                  .sort((a, b) => a.sort_order - b.sort_order)
                  .map((ln) => {
                    const computed = previewLine(ln.key)
                    const isCalculated = ln.line_kind === 'vat' || ln.line_kind === 'subtotal' || ln.line_kind === 'total'
                    const showAmount = ln.line_kind !== 'section_header'
                    const amountStr =
                      amountOverrides[ln.key] ??
                      (computed?.amount_pence != null ? penceToPounds(computed.amount_pence) : '')
                    return (
                      <tr key={ln.key} className={`finRow${computed?.is_bold ? ' quoteReviewRowBold' : ''}`}>
                        <td>
                          <select
                            className="select"
                            style={{ width: '100%', maxWidth: 124 }}
                            value={ln.line_kind}
                            onChange={(e) =>
                              setLineField(cat.key, ln.key, { line_kind: e.target.value as FeeScaleLineKind })
                            }
                          >
                            {LINE_KIND_OPTIONS.map((o) => (
                              <option key={o.value} value={o.value}>
                                {o.label}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <input
                            className="input"
                            style={{ width: '100%' }}
                            value={ln.name}
                            onChange={(e) => setLineField(cat.key, ln.key, { name: e.target.value })}
                          />
                        </td>
                        <td className="finAmtCell">
                          {showAmount ? (
                            <input
                              className="input"
                              style={{ width: '100%', textAlign: 'right' }}
                              value={amountStr}
                              disabled={isCalculated}
                              placeholder={isCalculated ? '—' : '0.00'}
                              onChange={(e) =>
                                setAmountOverrides((prev) => ({ ...prev, [ln.key]: e.target.value }))
                              }
                            />
                          ) : (
                            <span className="muted">—</span>
                          )}
                        </td>
                        <td className="finActCell">
                          <div className="row" style={{ gap: 2, justifyContent: 'flex-end' }}>
                            <button
                              type="button"
                              className="btn finRowBtn"
                              title="Move up"
                              onClick={() => moveLine(cat.key, ln.key, -1)}
                            >
                              ↑
                            </button>
                            <button
                              type="button"
                              className="btn finRowBtn"
                              title="Move down"
                              onClick={() => moveLine(cat.key, ln.key, 1)}
                            >
                              ↓
                            </button>
                            <button
                              type="button"
                              className="btn danger finRowBtn"
                              onClick={() => void deleteLine(cat.key, ln.key)}
                              title="Remove"
                            >
                              ✕
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                {cat.lines.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="muted" style={{ padding: '8px 10px', fontStyle: 'italic' }}>
                      No lines in this category.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>

            {addLineCatKey === cat.key ? (
              <div className="finAddItemRow">
                <input
                  className="input"
                  style={{ flex: 1 }}
                  placeholder="Line description…"
                  value={addLineName}
                  autoFocus
                  onChange={(e) => setAddLineName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') addLine(cat.key)
                    if (e.key === 'Escape') {
                      setAddLineCatKey(null)
                      setAddLineName('')
                    }
                  }}
                />
                <button
                  className="btn"
                  style={{ background: 'var(--primary)', color: '#fff', borderColor: 'var(--primary)' }}
                  disabled={!addLineName.trim()}
                  onClick={() => addLine(cat.key)}
                >
                  Add
                </button>
                <button
                  className="btn"
                  onClick={() => {
                    setAddLineCatKey(null)
                    setAddLineName('')
                  }}
                >
                  Cancel
                </button>
              </div>
            ) : (
              <button type="button" className="btn finAddItemBtn" onClick={() => setAddLineCatKey(cat.key)}>
                + Add line
              </button>
            )}
          </div>
        ))}
      </div>

      {addCatOpen ? (
        <div className="finAddCatRow">
          <input
            className="input"
            style={{ flex: 1, maxWidth: 320 }}
            placeholder="New category name…"
            value={addCatName}
            autoFocus
            onChange={(e) => setAddCatName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') addCategory()
              if (e.key === 'Escape') {
                setAddCatOpen(false)
                setAddCatName('')
              }
            }}
          />
          <button
            className="btn"
            style={{ background: 'var(--primary)', color: '#fff', borderColor: 'var(--primary)' }}
            disabled={!addCatName.trim()}
            onClick={addCategory}
          >
            Add category
          </button>
          <button
            className="btn"
            onClick={() => {
              setAddCatOpen(false)
              setAddCatName('')
            }}
          >
            Cancel
          </button>
        </div>
      ) : null}
    </div>
  )
}
