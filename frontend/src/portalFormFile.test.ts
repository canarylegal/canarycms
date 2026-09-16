import { describe, expect, it } from 'vitest'
import type { FileSummary, PortalFormSubmissionSummary } from './types'
import { isPortalFormFile, portalFormStatusLabel } from './portalFormFile'

describe('portalFormStatusLabel', () => {
  const base = {
    id: 'p1',
    case_id: 'c1',
    contact_name: 'Sam',
  } as PortalFormSubmissionSummary

  it('labels known statuses', () => {
    expect(portalFormStatusLabel({ ...base, status: 'pending' })).toBe('Awaiting Sam')
    expect(portalFormStatusLabel({ ...base, status: 'completed' })).toBe('Complete')
    expect(portalFormStatusLabel({ ...base, status: 'voided' })).toBe('Voided')
    expect(portalFormStatusLabel({ ...base, status: 'superseded' })).toBe('Superseded')
  })
})

describe('isPortalFormFile', () => {
  it('is true only when portal_form_submission is set', () => {
    const f = {
      id: 'f1',
      original_filename: 'form.pdf',
      mime_type: 'application/pdf',
      size_bytes: 1,
      created_at: '2024-01-01T00:00:00Z',
    } as FileSummary
    expect(isPortalFormFile(f)).toBe(false)
    expect(isPortalFormFile({ ...f, portal_form_submission: { id: 'p1' } as PortalFormSubmissionSummary })).toBe(
      true,
    )
  })
})
