import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { useCalendarGrid } from './useCalendarGrid'
import { useAuth } from '../auth/useAuth'
import { rememberSessionUser, signalSessionExpired } from '../auth/sessionRecovery'
import { apiFetch } from '../api'
import { invalidateCalendarEventCache } from '../calendarEventCache'
import type { UserPublic } from '../types'
vi.mock('../api', () => ({ apiFetch: vi.fn(), COOKIE_SESSION_TOKEN: 'cookie' }))
vi.mock('../useUserUiPreferences', () => ({ useUserUiPreferences: () => ({ prefs: { calendar_selected_calendar_ids: [], calendar_view: 'dayGridMonth' }, setPreference: vi.fn() }) }))
const oldKey = 'canary-calendar-events:v1:2026-11-01|2026-12-01|shared-calendar'
const event = { id: 'private-event', title: 'Private title', description: 'Private details', start: '2026-11-22', end: '2026-11-23', all_day: true, case_id: 'private-matter' }
const me = (id: string) => ({ id, email: id + '@example.test' }) as UserPublic
const range = { startStr: '2026-11-01', endStr: '2026-12-01' }
beforeEach(() => {
  sessionStorage.clear()
  vi.mocked(apiFetch).mockImplementation(async path => path === '/auth/me' ? me('alice') as never : [] as never)
})
afterEach(() => { cleanup(); vi.resetAllMocks() })
it('clears old storage on logout while leaving unrelated data alone', async () => {
  const { result } = renderHook(() => useAuth())
  await waitFor(() => expect(result.current.me?.id).toBe('alice'))
  sessionStorage.setItem(oldKey, JSON.stringify([event])); sessionStorage.setItem('unrelated', 'keep')
  act(() => result.current.logout())
  expect(sessionStorage.getItem(oldKey)).toBeNull()
  expect(sessionStorage.getItem('unrelated')).toBe('keep')
})
it.each(['expiry', 'switch'])('clears storage and visible calendar on %s', async kind => {
  const { result } = renderHook(() => useCalendarGrid({ token: 'cookie', me: me('alice') }))
  await waitFor(() => expect(result.current.calendarsLoaded).toBe(true))
  const removeAllEvents = vi.fn()
  result.current.calRef.current = { getApi: () => ({ removeAllEvents }) } as never
  rememberSessionUser('alice')
  sessionStorage.setItem(oldKey, JSON.stringify([event]))
  act(() => kind === 'expiry' ? signalSessionExpired() : rememberSessionUser('bob'))
  expect(sessionStorage.getItem(oldKey)).toBeNull()
  expect(removeAllEvents).toHaveBeenCalled()
})
it('does not read or write stored events, and keeps fresh matter-only first paint', async () => {
  sessionStorage.setItem(oldKey, JSON.stringify([event]))
  const { result } = renderHook(() => useCalendarGrid({ token: 'cookie', me: me('bob') }))
  await waitFor(() => expect(result.current.calendarsLoaded).toBe(true))
  vi.mocked(apiFetch).mockImplementation(async path => path.includes('include_caldav=false') ? [] as never : [event] as never)
  const success = vi.fn()
  await act(async () => result.current.fetchEvents(range, success, vi.fn()))
  expect(success).toHaveBeenCalledTimes(1)
  expect(Object.keys(sessionStorage)).toEqual([oldKey])
  // No replacement or additional event payload was persisted.
  expect(sessionStorage.getItem(oldKey)).toBe(JSON.stringify([event]))
})
it.each(['logout', 'switch', 'unmount'])('discards an in-flight event response after %s', async kind => {
  const { result, rerender, unmount } = renderHook(({ id }) => useCalendarGrid({ token: 'cookie', me: me(id) }), { initialProps: { id: 'alice' } })
  await waitFor(() => expect(result.current.calendarsLoaded).toBe(true))
  let resolve!: (value: never) => void
  vi.mocked(apiFetch).mockImplementation(async path => (!path.includes('/calendar/events?') || path.includes('include_caldav=false')) ? [] as never : new Promise(r => { resolve = r }))
  const success = vi.fn(); let pending!: Promise<void>
  act(() => { pending = result.current.fetchEvents(range, success, vi.fn()) })
  await waitFor(() => expect(resolve).toBeTypeOf('function'))
  act(() => { if (kind === 'unmount') unmount(); else if (kind === 'switch') rerender({ id: 'bob' }); else invalidateCalendarEventCache() })
  await act(async () => { resolve([event] as never); await pending })
  expect(success).not.toHaveBeenCalled()
  expect(sessionStorage.length).toBe(0)
})
