import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

export type AppNotification = {
  id: string
  message: string
  createdAt: string
  read: boolean
}

type NotificationsContextValue = {
  notifications: AppNotification[]
  unreadCount: number
  push: (message: string) => void
  markAllRead: () => void
  markRead: (id: string) => void
  clearAll: () => void
}

type NotificationsScopeValue = {
  setUserId: (userId: string | null) => void
}

const LEGACY_STORAGE_KEY = 'canary-app-notifications'
const MAX_ITEMS = 50

const NotificationsContext = createContext<NotificationsContextValue | null>(null)
const NotificationsScopeContext = createContext<NotificationsScopeValue | null>(null)

function notificationsStorageKey(userId: string | null | undefined): string | null {
  if (!userId) return null
  return `canary-app-notifications.${userId}.v1`
}

function loadStored(userId: string | null | undefined): AppNotification[] {
  const key = notificationsStorageKey(userId)
  if (!key) return []
  try {
    let raw = localStorage.getItem(key)
    if (!raw) {
      const legacy = localStorage.getItem(LEGACY_STORAGE_KEY)
      if (legacy) {
        raw = legacy
        localStorage.setItem(key, legacy)
        localStorage.removeItem(LEGACY_STORAGE_KEY)
      }
    }
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter(
        (n): n is AppNotification =>
          !!n &&
          typeof n === 'object' &&
          typeof (n as AppNotification).id === 'string' &&
          typeof (n as AppNotification).message === 'string' &&
          typeof (n as AppNotification).createdAt === 'string',
      )
      .map((n) => ({ ...n, read: Boolean(n.read) }))
      .slice(0, MAX_ITEMS)
  } catch {
    return []
  }
}

function demoNotifications(): AppNotification[] {
  const now = Date.now()
  const mk = (minsAgo: number, message: string, read = false): AppNotification => ({
    id: `demo-${minsAgo}-${now}`,
    message,
    createdAt: new Date(now - minsAgo * 60_000).toISOString(),
    read,
  })
  return [
    mk(2, 'Canary Sign request voided.'),
    mk(18, 'Signing reminders sent.'),
    mk(45, 'Quote converted to Active.'),
    mk(120, 'Portal contact notified by e-mail.'),
    mk(400, 'Outlook draft created with 1 file attached. Review and send from the draft window.', true),
  ]
}

function shouldSeedDemoNotifications(): boolean {
  try {
    const params = new URLSearchParams(window.location.search)
    return params.get('demoNotifications') === '1'
  } catch {
    return false
  }
}

function persist(userId: string | null | undefined, items: AppNotification[]) {
  const key = notificationsStorageKey(userId)
  if (!key) return
  try {
    localStorage.setItem(key, JSON.stringify(items.slice(0, MAX_ITEMS)))
  } catch {
    // ignore quota / private mode
  }
}

function newId() {
  try {
    return crypto.randomUUID()
  } catch {
    return `n-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
  }
}

export function useNotifications(): NotificationsContextValue {
  const v = useContext(NotificationsContext)
  if (!v) {
    throw new Error('useNotifications must be used within NotificationsProvider')
  }
  return v
}

/** Optional: no-op push when provider missing (e.g. standalone pages). */
export function useNotificationsOptional(): NotificationsContextValue | null {
  return useContext(NotificationsContext)
}

/** Bind notifications localStorage to the signed-in user (call from App on me.id change). */
export function useNotificationsUserScope(): NotificationsScopeValue {
  const v = useContext(NotificationsScopeContext)
  if (!v) {
    throw new Error('useNotificationsUserScope must be used within NotificationsProvider')
  }
  return v
}

export function NotificationsProvider({ children }: { children: ReactNode }) {
  const [userId, setUserId] = useState<string | null>(null)
  const userIdRef = useRef(userId)
  const [notifications, setNotifications] = useState<AppNotification[]>(() => {
    if (typeof window !== 'undefined' && shouldSeedDemoNotifications()) {
      return demoNotifications()
    }
    return []
  })

  useEffect(() => {
    if (userIdRef.current === userId) return
    userIdRef.current = userId
    if (typeof window !== 'undefined' && shouldSeedDemoNotifications()) {
      const demo = demoNotifications()
      persist(userId, demo)
      setNotifications(demo)
      return
    }
    setNotifications(loadStored(userId))
  }, [userId])

  useEffect(() => {
    if (!shouldSeedDemoNotifications()) return
    try {
      const url = new URL(window.location.href)
      if (url.searchParams.has('demoNotifications')) {
        url.searchParams.delete('demoNotifications')
        window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`)
      }
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => {
    persist(userId, notifications)
  }, [userId, notifications])

  const push = useCallback((message: string) => {
    const text = String(message || '').trim()
    if (!text) return
    setNotifications((prev) => {
      const next: AppNotification = {
        id: newId(),
        message: text,
        createdAt: new Date().toISOString(),
        read: false,
      }
      return [next, ...prev].slice(0, MAX_ITEMS)
    })
  }, [])

  const markAllRead = useCallback(() => {
    setNotifications((prev) => {
      if (!prev.some((n) => !n.read)) return prev
      return prev.map((n) => (n.read ? n : { ...n, read: true }))
    })
  }, [])

  const markRead = useCallback((id: string) => {
    setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)))
  }, [])

  const clearAll = useCallback(() => {
    setNotifications([])
  }, [])

  const unreadCount = useMemo(() => notifications.reduce((n, item) => n + (item.read ? 0 : 1), 0), [notifications])

  const value = useMemo(
    () => ({ notifications, unreadCount, push, markAllRead, markRead, clearAll }),
    [notifications, unreadCount, push, markAllRead, markRead, clearAll],
  )

  const scope = useMemo(() => ({ setUserId }), [])

  return (
    <NotificationsScopeContext.Provider value={scope}>
      <NotificationsContext.Provider value={value}>{children}</NotificationsContext.Provider>
    </NotificationsScopeContext.Provider>
  )
}
