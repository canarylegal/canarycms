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

/** One staff lookup table per list calculation; preserve first-match semantics. */
export function buildFeeEarnerLabels(users: UserSummary[]): Map<string, string> {
  const labels = new Map<string, string>()
  for (const user of users) {
    const id = user.id
    if (!labels.has(id)) labels.set(id, user.display_name)
  }
  return labels
}

export function caseMatchesMainMenuSearch(c: CaseOut, users: UserSummary[], search: string): boolean {
  const s = search.trim().toLowerCase()
  return !s || caseMatchesSearchLabel(c, feeEarnerLabel(c, users), s)
}

function caseMatchesSearchLabel(c: CaseOut, fe: string, s: string): boolean {
  if (!s) return true
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
  const s = search.trim().toLowerCase()
  const labels = buildFeeEarnerLabels(users)
  const label = (c: CaseOut) => c.fee_earner_user_id == null ? '—' : labels.get(c.fee_earner_user_id) ?? '—'
  const pool = filters.quotesOnlyMatters
    ? cases.filter((c) => c.status === 'quote' || c.status === 'quote_closed')
    : filters.excludeQuoteMatters
      ? cases.filter((c) => c.status !== 'quote' && c.status !== 'quote_closed')
      : cases
  const filtered = s
    ? pool.filter((c) => caseMatchesSearchLabel(c, label(c), s))
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
              ? label(a)
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
              ? label(b)
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
