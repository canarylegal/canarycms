export type CaseContextMenuActionKind = 'open' | 'accounts' | 'convert' | 'close'

export function buildCaseContextMenuActions(
  variant: 'main' | 'quotes',
  caseStatus: string | undefined,
): CaseContextMenuActionKind[] {
  const actions: CaseContextMenuActionKind[] = ['open']
  if (variant === 'quotes') {
    if (caseStatus === 'quote') actions.push('convert')
    if (caseStatus === 'quote') actions.push('close')
  } else {
    actions.push('accounts')
  }
  return actions
}

export function scrollCaseRowIntoView(caseId: string) {
  const el = document.querySelector(`[data-case-row-id="${CSS.escape(caseId)}"]`)
  el?.scrollIntoView({ block: 'nearest' })
}
