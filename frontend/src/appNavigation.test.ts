import { afterEach, describe, expect, it, vi } from 'vitest'
import { syncAppNavigationUrl, type AppNavState } from './appNavigation'

const base: AppNavState = {
  view: 'main-menu',
  caseId: null,
  quotesSubPanel: 'list',
  tasksCaseFilter: null,
}

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
