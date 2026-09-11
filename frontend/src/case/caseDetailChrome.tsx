import type { ReactNode } from 'react'
import { NavIcon, type NavIconName } from '../NavIcon'

/** Matter sub-menu panel body: fit width, scroll vertically (no zoom shrinking). */
export function CaseDocPanelScroll({
  children,
  /** Stretch direct child to host height when content is short (e.g. embedded calendar). */
  fillHost = false,
}: {
  children: ReactNode
  fillHost?: boolean
}) {
  return (
    <div className={`caseDocPanelScrollHost${fillHost ? ' caseDocPanelScrollHost--fillHost' : ''}`}>{children}</div>
  )
}

/** Dark header chrome for case sub-menus — matches New matter modal paneHead. */
export function CaseDocPanelChrome({
  title,
  subtitle,
  onClose,
  closeLabel = 'Close',
  closeDisabled,
  actions,
}: {
  title: string
  subtitle?: string
  onClose: () => void
  closeLabel?: string
  closeDisabled?: boolean
  actions?: ReactNode
}) {
  return (
    <div className="caseDocPanelBar">
      <div className="caseDocPanelBarTitle">
        <h2>{title}</h2>
        {subtitle ? <div className="muted">{subtitle}</div> : null}
      </div>
      <div className="caseDocPanelBarActions">
        {actions}
        <button type="button" className="btn" onClick={onClose} disabled={closeDisabled}>
          {closeLabel}
        </button>
      </div>
    </div>
  )
}

export function CaseDocsToolbarBtnIcon({ d }: { d: string }) {
  return (
    <svg className="caseDocsToolbarBtnIcon" width={16} height={16} viewBox="0 0 24 24" aria-hidden>
      <path fill="currentColor" d={d} />
    </svg>
  )
}

export const CASE_DOCS_TOOLBAR_ICONS = {
  import: 'M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z',
  export: 'M9 16h6v-6h4l-7-7-7 7h4zm-4 2v2h14v-2H5z',
  portal:
    'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z',
  refresh:
    'M17.65 6.35A7.958 7.958 0 0 0 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0 1 12 18c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z',
} as const

export type CaseLeftMenuIconName =
  | 'overview'
  | 'contacts'
  | 'accounts'
  | 'tasks'
  | 'property'
  | 'events'
  | 'finance'

/** Case left sub-menu icons — reuse main-nav glyphs where the same section exists. */
export function CaseLeftMenuIcon({ name }: { name: CaseLeftMenuIconName }) {
  const navName: NavIconName | null =
    name === 'contacts'
      ? 'contacts'
      : name === 'accounts'
        ? 'accounts'
        : name === 'tasks'
          ? 'tasks'
          : name === 'events'
            ? 'calendar'
            : name === 'finance'
              ? 'reports'
              : null
  if (navName) {
    return <NavIcon name={navName} className="caseLeftNavIcon" />
  }

  const common = {
    className: 'caseLeftNavIcon',
    width: 16,
    height: 16,
    viewBox: '0 0 24 24',
    fill: 'none' as const,
    xmlns: 'http://www.w3.org/2000/svg',
    'aria-hidden': true as const,
  }
  if (name === 'overview') {
    return (
      <svg {...common}>
        <rect x="4" y="4" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="2" />
        <rect x="13" y="4" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="2" />
        <rect x="4" y="13" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="2" />
        <rect x="13" y="13" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="2" />
      </svg>
    )
  }
  // Property — no main-nav counterpart
  return (
    <svg {...common}>
      <path
        d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5.5v-6h-5v6H4a1 1 0 0 1-1-1v-9.5Z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
    </svg>
  )
}
