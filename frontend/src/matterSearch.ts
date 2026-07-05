import type { CaseOut, UserSummary } from './types'
import { formatCaseStatusLabel, stripCaseNumberPrefix } from './types'

export const MATTER_PICKER_LIMIT = 50

export function feeEarnerLabel(c: CaseOut, users: Pick<UserSummary, 'id' | 'display_name'>[]): string {
  const u = users.find((x) => x.id === c.fee_earner_user_id)
  return u?.display_name ?? ''
}

export function matterPickerSummary(c: CaseOut): { primary: string; secondary: string | null } {
  const primary = c.case_number
  const bits = [c.client_name?.trim(), c.matter_description?.trim()].filter(Boolean) as string[]
  return { primary, secondary: bits.length ? bits.join(' · ') : null }
}

export function caseMatchesMatterSearch(
  c: CaseOut,
  users: Pick<UserSummary, 'id' | 'display_name'>[],
  search: string,
): boolean {
  const s = search.trim().toLowerCase()
  if (!s) return false
  const parts = [
    c.case_number,
    stripCaseNumberPrefix(c.case_number),
    c.client_name ?? '',
    c.matter_description ?? '',
    formatCaseStatusLabel(c.status),
    feeEarnerLabel(c, users),
    c.matter_head_type_name ?? '',
    c.matter_sub_type_name ?? '',
    c.source_name ?? '',
  ]
  return parts.join(' ').toLowerCase().includes(s)
}

export function filterCasesForMatterSearch(
  cases: CaseOut[],
  users: Pick<UserSummary, 'id' | 'display_name'>[],
  search: string,
  limit = MATTER_PICKER_LIMIT,
): CaseOut[] {
  const q = search.trim()
  if (!q) return []
  const sorted = [...cases].sort((a, b) => a.case_number.localeCompare(b.case_number))
  return sorted.filter((c) => caseMatchesMatterSearch(c, users, q)).slice(0, limit)
}
