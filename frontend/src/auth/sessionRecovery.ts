export const SESSION_EXPIRED = 'canary:session-expired'
let authenticatedUserId: string | null = null
export function rememberSessionUser(id: string) { authenticatedUserId = id }
export function sessionUserId() { return authenticatedUserId }
export function signalSessionExpired() {
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(SESSION_EXPIRED))
}
