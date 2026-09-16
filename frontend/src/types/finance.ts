export type FinanceItemTemplateOut = {
  id: string
  category_id: string
  name: string
  direction: 'debit' | 'credit'
  sort_order: number
}

export type FinanceCategoryTemplateOut = {
  id: string
  matter_sub_type_id: string
  name: string
  sort_order: number
  credit_only: boolean
  items: FinanceItemTemplateOut[]
}

export type FinanceTemplateOut = {
  matter_sub_type_id: string
  categories: FinanceCategoryTemplateOut[]
}

// ---------------------------------------------------------------------------
// Finance case data
// ---------------------------------------------------------------------------

export type FinanceItemOut = {
  id: string
  category_id: string
  template_item_id?: string | null
  name: string
  direction: 'debit' | 'credit'
  amount_pence?: number | null
  vat_pence?: number | null
  vat_treatment?: 'included' | 'plus_vat' | null
  sort_order: number
}

export type FinanceCategoryOut = {
  id: string
  case_id: string
  template_category_id?: string | null
  name: string
  sort_order: number
  credit_only: boolean
  items: FinanceItemOut[]
}

export type FinanceOut = {
  case_id: string
  categories: FinanceCategoryOut[]
  has_finance_preset?: boolean
  has_quote_snapshot?: boolean
  vat_rate_bps?: number
}
