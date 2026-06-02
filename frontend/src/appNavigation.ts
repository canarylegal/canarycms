export type AppView =
  | 'main-menu'
  | 'quotes'
  | 'tasks'
  | 'case-menu'
  | 'contacts'
  | 'calendar'
  | 'reports'
  | 'user-settings'
  | 'admin-console'

export type AppNavState = {
  view: AppView
  caseId: string | null
  quotesSubPanel: 'list' | 'fee-scales' | 'sources'
  tasksCaseFilter: string | null
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function isUuid(value: string | null | undefined): value is string {
  return Boolean(value && UUID_RE.test(value))
}

const STATIC_ROUTES: Record<string, AppView> = {
  '/calendar': 'calendar',
  '/tasks': 'tasks',
  '/contacts': 'contacts',
  '/reports': 'reports',
  '/settings': 'user-settings',
  '/admin': 'admin-console',
}

const DEFAULT_NAV: AppNavState = {
  view: 'main-menu',
  caseId: null,
  quotesSubPanel: 'list',
  tasksCaseFilter: null,
}

/** Parse the SPA URL into top-level navigation state (survives browser refresh). */
export function parseAppNavigation(loc: Pick<Location, 'pathname' | 'search'>): AppNavState {
  const searchParams = new URLSearchParams(loc.search)
  const legacyTasksCaseId = searchParams.get('tasks')
  const path = loc.pathname.replace(/\/+$/, '') || '/'

  if (legacyTasksCaseId && (path === '/' || path === '/main')) {
    return {
      view: 'tasks',
      caseId: null,
      quotesSubPanel: 'list',
      tasksCaseFilter: isUuid(legacyTasksCaseId) ? legacyTasksCaseId : null,
    }
  }

  if (path === '/' || path === '/main') {
    return DEFAULT_NAV
  }

  if (path === '/quotes' || path === '/quotes/fee-scales') {
    return {
      view: 'quotes',
      caseId: null,
      quotesSubPanel: path === '/quotes/fee-scales' ? 'fee-scales' : 'list',
      tasksCaseFilter: null,
    }
  }

  const caseMatch = /^\/case\/([^/]+)$/.exec(path)
  if (caseMatch && isUuid(caseMatch[1])) {
    return {
      view: 'case-menu',
      caseId: caseMatch[1],
      quotesSubPanel: 'list',
      tasksCaseFilter: null,
    }
  }

  const view = STATIC_ROUTES[path]
  if (view) {
    const tasksCaseFilter = view === 'tasks' ? searchParams.get('case') : null
    return {
      view,
      caseId: null,
      quotesSubPanel: 'list',
      tasksCaseFilter: isUuid(tasksCaseFilter) ? tasksCaseFilter : null,
    }
  }

  return DEFAULT_NAV
}

export function buildAppNavigationUrl(state: AppNavState): string {
  let pathname = '/'
  const searchParams = new URLSearchParams()

  switch (state.view) {
    case 'main-menu':
      pathname = '/'
      break
    case 'quotes':
      pathname = state.quotesSubPanel === 'fee-scales' ? '/quotes/fee-scales' : '/quotes'
      break
    case 'case-menu':
      pathname = state.caseId ? `/case/${state.caseId}` : '/'
      break
    case 'calendar':
      pathname = '/calendar'
      break
    case 'tasks':
      pathname = '/tasks'
      if (state.tasksCaseFilter) searchParams.set('case', state.tasksCaseFilter)
      break
    case 'contacts':
      pathname = '/contacts'
      break
    case 'reports':
      pathname = '/reports'
      break
    case 'user-settings':
      pathname = '/settings'
      break
    case 'admin-console':
      pathname = '/admin'
      break
  }

  const qs = searchParams.toString()
  return qs ? `${pathname}?${qs}` : pathname
}

export function syncAppNavigationUrl(state: AppNavState, mode: 'push' | 'replace' = 'replace'): void {
  const next = buildAppNavigationUrl(state)
  const current = `${window.location.pathname}${window.location.search}`
  if (next === current) return
  if (mode === 'push') {
    window.history.pushState(null, '', next)
  } else {
    window.history.replaceState(null, '', next)
  }
}

export function readBootNavigation(initialTasksCaseFilter?: string | null): AppNavState {
  const nav = parseAppNavigation(window.location)
  if (initialTasksCaseFilter && isUuid(initialTasksCaseFilter)) {
    return {
      view: 'tasks',
      caseId: null,
      quotesSubPanel: 'list',
      tasksCaseFilter: initialTasksCaseFilter,
    }
  }
  return nav
}

/** Strip admin navigation when the signed-in user lacks admin console access. */
export function sanitizeAppNavigation(nav: AppNavState, canAccessAdmin: boolean): AppNavState {
  if (canAccessAdmin || nav.view !== 'admin-console') return nav
  return { ...DEFAULT_NAV }
}
