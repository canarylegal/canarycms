export class PortalRequestError extends Error {
  readonly status: number
  constructor(message: string, status: number) { super(message); this.status = status }
}
export function portalRequestError(status: number, message: string, token: string) {
  if (status === 401 && token) {
    window.dispatchEvent(new CustomEvent('portal-session-expired', { detail: { token, message } }))
  }
  return new PortalRequestError(message, status)
}
export type PortalDraft = { contactId: string; submissionId: string; values: Record<string, unknown> }
