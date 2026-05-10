/** Stable ``window.open`` names so a second open focuses the existing OnlyOffice tab instead of spawning another. */

export function onlyofficeCaseEditorWindowTarget(caseId: string, fileId: string): string {
  return `canary-oo-case-${caseId}-${fileId}`
}

export function onlyofficePrecedentEditorWindowTarget(precedentId: string): string {
  return `canary-oo-precedent-${precedentId}`
}
