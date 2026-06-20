import { apiFetch } from './api'
import { GLOBAL_PRECEDENT_SCOPE, type FeeScaleBandRowOut, type FeeScaleBandSetOut, type FeeScaleCategoryOut, type FeeScaleDetailOut, type FeeScaleLineOut, type MatterHeadTypeOut } from './types'

export type FeeScaleDraftCreate = {
  name: string
  reference: string
  matter_head_type_id: string | null
  matter_sub_type_id: string | null
  scope_summary: string
}

export function scopeSummaryForCreate(
  headId: string,
  subId: string,
  matterHeads: MatterHeadTypeOut[],
): string {
  if (!headId || headId === GLOBAL_PRECEDENT_SCOPE) return 'Global — all cases'
  const head = matterHeads.find((h) => h.id === headId)
  const headName = head?.name ?? '—'
  if (!subId || subId === GLOBAL_PRECEDENT_SCOPE) return `All sub-types — ${headName}`
  const sub = head?.sub_types?.find((s) => s.id === subId)
  return sub?.name ?? '—'
}

export function buildEmptyDraftDetail(draft: FeeScaleDraftCreate): FeeScaleDetailOut {
  const now = new Date().toISOString()
  return {
    id: 'draft',
    name: draft.name,
    reference: draft.reference,
    vat_rate_bps: 2000,
    matter_head_type_id: draft.matter_head_type_id,
    matter_sub_type_id: draft.matter_sub_type_id,
    scope_summary: draft.scope_summary,
    created_at: now,
    updated_at: now,
    categories: [],
    band_sets: [],
  }
}

/** Deep-copy an existing fee scale into draft form (new ids; band_set links preserved). */
export function buildClonedDraftDetail(source: FeeScaleDetailOut, draft: FeeScaleDraftCreate): FeeScaleDetailOut {
  const bandSetIdMap = new Map<string, string>()
  const band_sets = source.band_sets.map((bs) => {
    const bandSetId = newId()
    bandSetIdMap.set(bs.id, bandSetId)
    return {
      ...bs,
      id: bandSetId,
      fee_scale_id: 'draft',
      rows: bs.rows.map((row) => ({
        ...row,
        id: newId(),
        band_set_id: bandSetId,
      })),
    }
  })

  const categories = source.categories.map((cat) => {
    const categoryId = newId()
    return {
      ...cat,
      id: categoryId,
      fee_scale_id: 'draft',
      lines: cat.lines.map((line) => ({
        ...line,
        id: newId(),
        category_id: categoryId,
        band_set_id: line.band_set_id ? bandSetIdMap.get(line.band_set_id) ?? null : null,
      })),
    }
  })

  return {
    ...buildEmptyDraftDetail(draft),
    vat_rate_bps: source.vat_rate_bps ?? 2000,
    categories,
    band_sets,
  }
}

function newId(): string {
  return crypto.randomUUID()
}

export function addCategoryLocal(detail: FeeScaleDetailOut, name: string): FeeScaleDetailOut {
  const cat: FeeScaleCategoryOut = {
    id: newId(),
    fee_scale_id: detail.id,
    name: name.trim(),
    sort_order: detail.categories.length,
    lines: [],
  }
  return { ...detail, categories: [...detail.categories, cat] }
}

export function addLineLocal(detail: FeeScaleDetailOut, categoryId: string, name: string): FeeScaleDetailOut {
  return {
    ...detail,
    categories: detail.categories.map((cat) => {
      if (cat.id !== categoryId) return cat
      const line: FeeScaleLineOut = {
        id: newId(),
        category_id: cat.id,
        name: name.trim(),
        line_kind: 'item',
        amount_kind: 'fixed',
        default_amount_pence: 0,
        vat_treatment: 'included',
        sort_order: cat.lines.length,
      }
      return { ...cat, lines: [...cat.lines, line] }
    }),
  }
}

export function addBandSetLocal(detail: FeeScaleDetailOut, name: string): FeeScaleDetailOut {
  const set: FeeScaleBandSetOut = {
    id: newId(),
    fee_scale_id: detail.id,
    name: name.trim(),
    sort_order: detail.band_sets.length,
    rows: [],
  }
  return { ...detail, band_sets: [...detail.band_sets, set] }
}

export function addBandRowLocal(
  detail: FeeScaleDetailOut,
  bandSetId: string,
  values: { min_value_pence: number; max_value_pence: number | null; amount_pence: number },
): FeeScaleDetailOut {
  return {
    ...detail,
    band_sets: detail.band_sets.map((bs) => {
      if (bs.id !== bandSetId) return bs
      const row: FeeScaleBandRowOut = {
        id: newId(),
        band_set_id: bs.id,
        min_value_pence: values.min_value_pence,
        max_value_pence: values.max_value_pence,
        amount_pence: values.amount_pence,
        sort_order: bs.rows.length,
      }
      return { ...bs, rows: [...bs.rows, row] }
    }),
  }
}

export function updateLineLocal(
  detail: FeeScaleDetailOut,
  lineId: string,
  patch: Partial<FeeScaleLineOut>,
): FeeScaleDetailOut {
  return {
    ...detail,
    categories: detail.categories.map((cat) => ({
      ...cat,
      lines: cat.lines.map((ln) => (ln.id === lineId ? { ...ln, ...patch } : ln)),
    })),
  }
}

export function deleteLineLocal(detail: FeeScaleDetailOut, lineId: string): FeeScaleDetailOut {
  return {
    ...detail,
    categories: detail.categories.map((cat) => ({
      ...cat,
      lines: cat.lines.filter((ln) => ln.id !== lineId),
    })),
  }
}

export function updateBandRowLocal(
  detail: FeeScaleDetailOut,
  rowId: string,
  patch: Partial<FeeScaleBandRowOut>,
): FeeScaleDetailOut {
  return {
    ...detail,
    band_sets: detail.band_sets.map((bs) => ({
      ...bs,
      rows: bs.rows.map((r) => (r.id === rowId ? { ...r, ...patch } : r)),
    })),
  }
}

export function deleteBandRowLocal(detail: FeeScaleDetailOut, rowId: string): FeeScaleDetailOut {
  return {
    ...detail,
    band_sets: detail.band_sets.map((bs) => ({
      ...bs,
      rows: bs.rows.filter((r) => r.id !== rowId),
    })),
  }
}

export function setVatRateLocal(detail: FeeScaleDetailOut, vat_rate_bps: number): FeeScaleDetailOut {
  return { ...detail, vat_rate_bps }
}

export function setScaleMetaLocal(
  detail: FeeScaleDetailOut,
  name: string,
  reference: string,
): FeeScaleDetailOut {
  return { ...detail, name: name.trim(), reference: reference.trim() }
}

export async function persistDraftFeeScale(
  token: string,
  detail: FeeScaleDetailOut,
  draft: FeeScaleDraftCreate,
): Promise<void> {
  const scale = await apiFetch<FeeScaleDetailOut>('/fee-scales', {
    token,
    method: 'POST',
    json: {
      name: detail.name.trim(),
      reference: detail.reference.trim(),
      matter_head_type_id: draft.matter_head_type_id,
      matter_sub_type_id: draft.matter_sub_type_id,
      vat_rate_bps: detail.vat_rate_bps ?? 2000,
    },
  })

  const bandSetIdMap = new Map<string, string>()
  for (const bs of detail.band_sets) {
    const created = await apiFetch<FeeScaleBandSetOut>('/fee-scales/band-sets', {
      token,
      method: 'POST',
      json: { fee_scale_id: scale.id, name: bs.name, sort_order: bs.sort_order },
    })
    bandSetIdMap.set(bs.id, created.id)
    for (const row of bs.rows) {
      await apiFetch('/fee-scales/band-rows', {
        token,
        method: 'POST',
        json: {
          band_set_id: created.id,
          min_value_pence: row.min_value_pence,
          max_value_pence: row.max_value_pence,
          amount_pence: row.amount_pence,
          sort_order: row.sort_order,
        },
      })
    }
  }

  const categoryIdMap = new Map<string, string>()
  for (const cat of detail.categories) {
    const created = await apiFetch<FeeScaleCategoryOut>('/fee-scales/categories', {
      token,
      method: 'POST',
      json: { fee_scale_id: scale.id, name: cat.name, sort_order: cat.sort_order },
    })
    categoryIdMap.set(cat.id, created.id)
  }

  for (const cat of detail.categories) {
    const categoryId = categoryIdMap.get(cat.id)!
    for (const line of cat.lines) {
      await apiFetch('/fee-scales/lines', {
        token,
        method: 'POST',
        json: {
          category_id: categoryId,
          name: line.name,
          line_kind: line.line_kind,
          amount_kind: line.amount_kind,
          default_amount_pence: line.default_amount_pence,
          band_set_id: line.band_set_id ? bandSetIdMap.get(line.band_set_id) ?? null : null,
          vat_treatment: line.vat_treatment,
          sort_order: line.sort_order,
        },
      })
    }
  }
}
