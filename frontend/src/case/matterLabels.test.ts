import { describe, expect, it } from 'vitest'
import { matterContactTypeLabel } from './matterLabels'

describe('matterContactTypeLabel', () => {
  it('maps known values via fallback options', () => {
    expect(matterContactTypeLabel('client')).toBe('Client')
    expect(matterContactTypeLabel('new-lender')).toBe('New lender')
  })

  it('returns em dash for empty values', () => {
    expect(matterContactTypeLabel(null)).toBe('—')
    expect(matterContactTypeLabel(undefined)).toBe('—')
    expect(matterContactTypeLabel('  ')).toBe('—')
  })

  it('falls back to the raw value when unknown', () => {
    expect(matterContactTypeLabel('custom-role')).toBe('custom-role')
  })

  it('uses provided option list when passed', () => {
    expect(matterContactTypeLabel('x', [{ value: 'x', label: 'Custom' }])).toBe('Custom')
  })
})
