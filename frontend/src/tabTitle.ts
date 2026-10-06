import { getProductName } from './brandConfig'

/** Browser tab title: `{product} - {segment}` (product from brand config / Canary default). */
export function canaryDocumentTitle(segment: string): string {
  const product = getProductName()
  const s = segment.trim()
  return s ? `${product} - ${s}` : product
}
