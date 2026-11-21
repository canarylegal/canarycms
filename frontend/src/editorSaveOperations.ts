import { documentRequest, DocumentRequestError } from './case/documentRequests'

const OO_SAVE_POLL_MS = 300
type OoSaveStatusOut = { saved: boolean; version: number; state?: string }

export function ooForceSavePath(base: string, docKey: string, phase: 'arm' | 'command', attemptId?: string): string {
  const q = new URLSearchParams({ doc_key: docKey, phase })
  if (attemptId) q.set('attempt_id', attemptId)
  return `${base}?${q}`
}

export function ooSaveStatusPath(forceSaveUrl: string, baseVersion: number, attemptId?: string): string {
  const url = forceSaveUrl.replace(/\/oo-force-save$/, '/oo-save-status')
  return `${url}?base_version=${encodeURIComponent(String(baseVersion))}${attemptId ? `&attempt_id=${encodeURIComponent(attemptId)}` : ''}`
}

export async function pollOnlyofficeSaveConfirmed(
  statusUrl: string,
  baseVersion: number,
  token: string | undefined,
  timeoutMs: number,
): Promise<void> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      const st = await documentRequest<OoSaveStatusOut>(statusUrl, token, (res) => res.json(), {
        timeoutMs: Math.max(1, deadline - Date.now()), retryReads: false,
      })
      if (st.saved && st.version > baseVersion) return
      if (st.state === 'failed' || st.state === 'superseded') {
        throw new Error('This save was not confirmed. Keep the editor open and retry.')
      }
    } catch (error) {
      if (!(error instanceof DocumentRequestError) || !error.retryable) throw error
    }
    const remaining = deadline - Date.now()
    if (remaining > 0) await new Promise((r) => setTimeout(r, Math.min(OO_SAVE_POLL_MS, remaining)))
  }
  throw new Error('ONLYOFFICE forcesave did not confirm within the expected time.')
}
