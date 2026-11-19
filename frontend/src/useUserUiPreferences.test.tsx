import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { useUserUiPreferences } from './useUserUiPreferences'
import { DEFAULT_UI_PREFERENCES, writeCachedUiPreferences } from './userUiPreferences'
import type { UserPublic } from './types'

beforeEach(() => localStorage.clear())
afterEach(() => { cleanup(); vi.unstubAllGlobals() })
const saved = { ...DEFAULT_UI_PREFERENCES, main_menu_column_widths: [189, 350, 511, 269, 167], tasks_menu_column_widths: [100, 80, 100, 200, 300, 200, 100] }
const user = { id: 'signed-in-user', ui_preferences: saved } as UserPublic

it('uses server preferences on fresh sign-in without needing a reload or writing defaults', async () => {
  const fetch = vi.fn()
  vi.stubGlobal('fetch', fetch)
  const { result, rerender } = renderHook(({ me }: { me: UserPublic | null }) => useUserUiPreferences(me, me ? 'session' : null), { initialProps: { me: null as UserPublic | null } })
  await act(async () => { rerender({ me: user }) })
  expect(result.current.prefs.main_menu_column_widths).toEqual(saved.main_menu_column_widths)
  expect(result.current.prefs.tasks_menu_column_widths).toEqual(saved.tasks_menu_column_widths)
  expect(fetch).not.toHaveBeenCalled()
})

it('uses server preferences instead of a stale device cache when switching users', async () => {
  writeCachedUiPreferences(DEFAULT_UI_PREFERENCES, user.id)
  const { result, rerender } = renderHook(({ me }) => useUserUiPreferences(me, 'session'), { initialProps: { me: { id: 'previous-user', ui_preferences: DEFAULT_UI_PREFERENCES } as UserPublic } })
  await act(async () => { rerender({ me: user }) })
  expect(result.current.prefs.main_menu_column_widths).toEqual(saved.main_menu_column_widths)
})
