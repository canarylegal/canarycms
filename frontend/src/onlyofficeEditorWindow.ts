/** Stable ``window.open`` names so a second open focuses the existing OnlyOffice window. */

/** Nearly fill the available screen; browsers may still clamp popup size. */
export function onlyofficeEditorWindowFeatures(): string {
  const availW = window.screen?.availWidth ?? 1600
  const availH = window.screen?.availHeight ?? 1000
  // Leave a slim margin so the window does not look stuck to the OS chrome edge.
  const width = Math.max(1100, Math.min(availW - 24, Math.round(availW * 0.96)))
  const height = Math.max(720, Math.min(availH - 48, Math.round(availH * 0.94)))
  const left = Math.max(0, Math.round((availW - width) / 2))
  const top = Math.max(0, Math.round((availH - height) / 2))
  return `popup=yes,width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes`
}

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
    onlyofficeEditorWindowFeatures(),
  )
}

export function openOnlyOfficePrecedentEditor(precedentId: string): Window | null {
  return window.open(
    `/editor/precedent/${precedentId}`,
    onlyofficePrecedentEditorWindowTarget(precedentId),
    onlyofficeEditorWindowFeatures(),
  )
}

export function onlyofficeFirmLetterheadEditorWindowTarget(kind: 'letterhead' | 'quote_letterhead'): string {
  return kind === 'letterhead' ? 'canary-oo-firm-letterhead' : 'canary-oo-firm-quote-letterhead'
}

export function openOnlyOfficeFirmLetterheadEditor(kind: 'letterhead' | 'quote_letterhead'): Window | null {
  const path = kind === 'letterhead' ? '/editor/firm-letterhead' : '/editor/firm-quote-letterhead'
  return window.open(
    path,
    onlyofficeFirmLetterheadEditorWindowTarget(kind),
    onlyofficeEditorWindowFeatures(),
  )
}

export function onlyofficeFeeScaleEditorWindowTarget(feeScaleId: string): string {
  return `canary-oo-fee-scale-${feeScaleId}`
}

export function openOnlyOfficeFeeScaleEditor(feeScaleId: string): Window | null {
  return window.open(
    `/editor/fee-scale/${feeScaleId}`,
    onlyofficeFeeScaleEditorWindowTarget(feeScaleId),
    onlyofficeEditorWindowFeatures(),
  )
}
