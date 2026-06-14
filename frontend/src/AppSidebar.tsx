import { useCallback, useState } from 'react'
import { CanaryMark } from './AppBrand'
import { PrimaryNavButton } from './NavIcon'

const SIDEBAR_EXPANDED_KEY = 'canary-sidebar-expanded'

function readSidebarExpanded(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_EXPANDED_KEY) === '1'
  } catch {
    return false
  }
}

function persistSidebarExpanded(expanded: boolean) {
  try {
    localStorage.setItem(SIDEBAR_EXPANDED_KEY, expanded ? '1' : '0')
  } catch {
    // ignore
  }
}

export type AppSidebarView =
  | 'main-menu'
  | 'quotes'
  | 'tasks'
  | 'case-menu'
  | 'contacts'
  | 'calendar'
  | 'accounts'
  | 'reports'
  | 'user-settings'
  | 'admin-console'

type Props = {
  view: AppSidebarView
  goMainMenu: () => void
  onQuotes: () => void
  onCalendar: () => void
  onTasks: () => void
  onContacts: () => void
  onAccounts: () => void
  onReports: () => void
  onUserSettings: () => void
  onAdminConsole: () => void
  canAccessAccounts: boolean
  canAdminConsole: boolean
  onLogout: () => void
}

/** Primary app navigation — vertical sidebar (Option 4). */
export function AppSidebar({
  view,
  goMainMenu,
  onQuotes,
  onCalendar,
  onTasks,
  onContacts,
  onAccounts,
  onReports,
  onUserSettings,
  onAdminConsole,
  canAccessAccounts,
  canAdminConsole,
  onLogout,
}: Props) {
  const [expanded, setExpanded] = useState(readSidebarExpanded)

  const toggleExpanded = useCallback(() => {
    setExpanded((prev) => {
      const next = !prev
      persistSidebarExpanded(next)
      return next
    })
  }, [])

  return (
    <aside
      className={`appSidebar${expanded ? ' appSidebar--expanded' : ' appSidebar--collapsed'}`}
      aria-expanded={expanded}
    >
      <div className="appSidebarBrand" aria-label="Canary">
        <CanaryMark className="appBrandMark" size="sidebar" />
        <span className="appSidebarBrandName" aria-hidden={!expanded}>
          Canary
        </span>
      </div>
      <nav className="appSidebarNav" aria-label="Primary">
        <PrimaryNavButton
          layout="sidebar"
          collapsed={!expanded}
          name="main-menu"
          label="Cases"
          active={view === 'main-menu' || view === 'case-menu'}
          onClick={goMainMenu}
        />
        <PrimaryNavButton
          layout="sidebar"
          collapsed={!expanded}
          name="quotes"
          label="Quotes"
          active={view === 'quotes'}
          onClick={onQuotes}
        />
        <PrimaryNavButton
          layout="sidebar"
          collapsed={!expanded}
          name="calendar"
          label="Calendar"
          active={view === 'calendar'}
          onClick={onCalendar}
        />
        <PrimaryNavButton
          layout="sidebar"
          collapsed={!expanded}
          name="tasks"
          label="Tasks"
          active={view === 'tasks'}
          onClick={onTasks}
        />
        <PrimaryNavButton
          layout="sidebar"
          collapsed={!expanded}
          name="contacts"
          label="Contacts"
          active={view === 'contacts'}
          onClick={onContacts}
        />
        {canAccessAccounts ? (
          <PrimaryNavButton
            layout="sidebar"
            collapsed={!expanded}
            name="accounts"
            label="Accounts"
            active={view === 'accounts'}
            onClick={onAccounts}
          />
        ) : null}
        <PrimaryNavButton
          layout="sidebar"
          collapsed={!expanded}
          name="reports"
          label="Reports"
          active={view === 'reports'}
          onClick={onReports}
        />
        <PrimaryNavButton
          layout="sidebar"
          collapsed={!expanded}
          name="user-settings"
          label="User Settings"
          active={view === 'user-settings'}
          onClick={onUserSettings}
        />
        {canAdminConsole ? (
          <PrimaryNavButton
            layout="sidebar"
            collapsed={!expanded}
            name="admin-console"
            label="Admin Settings"
            active={view === 'admin-console'}
            onClick={onAdminConsole}
          />
        ) : null}
      </nav>
      <div className="appSidebarFooter">
        <button
          type="button"
          className="appSidebarSignOut"
          onClick={onLogout}
          aria-label="Sign out"
          title={expanded ? undefined : 'Sign out'}
        >
          <svg className="appSidebarSignOutIcon" width={24} height={24} viewBox="0 0 24 24" fill="none" aria-hidden>
            <path
              d="M10 17l5-5-5-5M15 12H4M20 4v16"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span className="appSidebarSignOutLabel">Sign out</span>
        </button>
        <button
          type="button"
          className="appSidebarToggle"
          aria-expanded={expanded}
          aria-label={expanded ? 'Collapse sidebar' : 'Expand sidebar'}
          title={expanded ? 'Collapse sidebar' : 'Expand sidebar'}
          onClick={toggleExpanded}
        >
          <svg className="appSidebarToggleIcon" width={24} height={24} viewBox="0 0 24 24" fill="none" aria-hidden>
              {expanded ? (
                <path d="M15 6l-6 6 6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              ) : (
                <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            )}
          </svg>
          <span className="appSidebarToggleLabel">{expanded ? 'Collapse' : 'Expand'}</span>
        </button>
      </div>
    </aside>
  )
}
