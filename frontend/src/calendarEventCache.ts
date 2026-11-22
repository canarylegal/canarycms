// Calendar contents must not survive a session boundary in browser storage.
// Keep this cleanup for tabs carrying caches from earlier versions.
export const CALENDAR_SESSION_RESET = 'canary:calendar-session-reset'
export function invalidateCalendarEventCache(): void {
  try {
    const keys: string[] = []
    for (let i = 0; i < sessionStorage.length; i += 1) {
      const key = sessionStorage.key(i)
      if (key?.startsWith('canary-calendar-events:')) keys.push(key)
    }
    for (const key of keys) sessionStorage.removeItem(key)
  } catch { /* Storage can be unavailable; still discard in-memory events. */ }
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(CALENDAR_SESSION_RESET))
}
// Purge legacy data as soon as this module loads, including unauthenticated pages.
invalidateCalendarEventCache()
