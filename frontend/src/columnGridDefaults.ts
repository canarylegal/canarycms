/** Proportional column grids with readable minimum widths (see index.css). */

export const MAIN_MENU_CASES_TABLE_GRID =
  'minmax(88px, 10fr) minmax(140px, 26.25fr) minmax(180px, 34.375fr) minmax(120px, 18.125fr) minmax(90px, 11.25fr)'

/** Quotes list uses the same five-column grid as the main menu (Source replaces Status). */
export const QUOTES_MENU_CASES_TABLE_GRID = MAIN_MENU_CASES_TABLE_GRID

export const TASKS_MENU_TABLE_GRID =
  'minmax(90px, 8.768fr) minmax(64px, 6.427fr) minmax(80px, 8.768fr) minmax(140px, 20.459fr) minmax(180px, 30fr) minmax(120px, 18.267fr) minmax(80px, 7.311fr)'

export const CONTACTS_TABLE_GRID =
  'minmax(140px, 90fr) minmax(90px, 70fr) minmax(180px, 70fr) minmax(120px, 70fr)'

/** DocuSign envelope list: Sent · Status · Document · Recipients · Client · Reference · Sent by */
export const DOCUSIGN_TABLE_GRID =
  'minmax(100px, 13fr) minmax(90px, 11fr) minmax(160px, 22fr) minmax(160px, 22fr) minmax(120px, 14fr) minmax(80px, 8fr) minmax(90px, 10fr)'

/** Pixel defaults auto-filled on first deploy; treat as “not customized”. */
export const LEGACY_AUTO_MAIN_MENU_COLUMN_WIDTHS = [110, 165, 300, 130, 225] as const
export const LEGACY_AUTO_TASKS_MENU_COLUMN_WIDTHS = [90, 66, 90, 210, 300, 183, 73] as const
export const LEGACY_AUTO_CONTACTS_COLUMN_WIDTHS = [270, 210, 210, 210] as const

/** Prior shipped defaults; treat as unset so layout changes roll out cleanly. */
export const LEGACY_MAIN_MENU_COLUMN_WIDTH_PRESETS: readonly (readonly number[])[] = [
  [110, 165, 300, 130, 225],
  [110, 240, 240, 190, 150],
  [110, 240, 240, 240, 100],
  [110, 240, 300, 180, 100],
]

export function effectiveColumnWidths(
  widths: number[],
  expected: number,
  legacyAuto: readonly number[],
): number[] | undefined {
  if (widths.length !== expected) return undefined
  const presets = [legacyAuto, ...LEGACY_MAIN_MENU_COLUMN_WIDTH_PRESETS]
  if (presets.some((preset) => preset.length === expected && widths.every((w, i) => w === preset[i]!))) {
    return undefined
  }
  return widths
}
