import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { apiFetch } from './api'
import { CanaryMark } from './AppBrand'
import { PrimaryNavButton } from './NavIcon'
import { useNotifications } from './NotificationsProvider'
import { SupportTicketModal, type SupportTicketKind } from './SupportTicketModal'
import { useDialogs } from './DialogProvider'

export type FirmPackageStatus = {
  attached: boolean
  compatible: boolean
  fault: boolean
  package_id?: string | null
  package_version?: string | null
  label?: string | null
  requires_canary?: string | null
  canary_version: string
  message?: string | null
  detail?: string | null
}

const SIDEBAR_EXPANDED_KEY = 'canary-sidebar-expanded'

function readSidebarExpanded(): boolean {
  try {
    const raw = localStorage.getItem(SIDEBAR_EXPANDED_KEY)
    // Explicit preference only — default collapsed until the user expands once.
    if (raw === '1') return true
    if (raw === '0') return false
    return false
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

function formatNotifyTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  try {
    return d.toLocaleString(undefined, {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return d.toISOString()
  }
}

export type AppSidebarView =
  | 'main-menu'
  | 'quotes'
  | 'tasks'
  | 'case-menu'
  | 'contacts'
  | 'calendar'
  | 'docusign'
  | 'accounts'
  | 'reports'
  | 'user-settings'
  | 'admin-console'

type Props = {
  view: AppSidebarView
  /** Open matter is a quote — keep Quotes highlighted instead of Cases. */
  caseMenuQuoteContext?: boolean
  goMainMenu: () => void
  onQuotes: () => void
  onCalendar: () => void
  onTasks: () => void
  onContacts: () => void
  onDocusign?: () => void
  onAccounts: () => void
  onReports: () => void
  onUserSettings: () => void
  onAdminConsole: () => void
  canAccessAccounts: boolean
  canAdminConsole: boolean
  docusignEnabled?: boolean
  onLogout: () => void
  /** Auth token for firm-package status (Phase 6 fault marker). */
  token?: string | null
}

/** Primary app navigation — vertical sidebar (Option 4). */
export function AppSidebar({
  view,
  caseMenuQuoteContext = false,
  goMainMenu,
  onQuotes,
  onCalendar,
  onTasks,
  onContacts,
  onDocusign,
  onAccounts,
  onReports,
  onUserSettings,
  onAdminConsole,
  canAccessAccounts,
  canAdminConsole,
  docusignEnabled = false,
  onLogout,
  token = null,
}: Props) {
  const [expanded, setExpanded] = useState(readSidebarExpanded)
  const [notifyOpen, setNotifyOpen] = useState(false)
  const [panelPos, setPanelPos] = useState<{ top: number; left: number } | null>(null)
  const notifyWrapRef = useRef<HTMLDivElement>(null)
  const brandBtnRef = useRef<HTMLButtonElement>(null)
  const supportWrapRef = useRef<HTMLDivElement>(null)
  const supportBtnRef = useRef<HTMLButtonElement>(null)
  const [supportMenuOpen, setSupportMenuOpen] = useState(false)
  const [supportMenuPos, setSupportMenuPos] = useState<{ top: number; left: number } | null>(null)
  const [ticketKind, setTicketKind] = useState<SupportTicketKind | null>(null)
  const [firmPackage, setFirmPackage] = useState<FirmPackageStatus | null>(null)
  const { notifications, unreadCount, markAllRead, clearAll } = useNotifications()
  const { alert } = useDialogs()
  const firmFault = Boolean(firmPackage?.fault)

  useEffect(() => {
    if (!token) {
      setFirmPackage(null)
      return
    }
    let cancelled = false
    void apiFetch<FirmPackageStatus>('/firm-package/status', { token })
      .then((s) => {
        if (!cancelled) setFirmPackage(s)
      })
      .catch(() => {
        if (!cancelled) setFirmPackage(null)
      })
    return () => {
      cancelled = true
    }
  }, [token])

  // Keep preference in sync across remounts / other tabs.
  useEffect(() => {
    function syncFromStorage() {
      setExpanded(readSidebarExpanded())
    }
    window.addEventListener('storage', syncFromStorage)
    window.addEventListener('focus', syncFromStorage)
    return () => {
      window.removeEventListener('storage', syncFromStorage)
      window.removeEventListener('focus', syncFromStorage)
    }
  }, [])

  useLayoutEffect(() => {
    if (!notifyOpen) {
      setPanelPos(null)
      return
    }
    function place() {
      const btn = brandBtnRef.current
      if (!btn) return
      const r = btn.getBoundingClientRect()
      const width = Math.min(320, window.innerWidth - 24)
      let left = r.right + 8
      if (left + width > window.innerWidth - 8) {
        left = Math.max(8, r.left)
      }
      let top = r.top
      const maxH = Math.min(420, window.innerHeight - 16)
      if (top + maxH > window.innerHeight - 8) {
        top = Math.max(8, window.innerHeight - maxH - 8)
      }
      setPanelPos({ top, left })
    }
    place()
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    return () => {
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place, true)
    }
  }, [notifyOpen, expanded])

  useEffect(() => {
    if (!notifyOpen) return
    markAllRead()
    function onDocMouseDown(e: MouseEvent) {
      const wrap = notifyWrapRef.current
      const panel = document.getElementById('app-sidebar-notify-panel')
      const t = e.target
      if (!(t instanceof Node)) return
      if (wrap?.contains(t) || panel?.contains(t)) return
      setNotifyOpen(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setNotifyOpen(false)
    }
    document.addEventListener('mousedown', onDocMouseDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDocMouseDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [notifyOpen, markAllRead])

  const toggleExpanded = useCallback(() => {
    setExpanded((prev) => {
      const next = !prev
      persistSidebarExpanded(next)
      return next
    })
  }, [])

  useLayoutEffect(() => {
    if (!supportMenuOpen) {
      setSupportMenuPos(null)
      return
    }
    function place() {
      const btn = supportBtnRef.current
      if (!btn) return
      const r = btn.getBoundingClientRect()
      const width = 220
      let left = r.right + 8
      if (left + width > window.innerWidth - 8) {
        left = Math.max(8, r.left)
      }
      const menuH = 96
      let top = r.bottom - menuH
      if (top < 8) top = 8
      setSupportMenuPos({ top, left })
    }
    place()
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    return () => {
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place, true)
    }
  }, [supportMenuOpen, expanded])

  useEffect(() => {
    if (!supportMenuOpen) return
    function onDocMouseDown(e: MouseEvent) {
      const wrap = supportWrapRef.current
      const panel = document.getElementById('app-sidebar-support-menu')
      const t = e.target
      if (!(t instanceof Node)) return
      if (wrap?.contains(t) || panel?.contains(t)) return
      setSupportMenuOpen(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setSupportMenuOpen(false)
    }
    document.addEventListener('mousedown', onDocMouseDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDocMouseDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [supportMenuOpen])

  const badgeLabel = unreadCount > 9 ? '9+' : String(unreadCount)

  function openTicket(kind: SupportTicketKind) {
    setSupportMenuOpen(false)
    setTicketKind(kind)
  }

  return (
    <aside
      className={`appSidebar${expanded ? ' appSidebar--expanded' : ' appSidebar--collapsed'}`}
      aria-expanded={expanded}
    >
      <div className="appSidebarBrandWrap" ref={notifyWrapRef}>
        <button
          type="button"
          ref={brandBtnRef}
          className={`appSidebarBrand appSidebarBrand--button${firmFault ? ' appSidebarBrand--fault' : ''}`}
          aria-label={
            firmFault
              ? `${firmPackage?.message || 'Firm package incompatible'}. ${firmPackage?.detail || ''}`.trim()
              : unreadCount
                ? `Notifications, ${unreadCount} unread`
                : 'Notifications'
          }
          aria-haspopup="dialog"
          aria-expanded={notifyOpen}
          aria-invalid={firmFault || undefined}
          title={
            firmFault
              ? [firmPackage?.message, firmPackage?.detail].filter(Boolean).join(' — ')
              : 'Notifications'
          }
          onClick={() => setNotifyOpen((o) => !o)}
        >
          <span className="appSidebarNotifyMark">
            {firmFault ? (
              <span className="appSidebarFirmFaultMark" aria-hidden>
                !
              </span>
            ) : (
              <CanaryMark className="appBrandMark" size="sidebar" />
            )}
            {unreadCount > 0 ? (
              <span className="appSidebarNotifyBadge" aria-hidden>
                {badgeLabel}
              </span>
            ) : null}
          </span>
          <span className="appSidebarBrandName" aria-hidden={!expanded}>
            {firmFault ? 'Fault' : 'Canary'}
          </span>
        </button>
        {notifyOpen && panelPos
          ? createPortal(
              <div
                id="app-sidebar-notify-panel"
                className="appSidebarNotifyPanel"
                role="dialog"
                aria-label={firmFault ? 'Firm package fault and notifications' : 'Notifications'}
                style={{ top: panelPos.top, left: panelPos.left }}
              >
                {firmFault ? (
                  <div className="appSidebarFirmFaultBanner" role="alert">
                    <strong>{firmPackage?.message || 'Firm package incompatible'}</strong>
                    {firmPackage?.detail ? (
                      <p className="appSidebarFirmFaultDetail">{firmPackage.detail}</p>
                    ) : null}
                    <p className="muted" style={{ margin: '8px 0 0', fontSize: 12, lineHeight: 1.45 }}>
                      Canary core is running. Firm features are disabled until the package and Canary
                      versions match. Admins: see Admin → Deploy.
                    </p>
                  </div>
                ) : null}
                <div className="appSidebarNotifyPanelHead">
                  <strong>Notifications</strong>
                  {notifications.length ? (
                    <button
                      type="button"
                      className="btnLink appSidebarNotifyClear"
                      onClick={() => {
                        clearAll()
                        setNotifyOpen(false)
                      }}
                    >
                      Clear all
                    </button>
                  ) : null}
                </div>
                {notifications.length === 0 ? (
                  <div className="appSidebarNotifyEmpty muted">No notifications yet.</div>
                ) : (
                  <ul className="appSidebarNotifyList">
                    {notifications.map((n) => (
                      <li
                        key={n.id}
                        className={`appSidebarNotifyItem${n.read ? '' : ' appSidebarNotifyItem--unread'}`}
                      >
                        <div className="appSidebarNotifyMessage">{n.message}</div>
                        <div className="appSidebarNotifyTime muted">{formatNotifyTime(n.createdAt)}</div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>,
              document.body,
            )
          : null}
      </div>
      <nav className="appSidebarNav" aria-label="Primary">
        <PrimaryNavButton
          layout="sidebar"
          collapsed={!expanded}
          name="main-menu"
          label="Cases"
          active={view === 'main-menu' || (view === 'case-menu' && !caseMenuQuoteContext)}
          onClick={goMainMenu}
        />
        <PrimaryNavButton
          layout="sidebar"
          collapsed={!expanded}
          name="quotes"
          label="Quotes"
          active={view === 'quotes' || (view === 'case-menu' && caseMenuQuoteContext)}
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
        {docusignEnabled && onDocusign ? (
          <PrimaryNavButton
            layout="sidebar"
            collapsed={!expanded}
            name="docusign"
            label="DocuSign"
            active={view === 'docusign'}
            onClick={onDocusign}
          />
        ) : null}
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
        <div className="appSidebarNavDivider" role="separator" aria-hidden />
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
        <div className="appSidebarSupportWrap" ref={supportWrapRef}>
          <button
            type="button"
            ref={supportBtnRef}
            className="appSidebarSignOut appSidebarSupport"
            onClick={() => setSupportMenuOpen((o) => !o)}
            aria-label="Support"
            aria-haspopup="menu"
            aria-expanded={supportMenuOpen}
            title={expanded ? undefined : 'Support'}
          >
            <svg className="appSidebarSignOutIcon" width={16} height={16} viewBox="0 0 24 24" fill="none" aria-hidden>
              <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
              <path
                d="M9.5 9.5a2.5 2.5 0 114 2c-.7.5-1.5 1-1.5 2v.5"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <circle cx="12" cy="17" r="1" fill="currentColor" />
            </svg>
            <span className="appSidebarSignOutLabel">Support</span>
          </button>
          {supportMenuOpen && supportMenuPos
            ? createPortal(
                <div
                  id="app-sidebar-support-menu"
                  className="appSidebarSupportMenu"
                  role="menu"
                  aria-label="Support options"
                  style={{ top: supportMenuPos.top, left: supportMenuPos.left }}
                >
                  <button type="button" role="menuitem" className="appSidebarSupportMenuItem" onClick={() => openTicket('support')}>
                    Submit support ticket
                  </button>
                  <button type="button" role="menuitem" className="appSidebarSupportMenuItem" onClick={() => openTicket('bug')}>
                    Report bug
                  </button>
                </div>,
                document.body,
              )
            : null}
        </div>
        <button
          type="button"
          className="appSidebarSignOut"
          onClick={onLogout}
          aria-label="Sign out"
          title={expanded ? undefined : 'Sign out'}
        >
          <svg className="appSidebarSignOutIcon" width={16} height={16} viewBox="0 0 24 24" fill="none" aria-hidden>
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
          <svg className="appSidebarToggleIcon" width={16} height={16} viewBox="0 0 24 24" fill="none" aria-hidden>
            {expanded ? (
              <path d="M15 6l-6 6 6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            ) : (
              <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            )}
          </svg>
          <span className="appSidebarToggleLabel">{expanded ? 'Collapse' : 'Expand'}</span>
        </button>
      </div>
      <SupportTicketModal
        open={ticketKind != null}
        kind={ticketKind ?? 'support'}
        onClose={() => setTicketKind(null)}
        onSubmitted={() => {
          void alert('Thanks — your message has been sent to Canary support.', 'Sent')
        }}
      />
    </aside>
  )
}
