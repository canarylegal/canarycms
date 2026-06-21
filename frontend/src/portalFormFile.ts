import type { FileSummary, PortalFormSubmissionSummary } from './types'

export function portalFormStatusLabel(d: PortalFormSubmissionSummary): string {
  switch (d.status) {
    case 'pending':
      return `Awaiting ${d.contact_name}`
    case 'completed':
      return 'Complete'
    case 'voided':
      return 'Voided'
    case 'superseded':
      return 'Superseded'
    default:
      return d.status
  }
}

/** Matter document row linked to a portal form submission. */
export function isPortalFormFile(f: FileSummary): boolean {
  return Boolean(f.portal_form_submission)
}
