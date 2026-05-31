/** Stable ``window.open`` names so a second open focuses the existing OnlyOffice window. */

export const ONLYOFFICE_EDITOR_WINDOW_FEATURES =
  'popup=yes,width=1280,height=900,left=40,top=32,resizable=yes,scrollbars=yes'

export function onlyofficeCaseEditorWindowTarget(caseId: string, fileId: string): string {
  return `canary-oo-case-${caseId}-${fileId}`
}

export function onlyofficePrecedentEditorWindowTarget(precedentId: string): string {
  return `canary-oo-precedent-${precedentId}`
}

export function openOnlyOfficeCaseEditor(caseId: string, fileId: string): Window | null {
  return window.open(
    `/editor/${caseId}/${fileId}`,
    onlyofficeCaseEditorWindowTarget(caseId, fileId),
    ONLYOFFICE_EDITOR_WINDOW_FEATURES,
  )
}

export function openOnlyOfficePrecedentEditor(precedentId: string): Window | null {
  return window.open(
    `/editor/precedent/${precedentId}`,
    onlyofficePrecedentEditorWindowTarget(precedentId),
    ONLYOFFICE_EDITOR_WINDOW_FEATURES,
  )
}

export function onlyofficeFeeScaleEditorWindowTarget(feeScaleId: string): string {
  return `canary-oo-fee-scale-${feeScaleId}`
}

export function openOnlyOfficeFeeScaleEditor(feeScaleId: string): Window | null {
  return window.open(
    `/editor/fee-scale/${feeScaleId}`,
    onlyofficeFeeScaleEditorWindowTarget(feeScaleId),
    ONLYOFFICE_EDITOR_WINDOW_FEATURES,
  )
}
