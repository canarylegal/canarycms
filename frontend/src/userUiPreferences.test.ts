import { beforeEach, describe, expect, it } from 'vitest'
import {
  DEFAULT_UI_PREFERENCES,
  readCachedUiPreferences,
  uiPreferencesCacheKey,
  writeCachedUiPreferences,
} from './userUiPreferences'

describe('ui preferences local cache', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('namespaces storage by user id', () => {
    writeCachedUiPreferences(
      { ...DEFAULT_UI_PREFERENCES, main_menu_sort_key: 'client', main_menu_search: 'Mrs Smith' },
      'user-a',
    )
    writeCachedUiPreferences(
      { ...DEFAULT_UI_PREFERENCES, main_menu_sort_key: 'matter' },
      'user-b',
    )

    expect(localStorage.getItem(uiPreferencesCacheKey('user-a'))).toBeTruthy()
    expect(localStorage.getItem(uiPreferencesCacheKey('user-b'))).toBeTruthy()
    expect(readCachedUiPreferences('user-a').main_menu_sort_key).toBe('client')
    expect(readCachedUiPreferences('user-b').main_menu_sort_key).toBe('matter')
  })

  it('does not persist free-text search strings in localStorage', () => {
    writeCachedUiPreferences(
      {
        ...DEFAULT_UI_PREFERENCES,
        main_menu_search: 'secret client',
        tasks_menu_search: 'secret task',
        contacts_search: 'secret contact',
        calendar_view: 'timeGridWeek',
      },
      'user-a',
    )
    const raw = JSON.parse(localStorage.getItem(uiPreferencesCacheKey('user-a')) || '{}') as Record<
      string,
      unknown
    >
    expect(raw.main_menu_search).toBe('')
    expect(raw.tasks_menu_search).toBe('')
    expect(raw.contacts_search).toBe('')
    expect(raw.calendar_view).toBe('timeGridWeek')
  })

  it('returns defaults when no user id is present', () => {
    writeCachedUiPreferences({ ...DEFAULT_UI_PREFERENCES, main_menu_sort_key: 'status' }, 'user-a')
    expect(readCachedUiPreferences(null)).toEqual(DEFAULT_UI_PREFERENCES)
  })

  it('migrates the legacy global cache key into the first user bucket', () => {
    localStorage.setItem(
      'canary.uiPreferences.v2',
      JSON.stringify({ ...DEFAULT_UI_PREFERENCES, main_menu_sort_key: 'feeEarner' }),
    )
    const prefs = readCachedUiPreferences('user-new')
    expect(prefs.main_menu_sort_key).toBe('feeEarner')
    expect(localStorage.getItem('canary.uiPreferences.v2')).toBeNull()
    expect(localStorage.getItem(uiPreferencesCacheKey('user-new'))).toBeTruthy()
  })
})
