import { describe, expect, it } from 'vitest'
import { buildContactCompareFields, contactMergeImpactLines } from './contactMergeCompare'
import type { ContactMergePreviewOut, ContactOut } from './types'

function contact(partial: Partial<ContactOut> & Pick<ContactOut, 'id' | 'name' | 'type'>): ContactOut {
  return {
    email: null,
    phone: null,
    title: null,
    first_name: null,
    middle_name: null,
    last_name: null,
    company_name: null,
    trading_name: null,
    address_line1: null,
    address_line2: null,
    city: null,
    county: null,
    postcode: null,
    country: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...partial,
  }
}

describe('contactMergeCompare', () => {
  it('highlights mismatched identity fields side by side', () => {
    const keep = contact({
      id: 'a',
      type: 'person',
      name: 'Sam Thomas',
      first_name: 'Sam',
      last_name: 'Thomas',
      email: 'sam@example.com',
      phone: '0111',
    })
    const absorb = contact({
      id: 'b',
      type: 'person',
      name: 'Samuel Thomas',
      first_name: 'Samuel',
      last_name: 'Thomas',
      email: 'other@example.com',
      phone: '0111',
    })
    const rows = buildContactCompareFields(keep, absorb)
    const byKey = Object.fromEntries(rows.map((r) => [r.key, r]))
    expect(byKey.first_name?.mismatch).toBe(true)
    expect(byKey.email?.mismatch).toBe(true)
    expect(byKey.phone?.mismatch).toBe(false)
    expect(byKey.last_name?.mismatch).toBe(false)
  })

  it('builds impact lines including optional e-mail note', () => {
    const preview: ContactMergePreviewOut = {
      survivor: contact({ id: 'a', type: 'person', name: 'Sam', email: 'sam@example.com' }),
      source: contact({ id: 'b', type: 'person', name: 'Sam 2' }),
      survivor_matter_links: 1,
      source_matter_links: 2,
      survivor_grants: 0,
      source_grants: 1,
      survivor_client_portal_active: true,
      source_client_portal_active: true,
      survivor_matter_portal_active: 0,
      source_matter_portal_active: 0,
      email_mismatch: false,
      type_mismatch: false,
      will_reset_client_portal: true,
      will_reset_matter_portal_cases: 1,
    }
    const lines = contactMergeImpactLines(preview, { willEmail: true })
    expect(lines.some((l) => l.includes('both access codes revoked'))).toBe(true)
    expect(lines.some((l) => l.includes('sam@example.com'))).toBe(true)
    expect(lines.some((l) => l.includes('1 case code'))).toBe(true)
  })
})
