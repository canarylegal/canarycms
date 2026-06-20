import { useEffect } from 'react'
import type { AppSidebarView } from './AppSidebar'
import { isCaseContextMenuOpen, isEditableKeyboardTarget, isModalBlockingKeyboard } from './keyboardUtils'

export type PrimaryNavId = Exclude<AppSidebarView, 'case-menu'>

function buildPrimaryNavItems(canAccessAccounts: boolean, canAdminConsole: boolean, docusignEnabled: boolean): PrimaryNavId[] {
  const items: PrimaryNavId[] = ['main-menu', 'quotes', 'calendar', 'tasks', 'contacts']
  if (docusignEnabled) items.push('docusign')
  if (canAccessAccounts) items.push('accounts')
  items.push('reports', 'user-settings')
  if (canAdminConsole) items.push('admin-console')
  return items
}

function resolvePrimaryNavView(view: AppSidebarView): PrimaryNavId {
  return view === 'case-menu' ? 'main-menu' : view
}

type NavigateHandlers = Record<PrimaryNavId, () => void>

export function usePrimaryNavKeyboard({
  enabled,
  view,
  canAccessAccounts,
  canAdminConsole,
  docusignEnabled,
  onNavigate,
}: {
  enabled: boolean
  view: AppSidebarView
  canAccessAccounts: boolean
  canAdminConsole: boolean
  docusignEnabled: boolean
  onNavigate: NavigateHandlers
}) {
  useEffect(() => {
    if (!enabled) return

    function onKeyDown(e: KeyboardEvent) {
      if (!e.shiftKey || (e.key !== 'ArrowDown' && e.key !== 'ArrowUp')) return
      if (e.altKey || e.ctrlKey || e.metaKey) return
      if (isEditableKeyboardTarget(e.target) || isModalBlockingKeyboard() || isCaseContextMenuOpen()) return

      const items = buildPrimaryNavItems(canAccessAccounts, canAdminConsole, docusignEnabled)
      if (items.length === 0) return

      const current = resolvePrimaryNavView(view)
      let index = items.indexOf(current)
      if (index < 0) index = 0

      const delta = e.key === 'ArrowDown' ? 1 : -1
      const next = items[(index + delta + items.length) % items.length]
      e.preventDefault()
      onNavigate[next]()
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [enabled, view, canAccessAccounts, canAdminConsole, docusignEnabled, onNavigate])
}
