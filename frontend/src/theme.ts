/** Appearance preferences: server is source of truth when signed in; localStorage caches for boot/editor tabs. */

import type { UserAppearanceOut } from './types'

const KEYS = {
  font: 'canary.fontFamily',
  accent: 'canary.accentColor',
  mode: 'canary.colorMode',
  pageBg: 'canary.pageBackground',
} as const

/** Brand canary yellow — primary action colour (dark ink on buttons). */
export const DEFAULT_ACCENT = '#f0d010'
/** Stored in ``appearance_accent`` to select slate navigation chrome (primary buttons stay yellow). */
export const SLATE_CHROME_ACCENT = '#1e293b'
export type ChromeStyle = 'canary' | 'slate'

/** Default light-theme page backdrop (matches `index.css` :root pale wash). */
export const DEFAULT_PAGE_BG = '#e8edf5'
/** Default dark-theme page backdrop (matches `index.css` `html.dark`). */
export const DARK_DEFAULT_PAGE_BG = '#0f172a'

export type ThemePreferences = {
  font: string
  accent: string
  mode: 'light' | 'dark'
  pageBg: string
}

export function chromeStyleFromAccent(accent: string): ChromeStyle {
  return accent.trim().toLowerCase() === SLATE_CHROME_ACCENT.toLowerCase() ? 'slate' : 'canary'
}

export function accentForChromeStyle(chrome: ChromeStyle): string {
  return chrome === 'slate' ? SLATE_CHROME_ACCENT : DEFAULT_ACCENT
}

/** Quick picks restored in Appearance — navigation chrome only (buttons stay Canary yellow). */
export const CHROME_STYLE_OPTIONS: { id: ChromeStyle; label: string; swatch: string; hint: string }[] = [
  {
    id: 'canary',
    label: 'Canary navy',
    swatch: '#172554',
    hint: 'Current navigation and ribbon colour',
  },
  {
    id: 'slate',
    label: 'Slate',
    swatch: '#1e293b',
    hint: 'Earlier darker grey-blue chrome',
  },
]

function hexToRgb(hex: string): { r: number; g: number; b: number } | null {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim())
  if (!m) return null
  const n = parseInt(m[1], 16)
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 }
}

function srgbToLinear(c: number): number {
  return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)
}

/** WCAG relative luminance for sRGB hex (0–1). */
function relativeLuminance(hex: string): number {
  const rgb = hexToRgb(hex)
  if (!rgb) return 0.2
  const [r, g, b] = [rgb.r / 255, rgb.g / 255, rgb.b / 255].map(srgbToLinear)
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

/** Readable foreground on a flat ``hex`` background (for top bar buttons that use ``--page-bg``). */
function textOnPageBackground(hex: string): string {
  return relativeLuminance(hex) > 0.45 ? '#0f172a' : '#f8fafc'
}

export function themeFromAppearance(a: UserAppearanceOut): ThemePreferences {
  return {
    font: a.font ?? '',
    accent: a.accent?.trim() || DEFAULT_ACCENT,
    mode: a.mode === 'dark' ? 'dark' : 'light',
    pageBg: a.page_bg ?? '',
  }
}

export function applyThemePreferences(p: ThemePreferences): void {
  const root = document.documentElement
  const mode = p.mode === 'dark' ? 'dark' : 'light'
  // Dark mode always uses slate chrome; Canary navy is light-mode only.
  const chrome: ChromeStyle = mode === 'dark' ? 'slate' : chromeStyleFromAccent(p.accent)
  // Keep action buttons on Canary yellow for both chrome packs.
  const accent = DEFAULT_ACCENT

  root.dataset.canaryChrome = chrome

  root.style.setProperty('--primary', accent)
  const rgb = hexToRgb(accent)
  if (rgb) {
    root.style.setProperty('--primary-rgb', `${rgb.r}, ${rgb.g}, ${rgb.b}`)
  }
  root.style.setProperty('--text-on-primary', textOnPageBackground(accent))

  if (p.font.trim()) {
    root.style.setProperty('--app-font-stack', p.font.trim())
  } else {
    root.style.removeProperty('--app-font-stack')
  }

  root.classList.toggle('dark', mode === 'dark')

  const pageHex = /^#[0-9a-fA-F]{6}$/.test(p.pageBg.trim()) ? p.pageBg.trim() : ''
  if (pageHex) {
    root.style.setProperty('--page-bg', pageHex)
    root.style.setProperty('--bg', pageHex)
    root.style.setProperty('--page-gradient', pageHex)
  } else {
    root.style.removeProperty('--page-bg')
    root.style.removeProperty('--bg')
    root.style.removeProperty('--page-gradient')
  }

  const effectivePageBg = pageHex || (mode === 'dark' ? DARK_DEFAULT_PAGE_BG : DEFAULT_PAGE_BG)
  root.style.setProperty('--text-on-page-bg', textOnPageBackground(effectivePageBg))
}

export function applyStoredTheme(): void {
  applyThemePreferences(getThemePreferences())
}

export function getThemePreferences(): ThemePreferences {
  return {
    font: localStorage.getItem(KEYS.font) ?? '',
    accent: localStorage.getItem(KEYS.accent) ?? DEFAULT_ACCENT,
    mode: (localStorage.getItem(KEYS.mode) === 'dark' ? 'dark' : 'light') as 'light' | 'dark',
    pageBg: localStorage.getItem(KEYS.pageBg) ?? '',
  }
}

export function saveThemePreferences(p: ThemePreferences): void {
  if (p.font.trim()) localStorage.setItem(KEYS.font, p.font.trim())
  else localStorage.removeItem(KEYS.font)
  localStorage.setItem(KEYS.accent, p.accent.trim() || DEFAULT_ACCENT)
  localStorage.setItem(KEYS.mode, p.mode)
  const pg = p.pageBg.trim()
  if (pg && /^#[0-9a-fA-F]{6}$/.test(pg)) localStorage.setItem(KEYS.pageBg, pg)
  else localStorage.removeItem(KEYS.pageBg)
  applyThemePreferences(p)
}

export const FONT_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'App default (DM Sans)' },
  { value: '"DM Sans", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif', label: 'DM Sans' },
  { value: 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif', label: 'System UI' },
  { value: '"Open Sans", "Helvetica Neue", Helvetica, Arial, sans-serif', label: 'Open Sans (if installed)' },
  { value: '"Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif', label: 'Segoe / Roboto' },
  { value: 'Verdana, Geneva, sans-serif', label: 'Verdana' },
  { value: 'Tahoma, Geneva, Verdana, sans-serif', label: 'Tahoma' },
  { value: '"Trebuchet MS", "Lucida Grande", sans-serif', label: 'Trebuchet MS' },
  { value: 'Georgia, "Times New Roman", Times, serif', label: 'Serif (Georgia)' },
  { value: '"Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif', label: 'Palatino / Book Antiqua' },
  { value: '"Source Serif 4", Georgia, "Times New Roman", serif', label: 'Source Serif (if installed)' },
  { value: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace', label: 'Monospace' },
  { value: 'Consolas, "Liberation Mono", Menlo, Courier, monospace', label: 'Code (Consolas / Liberation Mono)' },
]

/** Quick picks for accent — any hex still works in the field above. */
export const ACCENT_COLOR_PRESETS: { label: string; value: string }[] = [
  { label: 'Canary', value: '#f0d010' },
  { label: 'Blue', value: '#2563eb' },
  { label: 'Sky', value: '#0284c7' },
  { label: 'Teal', value: '#0d9488' },
  { label: 'Green', value: '#16a34a' },
  { label: 'Amber', value: '#d97706' },
  { label: 'Rose', value: '#e11d48' },
  { label: 'Violet', value: '#7c3aed' },
  { label: 'Indigo', value: '#4f46e5' },
  { label: 'Slate', value: '#475569' },
]

/** Quick picks for page background — empty string = built‑in default for light/dark mode. */
export const PAGE_BG_COLOR_PRESETS: { label: string; value: string }[] = [
  { label: 'App default', value: '' },
  { label: 'Pale wash', value: '#e8edf5' },
  { label: 'Navy', value: '#1e3a8a' },
  { label: 'Deep slate', value: '#0f172a' },
  { label: 'Charcoal', value: '#1c1917' },
  { label: 'Forest', value: '#14532d' },
  { label: 'Wine', value: '#4c0519' },
  { label: 'Warm grey', value: '#44403c' },
  { label: 'Soft blue-grey', value: '#334155' },
]
