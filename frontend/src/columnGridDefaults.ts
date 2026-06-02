/** Proportional column grids used before server-persisted pixel widths (see index.css). */

export const MAIN_MENU_CASES_TABLE_GRID =
  'minmax(0, 10fr) minmax(0, 26.25fr) minmax(0, 34.375fr) minmax(0, 18.125fr) minmax(0, 11.25fr)'

/** Quotes list uses the same five-column grid as the main menu (Source replaces Status). */
export const QUOTES_MENU_CASES_TABLE_GRID = MAIN_MENU_CASES_TABLE_GRID

export const TASKS_MENU_TABLE_GRID =
  'minmax(0, 8.768fr) minmax(0, 6.427fr) minmax(0, 8.768fr) minmax(0, 20.459fr) minmax(0, 30fr) minmax(0, 18.267fr) minmax(0, 7.311fr)'

export const CONTACTS_TABLE_GRID =
  'minmax(0, 90fr) minmax(0, 70fr) minmax(0, 70fr) minmax(0, 70fr)'

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
