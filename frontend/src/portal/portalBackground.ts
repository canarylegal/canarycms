/** Client-portal background colour helpers (hex wheel + text). */

export const DEFAULT_PORTAL_BACKGROUND = '#1E293B'
export const PORTAL_BRAND_INK = '#F8FAFC'

const HEX6 = /^#([0-9A-Fa-f]{6})$/
const HEX3 = /^#([0-9A-Fa-f]{3})$/

/** Canonical `#RRGGBB` or `null` for product default / empty. */
export function normalizePortalBackgroundColor(raw: string | null | undefined): string | null {
  if (raw == null) return null
  let s = raw.trim()
  if (!s) return null
  if (!s.startsWith('#')) s = `#${s}`
  const m6 = HEX6.exec(s)
  if (m6) return `#${m6[1]!.toUpperCase()}`
  const m3 = HEX3.exec(s)
  if (m3) {
    const [a, b, c] = m3[1]!
    return `#${a}${a}${b}${b}${c}${c}`.toUpperCase()
  }
  return null
}

function srgbChannel(c: number): number {
  const x = c / 255
  return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4
}

export function relativeLuminance(hex: string): number {
  const h = normalizePortalBackgroundColor(hex) ?? DEFAULT_PORTAL_BACKGROUND
  const r = parseInt(h.slice(1, 3), 16)
  const g = parseInt(h.slice(3, 5), 16)
  const b = parseInt(h.slice(5, 7), 16)
  return 0.2126 * srgbChannel(r) + 0.7152 * srgbChannel(g) + 0.0722 * srgbChannel(b)
}

export function contrastRatio(a: string, b: string): number {
  const l1 = relativeLuminance(a)
  const l2 = relativeLuminance(b)
  const lighter = Math.max(l1, l2)
  const darker = Math.min(l1, l2)
  return (lighter + 0.05) / (darker + 0.05)
}

/** Light brand title ink must stay readable on the portal canvas. */
export function portalBackgroundContrastOk(bg: string, minRatio = 4.5): boolean {
  const n = normalizePortalBackgroundColor(bg)
  if (!n) return true
  return contrastRatio(n, PORTAL_BRAND_INK) >= minRatio
}
