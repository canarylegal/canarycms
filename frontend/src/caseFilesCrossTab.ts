/** Used with the `storage` event so other tabs can refresh when case files change. */

export const CASE_FILES_STORAGE_KEY = 'canary.caseFilesSignal'

export type CanaryComposePublishedMessage = {
  type: 'canary-compose-published'
  caseId: string
  fileId: string
}

export type CanaryComposeDiscardedMessage = {
  type: 'canary-compose-discarded'
  caseId: string
  fileId: string
}

export function isCanaryComposePublishedMessage(data: unknown): data is CanaryComposePublishedMessage {
  if (!data || typeof data !== 'object') return false
  const d = data as Record<string, unknown>
  return (
    d.type === 'canary-compose-published' &&
    typeof d.caseId === 'string' &&
    typeof d.fileId === 'string'
  )
}

export function isCanaryComposeDiscardedMessage(data: unknown): data is CanaryComposeDiscardedMessage {
  if (!data || typeof data !== 'object') return false
  const d = data as Record<string, unknown>
  return (
    d.type === 'canary-compose-discarded' &&
    typeof d.caseId === 'string' &&
    typeof d.fileId === 'string'
  )
}

export function signalCaseFilesChanged(caseId: string): void {
  try {
    localStorage.setItem(CASE_FILES_STORAGE_KEY, JSON.stringify({ caseId, t: Date.now() }))
  } catch {
    /* private mode / quota */
  }
}
