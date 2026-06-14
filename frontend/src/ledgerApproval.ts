import type { LedgerEntryOut, LedgerPermissionsOut, LedgerPostCreate } from './types'

export type PendingLedgerApprovalRow = {
  pair_id: string
  case_id?: string
  client_direction?: string | null
  office_direction?: string | null
  is_anticipated?: boolean
  anticipated_for_date?: string | null
}

export function hasLedgerPostPrivilege(perm: LedgerPermissionsOut | null | undefined): boolean {
  return Boolean(perm?.can_post_client || perm?.can_post_office)
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

export function canApprovePendingLedgerRow(
  row: PendingLedgerApprovalRow,
  perm: LedgerPermissionsOut | null | undefined,
): boolean {
  if (!perm) return false
  if (row.is_anticipated) {
    if (row.client_direction && !perm.can_post_client) return false
    if (row.office_direction && !perm.can_post_office) return false
    return Boolean(row.client_direction || row.office_direction)
  }
  return Boolean(perm.can_approve_ledger)
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
