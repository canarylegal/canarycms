import { invalidateCalendarEventCache } from '../calendarEventCache'
export const SESSION_EXPIRED = 'canary:session-expired'
let authenticatedUserId: string | null = null
export function rememberSessionUser(id: string) {
  if (id !== authenticatedUserId) invalidateCalendarEventCache()
  authenticatedUserId = id
}
export function sessionUserId() { return authenticatedUserId }
export function signalSessionExpired() {
  invalidateCalendarEventCache()
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(SESSION_EXPIRED))
}
