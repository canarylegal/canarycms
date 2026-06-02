export type FeeScaleVatTreatment = 'included' | 'plus_vat'

export const VAT_TREATMENT_OPTIONS: { value: FeeScaleVatTreatment; label: string }[] = [
  { value: 'included', label: 'Including / No VAT' },
  { value: 'plus_vat', label: 'Plus VAT' },
]

export function vatPenceForItem(
  amountPence: number | null | undefined,
  treatment: FeeScaleVatTreatment,
  vatRateBps: number,
): number | null {
  if (amountPence == null || treatment !== 'plus_vat') return null
  return Math.round(amountPence * vatRateBps / 10000)
}

export function formatVatCell(
  amountPence: number | null | undefined,
  treatment: FeeScaleVatTreatment,
  vatRateBps: number,
): string {
  const vat = vatPenceForItem(amountPence, treatment, vatRateBps)
  if (vat == null) return '—'
  return (vat / 100).toFixed(2)
}
