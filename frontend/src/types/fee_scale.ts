export type FeeScaleLineKind = 'section_header' | 'item' | 'vat' | 'subtotal' | 'total'

export type FeeScaleAmountKind = 'fixed' | 'editable' | 'band'

export type FeeScaleOut = {
  id: string
  name: string
  reference: string
  vat_rate_bps: number
  matter_head_type_id?: string | null
  matter_sub_type_id?: string | null
  matter_head_type_name?: string | null
  matter_sub_type_name?: string | null
  scope_summary?: string | null
  is_favorited?: boolean
  created_at: string
  updated_at: string
}

export type FeeScaleLineOut = {
  id: string
  category_id: string
  name: string
  line_kind: FeeScaleLineKind
  amount_kind?: FeeScaleAmountKind | null
  default_amount_pence?: number | null
  band_set_id?: string | null
  vat_treatment: 'included' | 'plus_vat'
  sort_order: number
}

export type FeeScaleCategoryOut = {
  id: string
  fee_scale_id: string
  name: string
  sort_order: number
  lines: FeeScaleLineOut[]
}

export type FeeScaleBandRowOut = {
  id: string
  band_set_id: string
  min_value_pence: number
  max_value_pence?: number | null
  amount_pence: number
  sort_order: number
}

export type FeeScaleBandSetOut = {
  id: string
  fee_scale_id: string
  name: string
  sort_order: number
  rows: FeeScaleBandRowOut[]
}

export type FeeScaleDetailOut = FeeScaleOut & {
  categories: FeeScaleCategoryOut[]
  band_sets: FeeScaleBandSetOut[]
}

export type QuotePreviewLineOut = {
  key?: string | null
  line_id?: string | null
  name: string
  line_kind: string
  amount_pence?: number | null
  amount_display?: string | null
  editable: boolean
  is_bold: boolean
  vat_pence?: number | null
  vat_treatment?: 'included' | 'plus_vat' | null
  amount_kind?: string | null
  band_set_id?: string | null
  sort_order?: number
}

export type QuotePreviewCategoryOut = {
  key: string
  category_id?: string | null
  name: string
  sort_order: number
  lines: QuotePreviewLineOut[]
}

export type QuotePreviewOut = {
  fee_scale_id: string
  property_value_pence?: number | null
  needs_property_value: boolean
  lines: QuotePreviewLineOut[]
  categories?: QuotePreviewCategoryOut[]
}

export type QuoteDraftLine = {
  key: string
  line_id?: string | null
  name: string
  line_kind: FeeScaleLineKind
  amount_kind?: FeeScaleAmountKind | null
  amount_pence?: number | null
  vat_treatment: 'included' | 'plus_vat'
  band_set_id?: string | null
  sort_order: number
}

export type QuoteDraftCategory = {
  key: string
  category_id?: string | null
  name: string
  sort_order: number
  lines: QuoteDraftLine[]
}
