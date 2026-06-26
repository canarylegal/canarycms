import type { CasePropertyPayload, MatterSubTypeOut } from '../types'

export function subTypeHasPropertyMenu(sub: MatterSubTypeOut | null | undefined): boolean {
  if (!sub?.menus?.length) return false
  return sub.menus.some((m) => m.name.trim().toLowerCase() === 'property')
}

export function blankPropertyPayload(): CasePropertyPayload {
  return {
    is_non_postal: false,
    uk: {},
    free_lines: ['', '', '', '', '', ''],
    title_numbers: [],
    tenure: null,
    existing_lender_case_contact_id: null,
    charge_date: null,
  }
}

function propertyPayloadAddressLines(p: CasePropertyPayload): string[] {
  if (p.is_non_postal) {
    return p.free_lines.map((ln) => (ln || '').trim()).filter(Boolean)
  }
  return [
    p.uk.line1,
    p.uk.line2,
    p.uk.town,
    p.uk.county,
    p.uk.postcode,
    p.uk.country,
  ]
    .map((ln) => (ln || '').trim())
    .filter(Boolean)
}

/** Join address lines for matter description: comma+space, except adjacent to a digits-only segment (use space). */
export function joinAddressLinesForMatterDescription(lines: string[]): string {
  const parts = lines.map((s) => s.trim()).filter(Boolean)
  if (parts.length === 0) return ''
  let out = parts[0]!
  for (let i = 1; i < parts.length; i++) {
    const prev = parts[i - 1]!
    const cur = parts[i]!
    const prevNumeric = /^\d+$/.test(prev)
    const curNumeric = /^\d+$/.test(cur)
    const sep = prevNumeric || curNumeric ? ' ' : ', '
    out += sep + cur
  }
  return out
}

/** Pre-fix (Admin) + formatted property address for new matter description. */
export function buildNewMatterDescription(
  prefix: string | null | undefined,
  property: CasePropertyPayload | null,
): string {
  const pre = (prefix ?? '').trim()
  const addr = property ? joinAddressLinesForMatterDescription(propertyPayloadAddressLines(property)) : ''
  if (pre && addr) return `${pre} ${addr}`
  if (pre) return pre
  return addr
}
