import type { CalendarEventOut } from './types'

const STORAGE_PREFIX = 'canary-calendar-events:v1:'

export function calendarEventCacheKey(startStr: string, endStr: string, calendarSelectionKey: string): string {
  return `${STORAGE_PREFIX}${startStr}|${endStr}|${calendarSelectionKey}`
}

export function readCalendarEventCache(key: string): CalendarEventOut[] | null {
  try {
    const raw = sessionStorage.getItem(key)
    if (!raw) return null
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return null
    return parsed as CalendarEventOut[]
  } catch {
    return null
  }
}

export function writeCalendarEventCache(key: string, rows: CalendarEventOut[]): void {
  try {
    sessionStorage.setItem(key, JSON.stringify(rows))
  } catch {
    /* quota or private mode */
  }
}

export function invalidateCalendarEventCache(): void {
  try {
    const keys: string[] = []
    for (let i = 0; i < sessionStorage.length; i += 1) {
      const k = sessionStorage.key(i)
      if (k?.startsWith(STORAGE_PREFIX)) keys.push(k)
    }
    for (const k of keys) sessionStorage.removeItem(k)
  } catch {
    /* ignore */
  }
}
