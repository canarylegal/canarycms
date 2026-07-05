import type { LedgerEntryOut, LedgerPermissionsOut, LedgerPostCreate } from './types'

export type PendingLedgerApprovalRow = {
  pair_id: string
  case_id?: string
  client_direction?: string | null
  office_direction?: string | null
  is_anticipated?: boolean
  anticipated_for_date?: string | null
  posted_by_user_id?: string | null
}

export function hasLedgerPostPrivilege(perm: LedgerPermissionsOut | null | undefined): boolean {
  return Boolean(perm?.can_post_client || perm?.can_post_office)
}

export function hasPostAnticipatedPrivilege(perm: LedgerPermissionsOut | null | undefined): boolean {
  return Boolean(perm?.can_post_anticipated)
}

export function canPostAnticipatedLedger(perm: LedgerPermissionsOut | null | undefined): boolean {
  return hasPostAnticipatedPrivilege(perm)
}

export function canPostActualLedger(
  form: Pick<LedgerPostCreate, 'client_direction' | 'office_direction'>,
  perm: LedgerPermissionsOut | null | undefined,
): boolean {
  if (!perm) return false
  if (form.client_direction && !perm.can_post_client) return false
  if (form.office_direction && !perm.can_post_office) return false
  return Boolean(form.client_direction || form.office_direction)
}

export function canApproveAnticipatedLedgerRow(
  row: PendingLedgerApprovalRow,
  perm: LedgerPermissionsOut | null | undefined,
): boolean {
  if (!perm || !row.is_anticipated) return false
  if (row.client_direction && !perm.can_post_client) return false
  if (row.office_direction && !perm.can_post_office) return false
  return Boolean(row.client_direction || row.office_direction)
}

export function canApprovePendingLedgerRow(
  row: PendingLedgerApprovalRow,
  perm: LedgerPermissionsOut | null | undefined,
): boolean {
  if (row.is_anticipated) return canApproveAnticipatedLedgerRow(row, perm)
  return canEditPendingLedgerRow(row, perm)
}

/** Edit before confirming pending (non-anticipated) postings, or amend anticipated ones. */
export function canEditPendingLedgerRow(
  row: PendingLedgerApprovalRow,
  perm: LedgerPermissionsOut | null | undefined,
  currentUserId?: string | null,
): boolean {
  if (row.is_anticipated) {
    if (currentUserId && row.posted_by_user_id === currentUserId) return true
    return Boolean(perm?.can_post_anticipated)
  }
  if (!perm) return false
  return Boolean(perm.can_approve_ledger)
}

export function canAmendAnticipatedLedgerRow(
  row: PendingLedgerApprovalRow,
  perm: LedgerPermissionsOut | null | undefined,
  currentUserId?: string | null,
): boolean {
  if (!row.is_anticipated) return false
  return canEditPendingLedgerRow(row, perm, currentUserId)
}

export function canCancelAnticipatedLedgerRow(
  row: PendingLedgerApprovalRow,
  perm: LedgerPermissionsOut | null | undefined,
  currentUserId?: string | null,
): boolean {
  if (!row.is_anticipated) return false
  if (currentUserId && row.posted_by_user_id === currentUserId) return true
  if (perm?.can_post_anticipated) return true
  if (row.client_direction && perm?.can_post_client) return true
  if (row.office_direction && perm?.can_post_office) return true
  return false
}

export function canApproveLedgerPair(
  pairId: string,
  entries: LedgerEntryOut[],
  perm: LedgerPermissionsOut | null | undefined,
): boolean {
  const legs = entries.filter((e) => e.pair_id === pairId)
  if (!legs.length) return false
  const clientLeg = legs.find((e) => e.account_type === 'client')
  const officeLeg = legs.find((e) => e.account_type === 'office')
  return canApprovePendingLedgerRow(
    {
      pair_id: pairId,
      client_direction: clientLeg?.direction ?? null,
      office_direction: officeLeg?.direction ?? null,
      is_anticipated: legs.some((e) => e.is_anticipated),
    },
    perm,
  )
}

export function pendingLedgerRowFromPair(
  pairId: string,
  entries: LedgerEntryOut[],
): PendingLedgerApprovalRow {
  const legs = entries.filter((e) => e.pair_id === pairId)
  const clientLeg = legs.find((e) => e.account_type === 'client')
  const officeLeg = legs.find((e) => e.account_type === 'office')
  const leg = legs[0]
  return {
    pair_id: pairId,
    client_direction: clientLeg?.direction ?? null,
    office_direction: officeLeg?.direction ?? null,
    is_anticipated: legs.some((e) => e.is_anticipated),
    posted_by_user_id: leg?.posted_by_user_id ?? null,
  }
}

export function canAmendLedgerPair(
  pairId: string,
  entries: LedgerEntryOut[],
  perm: LedgerPermissionsOut | null | undefined,
  currentUserId?: string | null,
): boolean {
  const row = pendingLedgerRowFromPair(pairId, entries)
  if (row.is_anticipated) {
    return canAmendAnticipatedLedgerRow(row, perm, currentUserId)
  }
  return canEditPendingLedgerRow(row, perm)
}

export function canCancelLedgerPair(
  pairId: string,
  entries: LedgerEntryOut[],
  perm: LedgerPermissionsOut | null | undefined,
  currentUserId?: string | null,
): boolean {
  const row = pendingLedgerRowFromPair(pairId, entries)
  if (row.is_anticipated) {
    return canCancelAnticipatedLedgerRow(row, perm, currentUserId)
  }
  return canEditPendingLedgerRow(row, perm)
}

export type PendingLedgerAccountFilter = 'all' | 'client' | 'office'
export type PendingLedgerDirectionFilter = 'all' | 'credit' | 'debit'

export function matchesPendingLedgerFilters(
  row: PendingLedgerApprovalRow,
  account: PendingLedgerAccountFilter,
  direction: PendingLedgerDirectionFilter,
): boolean {
  if (account === 'client' && !row.client_direction) return false
  if (account === 'office' && !row.office_direction) return false
  if (direction === 'all') return true
  if (account === 'client') return row.client_direction === direction
  if (account === 'office') return row.office_direction === direction
  return row.client_direction === direction || row.office_direction === direction
}

export function isLedgerEntryAnticipated(e: LedgerEntryOut): boolean {
  return e.is_anticipated === true
}

export function isLedgerEntryPending(e: LedgerEntryOut): boolean {
  if (e.is_approved === true) return false
  if (e.is_approved === false) return true
  return (e.description ?? '').toLowerCase().includes('pending approval')
}

export function ledgerEntryAffectsBalance(e: LedgerEntryOut): boolean {
  return !isLedgerEntryPending(e)
}
