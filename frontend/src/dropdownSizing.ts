/** Show full list without scroll when option count is at or below this (see ``dropdownMenu--fitContent``). */
export const DROPDOWN_FIT_CONTENT_MAX_ITEMS = 12

export function dropdownMenuFitsContent(itemCount: number): boolean {
  return itemCount > 0 && itemCount <= DROPDOWN_FIT_CONTENT_MAX_ITEMS
}

export function joinClassNames(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ')
}

/** Portal / absolute dropdown menus (``SingleSelectDropdown``, filter pickers, …). */
export function dropdownMenuClassName(base: string, itemCount: number): string {
  return joinClassNames(base, dropdownMenuFitsContent(itemCount) && 'dropdownMenu--fitContent')
}

/** Inline scroll regions (search result lists, access pickers, …). */
export function scrollPanelClassName(base: string, itemCount: number): string {
  return joinClassNames(base, dropdownMenuFitsContent(itemCount) && 'scrollPanel--fitContent')
}
