import { formatCaseStatusLabel } from './types'
import type { CaseOut, UserSummary } from './types'
import type { MainMenuCaseStatusFilter } from './userUiPreferences'

export function matterTypeLabel(c: CaseOut): string {
  const parts = [c.matter_head_type_name, c.matter_sub_type_name].filter(Boolean)
  return parts.length ? parts.join(' · ') : '—'
}

export function feeEarnerLabel(c: CaseOut, users: UserSummary[]) {
  const u = users.find((x) => x.id === c.fee_earner_user_id)
  return u?.display_name ?? '—'
}

export function caseMatchesMainMenuSearch(c: CaseOut, users: UserSummary[], search: string): boolean {
  const s = search.trim().toLowerCase()
  if (!s) return true
  const fe = feeEarnerLabel(c, users)
  const parts = [
    c.case_number,
    c.client_name ?? '',
    c.matter_description ?? '',
    formatCaseStatusLabel(c.status),
    fe,
    c.source_name ?? '',
  ]
  return parts.join(' ').toLowerCase().includes(s)
}

export function filterMainMenuCases(
  cases: CaseOut[],
  matterTypes: string[],
  feeEarnerUserIds: string[],
  caseStatuses: MainMenuCaseStatusFilter[],
): CaseOut[] {
  let result = cases
  if (matterTypes.length > 0) {
    result = result.filter((c) => matterTypes.includes(matterTypeLabel(c)))
  }
  if (feeEarnerUserIds.length > 0) {
    result = result.filter((c) => c.fee_earner_user_id && feeEarnerUserIds.includes(c.fee_earner_user_id))
  }
  if (caseStatuses.length > 0) {
    result = result.filter((c) => caseStatuses.includes(c.status as MainMenuCaseStatusFilter))
  }
  return result
}

export function buildCaseTableRows(
  cases: CaseOut[],
  users: UserSummary[],
  search: string,
  filters: {
    matterTypes: string[]
    feeEarnerUserIds: string[]
    caseStatuses: MainMenuCaseStatusFilter[]
    excludeQuoteMatters?: boolean
    quotesOnlyMatters?: boolean
  },
  sortKey: 'reference' | 'client' | 'matter' | 'feeEarner' | 'status' | 'source' | 'created',
  sortDir: 'asc' | 'desc',
): CaseOut[] {
  const s = search.trim()
  const pool = filters.quotesOnlyMatters
    ? cases.filter((c) => c.status === 'quote' || c.status === 'quote_closed')
    : filters.excludeQuoteMatters
      ? cases.filter((c) => c.status !== 'quote' && c.status !== 'quote_closed')
      : cases
  const filtered = s
    ? pool.filter((c) => caseMatchesMainMenuSearch(c, users, search))
    : filterMainMenuCases(pool, filters.matterTypes, filters.feeEarnerUserIds, filters.caseStatuses)
  const dir = sortDir === 'asc' ? 1 : -1
  return [...filtered].sort((a, b) => {
    const av =
      sortKey === 'reference'
        ? a.case_number
        : sortKey === 'client'
          ? a.client_name ?? ''
          : sortKey === 'matter'
            ? a.matter_description ?? ''
            : sortKey === 'feeEarner'
              ? feeEarnerLabel(a, users)
              : sortKey === 'status'
                ? a.status
                : sortKey === 'source'
                  ? a.source_name ?? ''
                : sortKey === 'created'
                  ? a.created_at
                  : ''
    const bv =
      sortKey === 'reference'
        ? b.case_number
        : sortKey === 'client'
          ? b.client_name ?? ''
          : sortKey === 'matter'
            ? b.matter_description ?? ''
            : sortKey === 'feeEarner'
              ? feeEarnerLabel(b, users)
              : sortKey === 'status'
                ? b.status
                : sortKey === 'source'
                  ? b.source_name ?? ''
                : sortKey === 'created'
                  ? b.created_at
                  : ''
    return String(av).localeCompare(String(bv)) * dir
  })
}
