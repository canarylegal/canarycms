import { describe, expect, it } from 'vitest'
import {
  DEFAULT_PORTAL_BACKGROUND,
  PORTAL_BRAND_INK,
  contrastRatio,
  normalizePortalBackgroundColor,
  portalBackgroundContrastOk,
  relativeLuminance,
} from './portalBackground'

describe('normalizePortalBackgroundColor', () => {
  it('returns null for empty / nullish / whitespace', () => {
    expect(normalizePortalBackgroundColor(null)).toBeNull()
    expect(normalizePortalBackgroundColor(undefined)).toBeNull()
    expect(normalizePortalBackgroundColor('')).toBeNull()
    expect(normalizePortalBackgroundColor('   ')).toBeNull()
  })

  it('normalizes 6-digit hex to uppercase with leading #', () => {
    expect(normalizePortalBackgroundColor('#1e293b')).toBe('#1E293B')
    expect(normalizePortalBackgroundColor('aabbcc')).toBe('#AABBCC')
  })

  it('expands 3-digit hex', () => {
    expect(normalizePortalBackgroundColor('#abc')).toBe('#AABBCC')
    expect(normalizePortalBackgroundColor('f00')).toBe('#FF0000')
  })

  it('rejects invalid colours', () => {
    expect(normalizePortalBackgroundColor('red')).toBeNull()
    expect(normalizePortalBackgroundColor('#gg0000')).toBeNull()
    expect(normalizePortalBackgroundColor('#12345')).toBeNull()
  })
})

describe('contrast helpers', () => {
  it('computes relative luminance for black and white', () => {
    expect(relativeLuminance('#000000')).toBeCloseTo(0, 5)
    expect(relativeLuminance('#FFFFFF')).toBeCloseTo(1, 5)
  })

  it('falls back to default background for invalid hex in luminance', () => {
    expect(relativeLuminance('not-a-colour')).toBeCloseTo(relativeLuminance(DEFAULT_PORTAL_BACKGROUND), 5)
  })

  it('reports high contrast for brand ink on dark slate', () => {
    const ratio = contrastRatio(DEFAULT_PORTAL_BACKGROUND, PORTAL_BRAND_INK)
    expect(ratio).toBeGreaterThan(4.5)
    expect(portalBackgroundContrastOk(DEFAULT_PORTAL_BACKGROUND)).toBe(true)
  })

  it('fails contrast for light backgrounds against light brand ink', () => {
    expect(portalBackgroundContrastOk('#FFFFFF')).toBe(false)
    expect(portalBackgroundContrastOk('#F8FAFC')).toBe(false)
  })

  it('treats empty/invalid as ok (product default path)', () => {
    expect(portalBackgroundContrastOk('')).toBe(true)
    expect(portalBackgroundContrastOk('nope')).toBe(true)
  })

  it('respects a custom minRatio', () => {
    expect(portalBackgroundContrastOk('#334155', 21)).toBe(false)
    expect(portalBackgroundContrastOk('#334155', 3)).toBe(true)
  })
})
