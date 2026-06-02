import { useCallback, useEffect, useRef, useState } from 'react'
import type { UserPublic } from './types'
import {
  DEFAULT_UI_PREFERENCES,
  legacyUiPreferenceOverrides,
  MENU_COLUMN_RESET_EVENT,
  normalizeUiPreferences,
  persistUserUiPreferences,
  readCachedUiPreferences,
  uiPreferencesEqual,
  writeCachedUiPreferences,
  type UserUiPreferences,
} from './userUiPreferences'

function prefValuesEqual<K extends keyof UserUiPreferences>(a: UserUiPreferences[K], b: UserUiPreferences[K]): boolean {
  if (Array.isArray(a) && Array.isArray(b)) return JSON.stringify(a) === JSON.stringify(b)
  return a === b
}

function columnWidthsCleared(prefs: UserUiPreferences): boolean {
  return (
    prefs.main_menu_column_widths.length === 0 &&
    prefs.tasks_menu_column_widths.length === 0 &&
    prefs.contacts_column_widths.length === 0
  )
}

function hadCustomColumnWidths(prefs: UserUiPreferences): boolean {
  return (
    prefs.main_menu_column_widths.length > 0 ||
    prefs.tasks_menu_column_widths.length > 0 ||
    prefs.contacts_column_widths.length > 0
  )
}

function writePrefsSnapshot(next: UserUiPreferences, serverSnapshotRef: { current: string }) {
  writeCachedUiPreferences(next)
  serverSnapshotRef.current = JSON.stringify(next)
}

export function useUserUiPreferences(me: UserPublic | null | undefined, token: string | null) {
  const migratedRef = useRef(false)
  const debounceRef = useRef<Partial<Record<keyof UserUiPreferences, ReturnType<typeof setTimeout>>>>({})
  const serverSnapshotRef = useRef('')
  const [prefs, setPrefs] = useState<UserUiPreferences>(() => readCachedUiPreferences())

  useEffect(() => {
    if (!me?.ui_preferences) return
    const server = normalizeUiPreferences(me.ui_preferences)
    const serverJson = JSON.stringify(server)
    if (serverJson === serverSnapshotRef.current) return

    setPrefs((prev) => {
      const pending = Object.entries(debounceRef.current)
        .filter(([, timer]) => timer != null)
        .map(([k]) => k as keyof UserUiPreferences)
      const localSnapshot = serverSnapshotRef.current
        ? normalizeUiPreferences(JSON.parse(serverSnapshotRef.current))
        : null

      if (pending.length > 0) {
        const overrides = Object.fromEntries(pending.map((k) => [k, prev[k]])) as Partial<UserUiPreferences>
        const next: UserUiPreferences = { ...server, ...overrides }
        writePrefsSnapshot(next, serverSnapshotRef)
        return next
      }

      // Incoming /auth/me prefs are stale relative to optimistic local edits — keep local state.
      if (localSnapshot && !uiPreferencesEqual(localSnapshot, server)) {
        const serverResetColumns = columnWidthsCleared(server) && hadCustomColumnWidths(localSnapshot)
        if (!serverResetColumns) {
          return prev
        }
      }

      if (uiPreferencesEqual(prev, server)) return prev
      writePrefsSnapshot(server, serverSnapshotRef)
      return server
    })
  }, [me?.ui_preferences])

  useEffect(() => {
    if (!token || !me || migratedRef.current) return
    const server = normalizeUiPreferences(me.ui_preferences)
    const legacy = legacyUiPreferenceOverrides()
    if (Object.keys(legacy).length === 0) return
    if (!uiPreferencesEqual(server, DEFAULT_UI_PREFERENCES)) return
    migratedRef.current = true
    void persistUserUiPreferences(token, legacy)
      .then((next) => {
        setPrefs(next)
        serverSnapshotRef.current = JSON.stringify(next)
      })
      .catch(() => {
        migratedRef.current = false
      })
  }, [me, token])

  useEffect(() => {
    const timers = debounceRef.current
    return () => {
      for (const t of Object.values(timers)) {
        if (t) clearTimeout(t)
      }
    }
  }, [])

  useEffect(() => {
    function onMenuColumnReset() {
      setPrefs((prev) => {
        const next: UserUiPreferences = {
          ...prev,
          main_menu_column_widths: [],
          tasks_menu_column_widths: [],
          contacts_column_widths: [],
        }
        writePrefsSnapshot(next, serverSnapshotRef)
        return next
      })
    }
    window.addEventListener(MENU_COLUMN_RESET_EVENT, onMenuColumnReset)
    return () => window.removeEventListener(MENU_COLUMN_RESET_EVENT, onMenuColumnReset)
  }, [])

  const persistPatch = useCallback(
    (patch: Partial<UserUiPreferences>) => {
      if (!token) return
      void persistUserUiPreferences(token, patch)
        .then((next) => {
          serverSnapshotRef.current = JSON.stringify(next)
        })
        .catch(() => {
          /* keep optimistic local state */
        })
    },
    [token],
  )

  const setPreference = useCallback(
    <K extends keyof UserUiPreferences>(key: K, value: UserUiPreferences[K]) => {
      setPrefs((prev) => {
        if (prefValuesEqual(prev[key], value)) return prev
        const next = { ...prev, [key]: value }
        writePrefsSnapshot(next, serverSnapshotRef)
        persistPatch({ [key]: value } as Partial<UserUiPreferences>)
        return next
      })
    },
    [persistPatch],
  )

  const setPreferenceDebounced = useCallback(
    <K extends keyof UserUiPreferences>(key: K, value: UserUiPreferences[K], delayMs = 400) => {
      setPrefs((prev) => {
        if (prefValuesEqual(prev[key], value)) return prev
        const next = { ...prev, [key]: value }
        writePrefsSnapshot(next, serverSnapshotRef)
        const existing = debounceRef.current[key]
        if (existing) clearTimeout(existing)
        debounceRef.current[key] = setTimeout(() => {
          debounceRef.current[key] = undefined
          persistPatch({ [key]: value } as Partial<UserUiPreferences>)
        }, delayMs)
        return next
      })
    },
    [persistPatch],
  )

  return { prefs, setPreference, setPreferenceDebounced }
}

export type { CalendarView, UserUiPreferences } from './userUiPreferences'
