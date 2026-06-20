import type { FileSummary, QuotePortalDeliverySummary } from './types'

export function quotePortalDeliveryHint(d: QuotePortalDeliverySummary): string {
  switch (d.status) {
    case 'pending':
      return `Awaiting ${d.contact_name}`
    case 'accepted':
      return `Accepted — ${d.contact_name}`
    case 'declined':
      return d.decline_reason ? `Declined — ${d.contact_name}` : `Declined — ${d.contact_name}`
    case 'superseded':
      return 'Superseded — re-send if needed'
    default:
      return d.status
  }
}

/** Matter quote document that can be sent (or re-sent) via the portal. */
export function isQuotePortalSendCandidate(f: FileSummary): boolean {
  if (f.quote_portal_delivery || f.is_portal_quote) return true
  return /^Quote[\s\u2014-]/i.test(f.original_filename.trim())
}
