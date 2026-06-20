export type NavIconName =
  | 'main-menu'
  | 'quotes'
  | 'calendar'
  | 'tasks'
  | 'contacts'
  | 'docusign'
  | 'accounts'
  | 'reports'
  | 'user-settings'
  | 'admin-console'

type Props = {
  name: NavIconName
  className?: string
}

/** Small stroke icons for the primary app navigation (Tier 4 brand layer). */
export function NavIcon({ name, className }: Props) {
  const common = {
    className,
    width: 16,
    height: 16,
    viewBox: '0 0 24 24',
    fill: 'none',
    xmlns: 'http://www.w3.org/2000/svg',
    'aria-hidden': true as const,
  }

  switch (name) {
    case 'main-menu':
      return (
        <svg {...common}>
          <path
            d="M4 6h16M4 12h16M4 18h10"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
      )
    case 'quotes':
      return (
        <svg {...common}>
          <path
            d="M9 4h6a2 2 0 0 1 2 2v14l-3-2-3 2-3-2-3 2V6a2 2 0 0 1 2-2Z"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinejoin="round"
          />
          <path d="M9 8h6M9 12h4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      )
    case 'calendar':
      return (
        <svg {...common}>
          <rect x="4" y="5" width="16" height="15" rx="2" stroke="currentColor" strokeWidth="2" />
          <path d="M8 3v4M16 3v4M4 10h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      )
    case 'tasks':
      return (
        <svg {...common}>
          <path
            d="M9 11l2 2 5-5M7 4h10a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      )
    case 'contacts':
      return (
        <svg {...common}>
          <circle cx="9" cy="8" r="3" stroke="currentColor" strokeWidth="2" />
          <path
            d="M4 19c0-2.8 2.2-5 5-5s5 2.2 5 5"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
          <path
            d="M16 8.5a2.5 2.5 0 0 1 0 5M18 19c0-2-1.2-3.6-3-4.2"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
      )
    case 'docusign':
      return (
        <svg {...common}>
          <path
            d="M4 19.5 9 4l5 7 6-2.5"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path d="M14 3h6v6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )
    case 'accounts':
      return (
        <svg {...common}>
          <rect x="3" y="6" width="18" height="13" rx="2" stroke="currentColor" strokeWidth="2" />
          <path d="M3 10h18M7 14h2M11 14h2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      )
    case 'reports':
      return (
        <svg {...common}>
          <path d="M5 19V9M12 19V5M19 19v-7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      )
    case 'user-settings':
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2" />
          <path
            d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
      )
    case 'admin-console':
      return (
        <svg {...common}>
          <path
            d="M12 3 4 7v6c0 4.2 3.4 6.8 8 8 4.6-1.2 8-3.8 8-8V7l-8-4Z"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinejoin="round"
          />
          <path d="M9 12l2 2 4-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )
    default:
      return null
  }
}

export function PrimaryNavButton({
  name,
  label,
  active,
  onClick,
  className,
  layout = 'ribbon',
  collapsed = false,
}: {
  name: NavIconName
  label: string
  active: boolean
  onClick: () => void
  className?: string
  layout?: 'ribbon' | 'sidebar'
  /** Icon-only sidebar item (label in tooltip / aria-label). */
  collapsed?: boolean
}) {
  return (
    <button
      type="button"
      className={`navBtn${layout === 'sidebar' ? ' sidebarNavBtn' : ''}${active ? ' active' : ''}${className ? ` ${className}` : ''}`}
      onClick={onClick}
      aria-label={label}
      title={collapsed ? label : undefined}
    >
      <NavIcon name={name} className="navBtnIcon" />
      <span className="navBtnLabel">{label}</span>
    </button>
  )
}
