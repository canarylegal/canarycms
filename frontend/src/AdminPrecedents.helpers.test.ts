import { describe, expect, it } from 'vitest'
import { precedentDisplayNameFromFile, suggestedPrecedentReferenceHex } from './AdminPrecedents'

describe('AdminPrecedents helpers', () => {
  it('strips .docx from display names', () => {
    expect(precedentDisplayNameFromFile(new File([], 'Letter of claim.docx'))).toBe('Letter of claim')
    expect(precedentDisplayNameFromFile(new File([], 'notes.TXT'))).toBe('notes.TXT')
  })

  it('returns a 6-char hex reference', () => {
    const hex = suggestedPrecedentReferenceHex()
    expect(hex).toMatch(/^[0-9a-f]{6}$/)
  })
})
