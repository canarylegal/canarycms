/** Proportional column grids used before server-persisted pixel widths (see index.css). */

export const MAIN_MENU_CASES_TABLE_GRID =
  'minmax(0, 10fr) minmax(0, 30fr) minmax(0, 35fr) minmax(0, 20fr) minmax(0, 5fr)'

export const TASKS_MENU_TABLE_GRID =
  'minmax(0, 8.768fr) minmax(0, 6.427fr) minmax(0, 8.768fr) minmax(0, 20.459fr) minmax(0, 30fr) minmax(0, 18.267fr) minmax(0, 7.311fr)'

export const CONTACTS_TABLE_GRID =
  'minmax(0, 90fr) minmax(0, 70fr) minmax(0, 70fr) minmax(0, 70fr)'

/** Pixel defaults auto-filled on first deploy; treat as “not customized”. */
export const LEGACY_AUTO_MAIN_MENU_COLUMN_WIDTHS = [110, 240, 300, 180, 100] as const
export const LEGACY_AUTO_TASKS_MENU_COLUMN_WIDTHS = [90, 66, 90, 210, 300, 183, 73] as const
export const LEGACY_AUTO_CONTACTS_COLUMN_WIDTHS = [270, 210, 210, 210] as const

export function effectiveColumnWidths(
  widths: number[],
  expected: number,
  legacyAuto: readonly number[],
): number[] | undefined {
  if (widths.length !== expected) return undefined
  if (legacyAuto.length === expected && widths.every((w, i) => w === legacyAuto[i]!)) return undefined
  return widths
}
