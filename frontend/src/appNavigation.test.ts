import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  buildAppNavigationUrl,
  parseAppNavigation,
  sanitizeAppNavigation,
  syncAppNavigationUrl,
  type AppNavState,
} from './appNavigation'

const base: AppNavState = {
  view: 'main-menu',
  caseId: null,
  quotesSubPanel: 'list',
  tasksCaseFilter: null,
}

const CASE_ID = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'

describe('parseAppNavigation / buildAppNavigationUrl', () => {
  it('round-trips static routes and quote subpanels', () => {
    expect(parseAppNavigation({ pathname: '/contacts', search: '' }).view).toBe('contacts')
    expect(buildAppNavigationUrl({ ...base, view: 'contacts' })).toBe('/contacts')
    expect(parseAppNavigation({ pathname: '/quotes/fee-scales', search: '' }).quotesSubPanel).toBe('fee-scales')
    expect(buildAppNavigationUrl({ ...base, view: 'quotes', quotesSubPanel: 'fee-scales' })).toBe(
      '/quotes/fee-scales',
    )
  })

  it('parses case URLs and tasks case filters', () => {
    expect(parseAppNavigation({ pathname: `/case/${CASE_ID}`, search: '' })).toEqual({
      view: 'case-menu',
      caseId: CASE_ID,
      quotesSubPanel: 'list',
      tasksCaseFilter: null,
    })
    expect(buildAppNavigationUrl({ ...base, view: 'case-menu', caseId: CASE_ID })).toBe(`/case/${CASE_ID}`)
    expect(parseAppNavigation({ pathname: '/tasks', search: `?case=${CASE_ID}` }).tasksCaseFilter).toBe(CASE_ID)
    expect(buildAppNavigationUrl({ ...base, view: 'tasks', tasksCaseFilter: CASE_ID })).toBe(
      `/tasks?case=${CASE_ID}`,
    )
  })

  it('supports legacy ?tasks= on the home path', () => {
    expect(parseAppNavigation({ pathname: '/', search: `?tasks=${CASE_ID}` }).view).toBe('tasks')
    expect(parseAppNavigation({ pathname: '/', search: '?tasks=not-a-uuid' }).tasksCaseFilter).toBeNull()
  })

  it('falls back to main menu for unknown paths', () => {
    expect(parseAppNavigation({ pathname: '/nope', search: '' })).toEqual(base)
  })
})

describe('sanitizeAppNavigation', () => {
  it('strips admin / accounts / docusign when unavailable', () => {
    expect(sanitizeAppNavigation({ ...base, view: 'admin-console' }, false).view).toBe('main-menu')
    expect(sanitizeAppNavigation({ ...base, view: 'accounts' }, true, false).view).toBe('main-menu')
    expect(sanitizeAppNavigation({ ...base, view: 'docusign' }, true, true, false).view).toBe('main-menu')
    expect(sanitizeAppNavigation({ ...base, view: 'admin-console' }, true).view).toBe('admin-console')
  })
})

describe('syncAppNavigationUrl', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    window.history.replaceState(null, '', '/')
  })

  it('uses pushState for user navigation by default when mode is push', () => {
    window.history.replaceState(null, '', '/')
    const push = vi.spyOn(window.history, 'pushState')
    const replace = vi.spyOn(window.history, 'replaceState')

    syncAppNavigationUrl({ ...base, view: 'contacts' }, 'push')

    expect(push).toHaveBeenCalled()
    expect(replace).not.toHaveBeenCalled()
    expect(String(push.mock.calls[0]?.[2])).toBe('/contacts')
  })

  it('uses replaceState for canonical or permission redirects', () => {
    const push = vi.spyOn(window.history, 'pushState')
    const replace = vi.spyOn(window.history, 'replaceState')
    window.history.replaceState(null, '', '/admin')

    syncAppNavigationUrl({ ...base, view: 'main-menu' }, 'replace')

    expect(replace).toHaveBeenCalled()
    // First call may be our setup; last call should be the sync
    const urls = replace.mock.calls.map((c) => String(c[2]))
    expect(urls.some((u) => u === '/' || u.endsWith('/'))).toBe(true)
    expect(push).not.toHaveBeenCalled()
  })

  it('is a no-op when the URL is already current', () => {
    window.history.replaceState(null, '', '/contacts')
    const push = vi.spyOn(window.history, 'pushState')
    const replace = vi.spyOn(window.history, 'replaceState')

    syncAppNavigationUrl({ ...base, view: 'contacts' }, 'push')

    expect(push).not.toHaveBeenCalled()
    expect(replace).not.toHaveBeenCalled()
  })
})
