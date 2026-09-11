import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  lazy,
  Suspense,
} from 'react'
import { AdminLoginUpdatePrompt } from './AdminLoginUpdatePrompt'
import { parseAppNavigation, readBootNavigation, sanitizeAppNavigation, syncAppNavigationUrl, type AppNavState } from './appNavigation'
import { CaseViewRoute } from './CaseViewRoute'
import { FeeScalesPanel } from './FeeScalesPanel'
import { QuoteSourcesPanel } from './QuoteSourcesPanel'
import { QuoteConvertModal } from './QuoteConvertModal'
import { QuoteWizard } from './QuoteWizard'
import { QuoteSendPrompt } from './QuoteSendPrompt'
import { useQuoteAwaitingSave, type QuoteAwaitingSaveContext } from './quoteAwaitingSave'
import { QUOTE_EMAIL_PRECEDENT_REFERENCE, type PendingCaseCompose } from './quoteEmailPrecedent'
import { TaskCreateModal } from './TaskCreateModal'
import { TasksTable } from './TasksTable'
import { closeMatterBlockMessage } from './case/closeMatterCheck'
import { releaseAllBodyCursorLocks } from './bodyCursorLock'
import { apiFetch } from './api'
import { useServerAppearance } from './useServerAppearance'
import { useUserUiPreferences } from './useUserUiPreferences'
import {
  MAIN_MENU_COLUMN_COUNT,
  MAIN_MENU_COLUMN_WIDTHS_DEFAULT,
  TASKS_MENU_COLUMN_COUNT,
  TASKS_MENU_COLUMN_WIDTHS_DEFAULT,
  type MainMenuCaseStatusFilter,
} from './userUiPreferences'
import {
  effectiveColumnWidths,
  LEGACY_AUTO_MAIN_MENU_COLUMN_WIDTHS,
  LEGACY_AUTO_TASKS_MENU_COLUMN_WIDTHS,
} from './columnGridDefaults'
import { useColumnWidths } from './useColumnWidths'
import { normalizeUiPreferences } from './userUiPreferences'
import { AppSidebar } from './AppSidebar'
import { usePrimaryNavKeyboard, type PrimaryNavId } from './usePrimaryNavKeyboard'
import { useDialogs } from './DialogProvider'
import { useNotifications, useNotificationsUserScope } from './NotificationsProvider'
import { SearchInput } from './SearchInput'
import { canaryDocumentTitle } from './tabTitle'
import {
  isQuoteWorkflowStatus,
  userCanAccessAccountsWorkspace,
  userCanAccessAdminConsole,
  userIsCashierAccountsHome,
  userIsMasterRecovery,
} from './types'
import type {
  CaseOut,
  TaskMenuRow,
  UserSummary,
} from './types'
import { SingleSelectDropdown } from './SingleSelectDropdown'
import type { CaseOpenDocPanel } from './case/CaseDetail'
import { useAuth } from './auth/useAuth'
import { LoginForm, ResetPasswordForm } from './auth/LoginScreens'
import { PasswordChangeSessionGate, SecondFactorSessionGate } from './auth/SessionGates'
import {
  sessionNeedsPasswordChange,
  sessionNeedsVerifiedSecondFactor,
  userNeedsSecondFactorSetup,
} from './auth/sessionFlags'
import { NewMatterModal } from './NewMatterModal'
import { MainMenuCasesPanel } from './mainMenuCases'
import { UserSettingsPage } from './UserSettingsPage'
import { Contacts } from './ContactsPage'

const AdminConsole = lazy(() =>
  import('./AdminConsole').then((m) => ({ default: m.AdminConsole })),
)
const RecoveryConsole = lazy(() =>
  import('./AdminConsole').then((m) => ({ default: m.RecoveryConsole })),
)
const CalendarPage = lazy(() => import('./CalendarPage').then((m) => ({ default: m.CalendarPage })))
const DocusignPage = lazy(() => import('./DocusignPage').then((m) => ({ default: m.DocusignPage })))
const ReportsPage = lazy(() => import('./ReportsPage').then((m) => ({ default: m.ReportsPage })))
const AccountsPage = lazy(() => import('./AccountsPage').then((m) => ({ default: m.AccountsPage })))

function LazyFallback() {
  return (
    <div className="muted" style={{ padding: 24 }}>
      Loading…
    </div>
  )
}


type View =
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

function canaryViewTitleSegment(view: View, caseDetail: CaseOut | null): string {
  switch (view) {
    case 'main-menu':
      return 'Cases'
    case 'quotes':
      return 'Quotes'
    case 'case-menu': {
      const desc = caseDetail?.matter_description?.trim()
      if (desc) return desc
      const ref = caseDetail?.case_number?.trim()
      return ref || 'Case'
    }
    case 'tasks':
      return 'Tasks'
    case 'contacts':
      return 'Contacts'
    case 'docusign':
      return 'DocuSign'
    case 'calendar':
      return 'Calendar'
    case 'accounts':
      return 'Accounts'
    case 'reports':
      return 'Reports'
    case 'user-settings':
      return 'User Settings'
    case 'admin-console':
      return 'Admin Settings'
  }
}


function App({ initialTasksCaseFilter }: { initialTasksCaseFilter?: string | null } = {}) {
  const auth = useAuth()

  useEffect(() => {
    releaseAllBodyCursorLocks()
    function onPageShow() {
      releaseAllBodyCursorLocks()
    }
    window.addEventListener('pageshow', onPageShow)
    return () => window.removeEventListener('pageshow', onPageShow)
  }, [])

  const bootNav = useMemo(() => readBootNavigation(initialTasksCaseFilter), [initialTasksCaseFilter])
  const [resetToken, setResetToken] = useState<string | null>(() => {
    try {
      return new URLSearchParams(window.location.search).get('reset_token')
    } catch {
      return null
    }
  })
  const clearResetToken = useCallback(() => {
    setResetToken(null)
    try {
      const url = new URL(window.location.href)
      url.searchParams.delete('reset_token')
      window.history.replaceState({}, '', url.pathname + url.search + url.hash)
    } catch {
      // ignore
    }
  }, [])
  useServerAppearance(auth.me, auth.token)
  const { askConfirm, alert } = useDialogs()
  const [view, setViewState] = useState<View>(bootNav.view)
  const viewRef = useRef(view)
  viewRef.current = view
  const caseTitleDetailRef = useRef<CaseOut | null>(null)
  const [caseTitleDetail, setCaseTitleDetail] = useState<CaseOut | null>(null)
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(bootNav.caseId)
  const [showNewMatter, setShowNewMatter] = useState(false)

  // Cases
  const [cases, setCases] = useState<CaseOut[]>([])
  const [, setCasesBusy] = useState(false)
  const [casesErr, setCasesErr] = useState<string | null>(null)
  const [caseListFocusId, setCaseListFocusId] = useState<string | null>(bootNav.caseId)
  const [caseOpenDocPanel, setCaseOpenDocPanel] = useState<CaseOpenDocPanel | null>(null)
  const consumeCaseOpenDocPanel = useCallback(() => setCaseOpenDocPanel(null), [])
  const [taskMenuRows, setTaskMenuRows] = useState<TaskMenuRow[]>([])
  const [taskMenuCaseFilter, setTaskMenuCaseFilter] = useState<string | null>(bootNav.tasksCaseFilter)
  const [globalTaskCreateOpen, setGlobalTaskCreateOpen] = useState(false)
  const [tasksMenuFilterOpen, setTasksMenuFilterOpen] = useState(false)
  const [tasksLayoutOpen, setTasksLayoutOpen] = useState(false)
  const [tasksFilterMatterTypeOpen, setTasksFilterMatterTypeOpen] = useState(false)

  const [caseListUsers, setCaseListUsers] = useState<UserSummary[]>([])
  const canAdminConsole = userCanAccessAdminConsole(auth.me)
  const canAdminConsoleRef = useRef(canAdminConsole)
  canAdminConsoleRef.current = canAdminConsole
  const canAccessAccounts = userCanAccessAccountsWorkspace(auth.me)
  const canAccessAccountsRef = useRef(canAccessAccounts)
  canAccessAccountsRef.current = canAccessAccounts
  const [docusignEnabled, setDocusignEnabled] = useState<boolean | null>(null)
  const docusignEnabledRef = useRef(docusignEnabled)
  docusignEnabledRef.current = docusignEnabled
  const [reportsInitialTab, setReportsInitialTab] = useState<
    'client_account_reconcile' | null
  >(null)
  const [cashierMainMenuExplicit, setCashierMainMenuExplicit] = useState(false)
  const cashierMainMenuExplicitRef = useRef(cashierMainMenuExplicit)
  cashierMainMenuExplicitRef.current = cashierMainMenuExplicit

  const token = auth.token ?? undefined
  const [taskMenuSearch, setTaskMenuSearch] = useState('')
  const [taskMenuFilterMatterType, setTaskMenuFilterMatterType] = useState('')
  const [mainMenuFilterMatterTypes, setMainMenuFilterMatterTypes] = useState<string[]>([])
  const [mainMenuFilterFeeEarnerUserIds, setMainMenuFilterFeeEarnerUserIds] = useState<string[]>([])
  const [mainMenuFilterCaseStatuses, setMainMenuFilterCaseStatuses] = useState<MainMenuCaseStatusFilter[]>([])
  const [quotesFilterMatterTypes, setQuotesFilterMatterTypes] = useState<string[]>([])
  const [quotesFilterFeeEarnerUserIds, setQuotesFilterFeeEarnerUserIds] = useState<string[]>([])
  const [quotesFilterCaseStatuses, setQuotesFilterCaseStatuses] = useState<MainMenuCaseStatusFilter[]>(['quote'])
  const [quotesSubPanel, setQuotesSubPanel] = useState<'list' | 'fee-scales' | 'sources'>(bootNav.quotesSubPanel)
  const [quoteWizardOpen, setQuoteWizardOpen] = useState(false)
  const [newMatterFromQuotes, setNewMatterFromQuotes] = useState(false)
  const [quoteWizardPendingCaseId, setQuoteWizardPendingCaseId] = useState<string | null>(null)
  const [quoteAwaitingSave, setQuoteAwaitingSave] = useState<QuoteAwaitingSaveContext | null>(null)
  const [quoteSendOpen, setQuoteSendOpen] = useState(false)
  const [pendingComposeKind, setPendingComposeKind] = useState<PendingCaseCompose | null>(null)

  const selectedCaseIdRef = useRef(selectedCaseId)
  selectedCaseIdRef.current = selectedCaseId
  const quotesSubPanelRef = useRef(quotesSubPanel)
  quotesSubPanelRef.current = quotesSubPanel
  const taskMenuCaseFilterRef = useRef(taskMenuCaseFilter)
  taskMenuCaseFilterRef.current = taskMenuCaseFilter

  const syncNavFromState = useCallback(
    (patch: Partial<AppNavState> & { view?: View }, mode: 'push' | 'replace' = 'push') => {
      const v = patch.view ?? viewRef.current
      const next: AppNavState = {
        view: v,
        caseId:
          patch.caseId !== undefined ? patch.caseId : v === 'case-menu' ? selectedCaseIdRef.current : null,
        quotesSubPanel: patch.quotesSubPanel ?? quotesSubPanelRef.current,
        tasksCaseFilter: patch.tasksCaseFilter ?? taskMenuCaseFilterRef.current,
      }
      syncAppNavigationUrl(next, mode)
    },
    [],
  )

  const setView = useCallback(
    async (next: View, opts?: { skipExitConfirm?: boolean }): Promise<boolean> => {
      if (next === 'admin-console' && !canAdminConsoleRef.current) {
        next = 'main-menu'
      }
      if (next === 'accounts' && !canAccessAccountsRef.current) {
        next = 'main-menu'
      }
      if (next === 'docusign' && docusignEnabledRef.current !== true) {
        next = 'main-menu'
      }
      if (viewRef.current === 'case-menu' && next !== 'case-menu' && !opts?.skipExitConfirm) {
        const ok = await askConfirm({
          title: 'Exit matter',
          message: 'Are you sure you want to exit this matter?',
          confirmLabel: 'Exit matter',
          cancelLabel: 'Stay here',
        })
        if (!ok) return false
      }
      setViewState(next)
      syncNavFromState({ view: next, caseId: next === 'case-menu' ? selectedCaseIdRef.current : null })
      return true
    },
    [askConfirm, syncNavFromState],
  )

  const goMainMenu = useCallback(async (opts?: { skipExitConfirm?: boolean }) => {
    if (!(await setView('main-menu', opts))) return
    if (userIsCashierAccountsHome(auth.me)) {
      setCashierMainMenuExplicit(true)
    }
  }, [auth.me, setView])

  const primaryNavHandlers = useMemo(
    (): Record<PrimaryNavId, () => void> => ({
      'main-menu': goMainMenu,
      quotes: async () => {
        if (!(await setView('quotes'))) return
        setQuotesSubPanel('list')
      },
      calendar: () => setView('calendar'),
      tasks: () => setView('tasks'),
      contacts: () => setView('contacts'),
      docusign: () => setView('docusign'),
      accounts: () => setView('accounts'),
      reports: () => setView('reports'),
      'user-settings': () => setView('user-settings'),
      'admin-console': () => setView('admin-console'),
    }),
    [goMainMenu, setView],
  )

  const caseMenuQuoteContext = useMemo(() => {
    if (view !== 'case-menu' || !selectedCaseId) return false
    if (caseTitleDetail?.id === selectedCaseId) {
      return isQuoteWorkflowStatus(caseTitleDetail.status)
    }
    const row = cases.find((c) => c.id === selectedCaseId)
    return row ? isQuoteWorkflowStatus(row.status) : false
  }, [view, selectedCaseId, caseTitleDetail, cases])

  usePrimaryNavKeyboard({
    enabled: Boolean(token),
    view,
    caseMenuQuoteContext,
    canAccessAccounts,
    canAdminConsole,
    docusignEnabled: docusignEnabled === true,
    onNavigate: primaryNavHandlers,
  })

  const confirmLogout = useCallback(async () => {
    const ok = await askConfirm({
      title: 'Sign out',
      message: 'Are you sure you want to sign out of Canary?',
      confirmLabel: 'Sign out',
      cancelLabel: 'Cancel',
    })
    if (ok) auth.logout()
  }, [askConfirm, auth.logout])

  const { prefs: uiPrefs, setPreference: setUiPreference, setPreferenceDebounced: setUiPreferenceDebounced } =
    useUserUiPreferences(auth.me, auth.token)

  const onMainMenuFilterMatterTypesChange = useCallback((value: string[]) => {
    setMainMenuFilterMatterTypes(value)
  }, [])

  const onMainMenuFilterFeeEarnerIdsChange = useCallback((value: string[]) => {
    setMainMenuFilterFeeEarnerUserIds(value)
  }, [])

  const onMainMenuFilterCaseStatusesChange = useCallback((value: MainMenuCaseStatusFilter[]) => {
    setMainMenuFilterCaseStatuses(value)
  }, [])

  const onQuotesFilterMatterTypesChange = useCallback((value: string[]) => {
    setQuotesFilterMatterTypes(value)
  }, [])
  const onQuotesFilterFeeEarnerIdsChange = useCallback((value: string[]) => {
    setQuotesFilterFeeEarnerUserIds(value)
  }, [])
  const onQuotesFilterCaseStatusesChange = useCallback((value: MainMenuCaseStatusFilter[]) => {
    setQuotesFilterCaseStatuses(value)
  }, [])
  const persistQuotesFilters = useCallback(
    (_matterTypes: string[], _feeEarnerUserIds: string[], _caseStatuses: MainMenuCaseStatusFilter[]) => {
      /* Quotes filters are session-local; default status Quote on first load. */
    },
    [],
  )

  const persistMainMenuFilters = useCallback(
    (matterTypes: string[], feeEarnerUserIds: string[], caseStatuses: MainMenuCaseStatusFilter[]) => {
      setUiPreference('main_menu_filter_matter_types', matterTypes)
      setUiPreference('main_menu_filter_fee_earner_user_ids', feeEarnerUserIds)
      setUiPreference('main_menu_filter_case_statuses', caseStatuses)
    },
    [setUiPreference],
  )

  const { gridTemplateColumns: casesGridColumns, startResize: casesStartResize } = useColumnWidths(
    MAIN_MENU_COLUMN_COUNT,
    {
      widths: effectiveColumnWidths(
        uiPrefs.main_menu_column_widths,
        MAIN_MENU_COLUMN_COUNT,
        LEGACY_AUTO_MAIN_MENU_COLUMN_WIDTHS,
      ),
      fallbackWidths: [...MAIN_MENU_COLUMN_WIDTHS_DEFAULT],
      onChange: (widths) => setUiPreferenceDebounced('main_menu_column_widths', widths, 300),
    },
  )

  const { gridTemplateColumns: tasksGridColumns, startResize: tasksStartResize } = useColumnWidths(
    TASKS_MENU_COLUMN_COUNT,
    {
      widths: effectiveColumnWidths(
        uiPrefs.tasks_menu_column_widths,
        TASKS_MENU_COLUMN_COUNT,
        LEGACY_AUTO_TASKS_MENU_COLUMN_WIDTHS,
      ),
      fallbackWidths: [...TASKS_MENU_COLUMN_WIDTHS_DEFAULT],
      onChange: (widths) => setUiPreferenceDebounced('tasks_menu_column_widths', widths, 300),
    },
  )

  const tasksMenuActiveFilterCount = useMemo(
    () => (taskMenuFilterMatterType ? 1 : 0),
    [taskMenuFilterMatterType],
  )

  const tasksMenuMatterTypeOptions = useMemo(() => {
    const s = new Set<string>()
    for (const r of taskMenuRows) {
      if (r.matter_type_label.trim()) s.add(r.matter_type_label)
    }
    return Array.from(s).sort((a, b) => a.localeCompare(b))
  }, [taskMenuRows])

  const tasksFilterMatterTypeOptions = useMemo(
    () => [
      { value: '', label: 'All' },
      ...tasksMenuMatterTypeOptions.map((label) => ({ value: label, label })),
    ],
    [tasksMenuMatterTypeOptions],
  )

  const taskLayoutOptions = useMemo(
    () => [
      { value: 'list', label: 'List' },
      { value: 'kanban', label: 'Kanban' },
    ],
    [],
  )

  useEffect(() => {
    if (!token) return
    let cancelled = false
    async function load() {
      try {
        const data = await apiFetch<UserSummary[]>('/users', { token })
        if (!cancelled) setCaseListUsers((Array.isArray(data) ? data : []).filter((u) => u.is_active))
      } catch {
        if (!cancelled) setCaseListUsers([])
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [token])

  async function refreshCases() {
    if (!token) return
    setCasesBusy(true)
    setCasesErr(null)
    try {
      const data = await apiFetch<CaseOut[]>('/cases', { token })
      setCases(Array.isArray(data) ? data : [])
    } catch (e: any) {
      setCasesErr(e?.message ?? 'Failed to load cases')
    } finally {
      setCasesBusy(false)
    }
  }

  const refreshTaskMenu = useCallback(async () => {
    if (!token) return
    try {
      const q = taskMenuCaseFilter ? `?case_id=${encodeURIComponent(taskMenuCaseFilter)}` : ''
      const data = await apiFetch<TaskMenuRow[]>(`/tasks${q}`, { token })
      setTaskMenuRows(Array.isArray(data) ? data : [])
    } catch {
      setTaskMenuRows([])
    }
  }, [token, taskMenuCaseFilter])

  useEffect(() => {
    if (!token) return
    void refreshCases()
  }, [token])

  useEffect(() => {
    if (!token || view !== 'tasks') return
    void refreshTaskMenu()
  }, [token, view, refreshTaskMenu])

  useEffect(() => {
    if (view !== 'tasks') {
      setTasksMenuFilterOpen(false)
      setTasksLayoutOpen(false)
      setTasksFilterMatterTypeOpen(false)
    }
  }, [view])

  useEffect(() => {
    syncNavFromState({}, 'replace')
  }, [syncNavFromState])

  useEffect(() => {
    if (view !== 'case-menu') setCaseTitleDetail(null)
  }, [view])

  const onCaseTitleDetailChange = useCallback((detail: CaseOut | null) => {
    caseTitleDetailRef.current = detail
    setCaseTitleDetail(detail)
    if (viewRef.current === 'case-menu') {
      document.title = canaryDocumentTitle(canaryViewTitleSegment('case-menu', detail))
    }
  }, [])

  const onPendingComposeConsumed = useCallback(() => {
    setPendingComposeKind(null)
  }, [])

  const onQuotePublished = useCallback(() => {
    setQuoteSendOpen(true)
  }, [])

  const onQuoteDiscarded = useCallback(() => {
    setQuoteAwaitingSave(null)
  }, [])

  useQuoteAwaitingSave(quoteAwaitingSave, {
    onPublished: onQuotePublished,
    onDiscarded: onQuoteDiscarded,
  })

  const onCaseListInvalidate = useCallback(() => {
    void refreshCases()
  }, [token])

  const onTaskMenuInvalidate = useCallback(() => {
    void refreshTaskMenu()
  }, [refreshTaskMenu])

  useEffect(() => {
    if (!auth.token) setCashierMainMenuExplicit(false)
  }, [auth.token])

  useEffect(() => {
    if (auth.loading || !auth.me) return
    if (!userIsCashierAccountsHome(auth.me)) return
    if (cashierMainMenuExplicitRef.current) return
    if (viewRef.current !== 'main-menu') return
    const path = window.location.pathname.replace(/\/+$/, '') || '/'
    if (path !== '/' && path !== '/main') return
    setViewState('accounts')
    syncNavFromState({ view: 'accounts', caseId: null }, 'replace')
  }, [auth.loading, auth.me, syncNavFromState])

  useEffect(() => {
    if (!auth.me || canAdminConsole) return
    if (viewRef.current !== 'admin-console') return
    setViewState('main-menu')
    syncNavFromState({ view: 'main-menu', caseId: null }, 'replace')
  }, [auth.me, canAdminConsole, syncNavFromState])

  useEffect(() => {
    if (!token) {
      setDocusignEnabled(false)
      return
    }
    setDocusignEnabled(null)
    void apiFetch<{ enabled: boolean }>('/docusign/options', { token })
      .then((o) => setDocusignEnabled(Boolean(o.enabled)))
      .catch(() => setDocusignEnabled(false))
  }, [token])

  useEffect(() => {
    if (!auth.me || canAccessAccounts) return
    if (viewRef.current !== 'accounts') return
    setViewState('main-menu')
    syncNavFromState({ view: 'main-menu', caseId: null }, 'replace')
  }, [auth.me, canAccessAccounts, syncNavFromState])

  useEffect(() => {
    if (docusignEnabled !== false) return
    if (viewRef.current !== 'docusign') return
    setViewState('main-menu')
    syncNavFromState({ view: 'main-menu', caseId: null }, 'replace')
  }, [docusignEnabled, syncNavFromState])

  useEffect(() => {
    function onPopState() {
      const parsed = parseAppNavigation(window.location)
      const nav = sanitizeAppNavigation(
        parsed,
        canAdminConsoleRef.current,
        canAccessAccountsRef.current,
        docusignEnabledRef.current === true,
      )
      if (nav.view !== parsed.view) {
        syncAppNavigationUrl(nav, 'replace')
      }
      setViewState(nav.view)
      setSelectedCaseId(nav.caseId)
      if (nav.caseId) setCaseListFocusId(nav.caseId)
      setQuotesSubPanel(nav.quotesSubPanel)
      setTaskMenuCaseFilter(nav.tasksCaseFilter)
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  const openCaseView = useCallback(
    (caseId: string) => {
      setSelectedCaseId(caseId)
      setViewState('case-menu')
      syncNavFromState({ view: 'case-menu', caseId })
    },
    [syncNavFromState],
  )

  const onMainMenuSelectCase = useCallback(
    (id: string, opts?: { docPanel?: CaseOpenDocPanel }) => {
      setCaseListFocusId(id)
      setCaseOpenDocPanel(opts?.docPanel ?? null)
      openCaseView(id)
    },
    [openCaseView],
  )

  const onMainMenuSort = useCallback(
    (k: 'reference' | 'client' | 'matter' | 'feeEarner' | 'status' | 'source' | 'created') => {
      if (k === uiPrefs.main_menu_sort_key) {
        setUiPreference('main_menu_sort_dir', uiPrefs.main_menu_sort_dir === 'asc' ? 'desc' : 'asc')
      } else {
        setUiPreference('main_menu_sort_key', k)
        setUiPreference('main_menu_sort_dir', 'asc')
      }
    },
    [setUiPreference, uiPrefs.main_menu_sort_dir, uiPrefs.main_menu_sort_key],
  )

  const onOpenNewMatter = useCallback(() => {
    setNewMatterFromQuotes(false)
    setShowNewMatter(true)
  }, [])
  const onCloseNewMatter = useCallback(() => {
    setShowNewMatter(false)
    setNewMatterFromQuotes(false)
  }, [])
  const onRefreshCases = useCallback(() => refreshCases(), [token])

  const [quoteConvertCaseId, setQuoteConvertCaseId] = useState<string | null>(null)
  const { push: pushNotification } = useNotifications()
  const { setUserId: setNotificationsUserId } = useNotificationsUserScope()
  useEffect(() => {
    setNotificationsUserId(auth.me?.id ?? null)
  }, [auth.me?.id, setNotificationsUserId])

  const onQuoteConvert = useCallback(
    (caseId: string) => {
      if (!cases.some((c) => c.id === caseId && c.status === 'quote')) return
      setQuoteConvertCaseId(caseId)
    },
    [cases],
  )

  const quoteConvertCase = useMemo(() => {
    if (!quoteConvertCaseId) return null
    const row = cases.find((c) => c.id === quoteConvertCaseId)
    return row?.status === 'quote' ? row : null
  }, [quoteConvertCaseId, cases])

  const onQuoteConverted = useCallback(
    async ({ caseId, openAfter }: { caseId: string; openAfter: boolean }) => {
      setQuoteConvertCaseId(null)
      setCases((prev) => prev.map((c) => (c.id === caseId ? { ...c, status: 'open' as const } : c)))
      await refreshCases()
      pushNotification('Quote converted to Active.')
      if (openAfter) openCaseView(caseId)
    },
    [openCaseView, refreshCases, pushNotification],
  )

  const onQuoteClose = useCallback(
    async (caseId: string) => {
      if (!token) return
      try {
        const blockMsg = await closeMatterBlockMessage(token, caseId)
        if (blockMsg) {
          void alert(blockMsg, 'Cannot close matter')
          return
        }
      } catch {
        /* fall through — server will reject if balances are non-zero */
      }
      const ok = await askConfirm({
        title: 'Close matter',
        message: 'Do you want to close this matter?',
        confirmLabel: 'Yes',
        cancelLabel: 'No',
      })
      if (!ok || !token) return
      try {
        await apiFetch(`/cases/${caseId}`, { method: 'PATCH', token, json: { status: 'quote_closed' } })
        void refreshCases()
      } catch (e: unknown) {
        const msg =
          e && typeof e === 'object' && 'message' in e
            ? String((e as { message?: string }).message)
            : 'Could not close matter'
        void alert(msg, 'Close matter')
      }
    },
    [alert, askConfirm, token],
  )

  const onMainMenuCaseCreated = useCallback(
    async (created?: CaseOut) => {
      setShowNewMatter(false)
      await refreshCases()
      if (!created?.id) return
      if (newMatterFromQuotes) {
        setQuoteWizardPendingCaseId(created.id)
        setQuoteWizardOpen(true)
        setNewMatterFromQuotes(false)
      } else {
        setCaseListFocusId(created.id)
        openCaseView(created.id)
      }
    },
    [newMatterFromQuotes, openCaseView],
  )

  const mainMenuFiltersLoadedForUser = useRef<string | null>(null)
  useEffect(() => {
    if (!auth.me?.id) {
      mainMenuFiltersLoadedForUser.current = null
      return
    }
    if (mainMenuFiltersLoadedForUser.current === auth.me.id) return
    mainMenuFiltersLoadedForUser.current = auth.me.id
    const saved = normalizeUiPreferences(auth.me.ui_preferences)
    setMainMenuFilterMatterTypes(saved.main_menu_filter_matter_types)
    setMainMenuFilterFeeEarnerUserIds(saved.main_menu_filter_fee_earner_user_ids)
    setMainMenuFilterCaseStatuses(saved.main_menu_filter_case_statuses.filter((s) => s !== 'quote' && s !== 'quote_closed'))
  }, [auth.me?.id])

  function renderMainContent() {
    if (!token) return null
    if (view === 'main-menu') return null
    if (view === 'quotes') {
      if (quotesSubPanel === 'fee-scales') {
        return <FeeScalesPanel token={token} onBack={() => setQuotesSubPanel('list')} />
      }
      if (quotesSubPanel === 'sources') {
        return <QuoteSourcesPanel token={token} me={auth.me} onBack={() => setQuotesSubPanel('list')} />
      }
      return null
    }

    if (view === 'admin-console') {
      if (!auth.me || !canAdminConsole) return null
      return (
        <Suspense fallback={<LazyFallback />}>
          <AdminConsole token={token} refreshMe={auth.refreshMe} />
        </Suspense>
      )
    }
    if (view === 'user-settings')
      return <UserSettingsPage token={token} refreshMe={auth.refreshMe} applySessionToken={auth.applySessionToken} />
    if (view === 'calendar')
      return (
        <Suspense fallback={<LazyFallback />}>
          <CalendarPage token={token} me={auth.me} onOpenSettings={() => setView('user-settings')} />
        </Suspense>
      )
    if (view === 'contacts') return <Contacts token={token} me={auth.me} />
    if (view === 'docusign') {
      if (docusignEnabled !== true) return null
      return (
        <Suspense fallback={<LazyFallback />}>
          <DocusignPage token={token} onSelectCase={openCaseView} />
        </Suspense>
      )
    }

    if (view === 'accounts') {
      if (!canAccessAccounts) return null
      return (
        <Suspense fallback={<LazyFallback />}>
          <AccountsPage
          token={token}
          me={auth.me}
          onOpenCase={openCaseView}
          onOpenReportsReconcile={() => {
            setReportsInitialTab('client_account_reconcile')
            setView('reports')
          }} />
        </Suspense>
      )
    }

    if (view === 'reports') {
      return (
        <Suspense fallback={<LazyFallback />}>
          <ReportsPage
          token={token}
          me={auth.me}
          initialTab={reportsInitialTab ?? undefined}
          onInitialTabConsumed={() => setReportsInitialTab(null)} />
        </Suspense>
      )
    }

    if (view === 'case-menu' && selectedCaseId) {
      return (
        <CaseViewRoute
          token={token}
          caseId={selectedCaseId}
          currentUser={auth.me}
          openDocPanel={caseOpenDocPanel}
          onOpenDocPanelConsumed={consumeCaseOpenDocPanel}
          pendingComposeKind={pendingComposeKind}
          onPendingComposeConsumed={onPendingComposeConsumed}
          onCaseListInvalidate={onCaseListInvalidate}
          onTaskMenuInvalidate={onTaskMenuInvalidate}
          onCaseDetailChange={onCaseTitleDetailChange}
          onBackToMainMenu={() => {
            if (caseMenuQuoteContext) void setView('quotes', { skipExitConfirm: true })
            else void goMainMenu({ skipExitConfirm: true })
          }}
          backNavLabel={caseMenuQuoteContext ? 'Back to quotes' : 'Back to main menu'}
        />
      )
    }

    if (view === 'tasks') {
      return (
        <>
        <div className="mainMenuShell mainMenuShell--mainMenu">
          <div className={`mainMenuFilterBar${tasksMenuFilterOpen ? ' mainMenuFilterBar--dropdownOpen' : ''}`}>
            <div className="row mainMenuFilterRow mainMenuFilterRow--toolbar mainMenuFilterRow--searchRight">
              <div className="mainMenuFilterRowLeft">
                {taskMenuCaseFilter ? (
                  <button type="button" className="btn" onClick={() => setTaskMenuCaseFilter(null)}>
                    Show all tasks
                  </button>
                ) : null}
                <button type="button" className="btn primary toolbarLeadBtn" onClick={() => setGlobalTaskCreateOpen(true)}>
                  New task
                </button>
                <div className="tasksToolbarLayoutGroup">
                  <span className="tasksToolbarLayoutLabel">View</span>
                  <SingleSelectDropdown
                    hideLabel
                    label="Task layout"
                    options={taskLayoutOptions}
                    value={uiPrefs.tasks_menu_layout}
                    onChange={(v) => setUiPreference('tasks_menu_layout', v as 'list' | 'kanban')}
                    open={tasksLayoutOpen}
                    onOpenChange={setTasksLayoutOpen}
                  />
                </div>
                <button
                  type="button"
                  className="btn"
                  onClick={() => {
                    void refreshCases()
                    void refreshTaskMenu()
                  }}
                >
                  Refresh
                </button>
                <button
                  type="button"
                  className="btn"
                  onClick={() => void (async () => {
                    if (!token) return
                    const ok = await askConfirm({
                      title: 'Clear completed tasks',
                      message: taskMenuCaseFilter
                        ? 'Remove all completed tasks for this matter from the list?'
                        : 'Remove all of your completed tasks from the list?',
                    })
                    if (!ok) return
                    try {
                      const q = taskMenuCaseFilter ? `?case_id=${encodeURIComponent(taskMenuCaseFilter)}` : ''
                      await apiFetch(`/tasks/completed${q}`, { token, method: 'DELETE' })
                      void refreshTaskMenu()
                    } catch {
                      // ignore
                    }
                  })()}
                >
                  Clear completed tasks
                </button>
              </div>
              <div className="mainMenuFilterRowRight">
                <div className="caseToolbarDropdownWrap">
                  <button
                    type="button"
                    className="btn mainMenuFilterBtn"
                    aria-expanded={tasksMenuFilterOpen}
                    aria-haspopup="true"
                    aria-controls="tasks-menu-filter-menu"
                    id="tasks-menu-filter-button"
                    onClick={(e) => {
                      e.stopPropagation()
                      setTasksMenuFilterOpen((o) => !o)
                    }}
                  >
                    <span className="mainMenuFilterBtnInner">
                      <svg
                        className="mainMenuFilterBtnIcon"
                        width={16}
                        height={16}
                        viewBox="0 0 24 24"
                        fill="none"
                        xmlns="http://www.w3.org/2000/svg"
                        aria-hidden
                      >
                        <polygon
                          points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          fill="none"
                        />
                      </svg>
                      <span>Filter</span>
                      <span className="mainMenuFilterBtnCount">({tasksMenuActiveFilterCount})</span>
                    </span>
                  </button>
                  {tasksMenuFilterOpen ? (
                    <div
                      id="tasks-menu-filter-menu"
                      className="caseToolbarDropdown mainMenuFilterDropdown"
                      role="group"
                      aria-labelledby="tasks-menu-filter-button"
                      onMouseDown={(e) => e.stopPropagation()}
                    >
                      <div className="stack mainMenuFilterDropdownBody">
                        <SingleSelectDropdown
                          label="Matter type"
                          options={tasksFilterMatterTypeOptions}
                          value={taskMenuFilterMatterType}
                          onChange={setTaskMenuFilterMatterType}
                          open={tasksFilterMatterTypeOpen}
                          onOpenChange={setTasksFilterMatterTypeOpen}
                          placeholder="All"
                        />
                      </div>
                    </div>
                  ) : null}
                </div>
            <SearchInput
              placeholder="Search"
              value={taskMenuSearch}
              onChange={(e) => setTaskMenuSearch(e.target.value)}
              onClear={() => setTaskMenuSearch('')}
              className="mainMenuSearchInput"
              aria-label="Search tasks"
            />
              </div>
            </div>
          </div>
          <TasksTable
            token={token}
            currentUserId={auth.me?.id ?? ''}
            users={caseListUsers}
            rows={taskMenuRows}
            layoutMode={uiPrefs.tasks_menu_layout}
            search={taskMenuSearch}
            filterMatterType={taskMenuFilterMatterType}
            gridTemplateColumns={tasksGridColumns}
            startColumnResize={tasksStartResize}
            onSelectCase={(caseId) => {
              openCaseView(caseId)
            }}
            sortKey={uiPrefs.tasks_menu_sort_key}
            sortDir={uiPrefs.tasks_menu_sort_dir}
            onSort={(k) => {
              if (k === uiPrefs.tasks_menu_sort_key) {
                setUiPreference('tasks_menu_sort_dir', uiPrefs.tasks_menu_sort_dir === 'asc' ? 'desc' : 'asc')
              } else {
                setUiPreference('tasks_menu_sort_key', k)
                setUiPreference('tasks_menu_sort_dir', k === 'priority' ? 'desc' : 'asc')
              }
            }}
            onInvalidate={() => void refreshTaskMenu()}
          />
        </div>
        <TaskCreateModal
          open={globalTaskCreateOpen}
          token={token}
          users={caseListUsers}
          caseIdFixed={null}
          preset={null}
          onClose={() => setGlobalTaskCreateOpen(false)}
          onCreated={() => void refreshTaskMenu()}
        />
        </>
      )
    }

    return null
  }

  const mainMenuCasesPanel = token ? (
    <MainMenuCasesPanel
      cases={cases}
      casesErr={casesErr}
      users={caseListUsers}
      filterMatterTypes={mainMenuFilterMatterTypes}
      filterFeeEarnerUserIds={mainMenuFilterFeeEarnerUserIds}
      filterCaseStatuses={mainMenuFilterCaseStatuses}
      onFilterMatterTypesChange={onMainMenuFilterMatterTypesChange}
      onFilterFeeEarnerIdsChange={onMainMenuFilterFeeEarnerIdsChange}
      onFilterCaseStatusesChange={onMainMenuFilterCaseStatusesChange}
      onPersistFilters={persistMainMenuFilters}
      gridTemplateColumns={casesGridColumns}
      startColumnResize={casesStartResize}
      caseListFocusId={caseListFocusId}
      onCaseRowFocus={setCaseListFocusId}
      onSelectCase={onMainMenuSelectCase}
      sortKey={uiPrefs.main_menu_sort_key}
      sortDir={uiPrefs.main_menu_sort_dir}
      onSort={onMainMenuSort}
      onOpenNewMatter={onOpenNewMatter}
      onRefreshCases={onRefreshCases}
      keyboardActive={view === 'main-menu'}
    />
  ) : null

  const quotesFeeScalesButton = useMemo(
    () => (
      <>
        <button type="button" className="btn" onClick={() => setQuotesSubPanel('sources')}>
          Sources
        </button>
        <button type="button" className="btn" onClick={() => setQuotesSubPanel('fee-scales')}>
          Fee scales
        </button>
      </>
    ),
    [],
  )

  const quotesCasesPanel = token ? (
    <MainMenuCasesPanel
      cases={cases}
      casesErr={casesErr}
      users={caseListUsers}
      filterMatterTypes={quotesFilterMatterTypes}
      filterFeeEarnerUserIds={quotesFilterFeeEarnerUserIds}
      filterCaseStatuses={quotesFilterCaseStatuses}
      onFilterMatterTypesChange={onQuotesFilterMatterTypesChange}
      onFilterFeeEarnerIdsChange={onQuotesFilterFeeEarnerIdsChange}
      onFilterCaseStatusesChange={onQuotesFilterCaseStatusesChange}
      onPersistFilters={persistQuotesFilters}
      gridTemplateColumns={casesGridColumns}
      startColumnResize={casesStartResize}
      showSourceColumn
      caseListFocusId={caseListFocusId}
      onCaseRowFocus={setCaseListFocusId}
      onSelectCase={onMainMenuSelectCase}
      sortKey={uiPrefs.main_menu_sort_key}
      sortDir={uiPrefs.main_menu_sort_dir}
      onSort={onMainMenuSort}
      onOpenNewMatter={onOpenNewMatter}
      onRefreshCases={onRefreshCases}
      createButtonLabel="New quote"
      onCreateClick={() => setQuoteWizardOpen(true)}
      toolbarMiddle={quotesFeeScalesButton}
      contextMenuVariant="quotes"
      onQuoteConvert={onQuoteConvert}
      onQuoteClose={onQuoteClose}
      keyboardActive={view === 'quotes' && quotesSubPanel === 'list'}
    />
  ) : null

  useEffect(() => {
    if (auth.loading) {
      document.title = canaryDocumentTitle('Loading…')
      return
    }
    if (!auth.token) {
      document.title = canaryDocumentTitle('Sign in')
      return
    }
    if (auth.me && sessionNeedsVerifiedSecondFactor(auth.me)) {
      document.title = canaryDocumentTitle(
        userNeedsSecondFactorSetup(auth.me) ? 'Security setup' : 'Verify sign-in',
      )
      return
    }
    document.title = canaryDocumentTitle(canaryViewTitleSegment(view, caseTitleDetail))
  }, [auth.loading, auth.token, auth.me, view, caseTitleDetail])

  if (auth.loading) return <div className="center muted">Loading…</div>
  if (!auth.token) {
    if (resetToken) {
      return <ResetPasswordForm token={resetToken} onDone={clearResetToken} />
    }
    return (
      <LoginForm
        onLogin={auth.login}
        onPasskeyLogin={auth.loginWithPasskey}
        error={auth.loginError}
        onClearError={auth.clearLoginError}
      />
    )
  }

  if (auth.me && sessionNeedsPasswordChange(auth.me)) {
    return (
      <PasswordChangeSessionGate
        token={auth.token}
        me={auth.me}
        onLogout={auth.logout}
        refreshMe={auth.refreshMe}
        applySessionToken={auth.applySessionToken}
      />
    )
  }

  if (auth.me && sessionNeedsVerifiedSecondFactor(auth.me)) {
    return (
      <SecondFactorSessionGate
        token={auth.token}
        me={auth.me}
        onLogout={auth.logout}
        onPasskeyLogin={auth.loginWithPasskey}
        refreshMe={auth.refreshMe}
        applySessionToken={auth.applySessionToken}
        loginError={auth.loginError}
        onClearLoginError={auth.clearLoginError}
      />
    )
  }

  if (auth.me && userIsMasterRecovery(auth.me) && auth.token) {
    return (
      <div className="appShell">
        <header className="topbar topbar--content">
          <div className="topbarMain">
            <nav className="topNav" aria-label="Recovery console">
              <span className="muted" style={{ padding: '6px 10px' }}>
                Master recovery
              </span>
            </nav>
          </div>
          <div className="topbarRight">
            <div className="muted">{auth.me.display_name}</div>
            <button type="button" className="btn" onClick={auth.logout}>
              Sign out
            </button>
          </div>
        </header>
        <main className="main main--mainMenu">
          <Suspense fallback={<LazyFallback />}>
            <RecoveryConsole token={auth.token} />
          </Suspense>
        </main>
      </div>
    )
  }

  return (
    <div className="appShell appShell--sidebar">
      <AdminLoginUpdatePrompt token={auth.token} me={auth.me} canAdmin={canAdminConsole} />
      <AppSidebar
        view={view}
        caseMenuQuoteContext={caseMenuQuoteContext}
        goMainMenu={goMainMenu}
        onQuotes={() => {
          setView('quotes')
          setQuotesSubPanel('list')
        }}
        onCalendar={() => setView('calendar')}
        onTasks={() => setView('tasks')}
        onContacts={() => setView('contacts')}
        onDocusign={() => setView('docusign')}
        onAccounts={() => setView('accounts')}
        onReports={() => setView('reports')}
        onUserSettings={() => setView('user-settings')}
        onAdminConsole={() => setView('admin-console')}
        canAccessAccounts={canAccessAccounts}
        canAdminConsole={canAdminConsole}
        docusignEnabled={docusignEnabled === true}
        onLogout={confirmLogout}
      />
      <div
        className={`appMainColumn${
          view === 'case-menu'
            ? ' appMainColumn--caseView'
            : view === 'main-menu' ||
                view === 'quotes' ||
                view === 'contacts' ||
                view === 'tasks' ||
                view === 'docusign' ||
                view === 'accounts' ||
                view === 'reports'
              ? ' appMainColumn--mainMenu'
              : ''
        }`}
      >
        <main
          className={
            view === 'case-menu'
              ? 'main main--caseView'
              : view === 'main-menu' || view === 'quotes' || view === 'contacts' || view === 'tasks' || view === 'docusign' || view === 'accounts' || view === 'reports'
                ? 'main main--mainMenu'
                : 'main'
          }
        >
        {mainMenuCasesPanel ? (
          <div className={view === 'main-menu' ? 'mainMenuCasesHost' : 'mainMenuCasesHost mainMenuCasesHost--hidden'}>
            {mainMenuCasesPanel}
          </div>
        ) : null}
        {quotesCasesPanel ? (
          <div
            className={
              view === 'quotes' && quotesSubPanel === 'list'
                ? 'mainMenuCasesHost'
                : 'mainMenuCasesHost mainMenuCasesHost--hidden'
            }
          >
            {quotesCasesPanel}
          </div>
        ) : null}
        {showNewMatter && token ? (
          <NewMatterModal
            token={token}
            currentUserId={auth.me?.id ?? ''}
            onClose={onCloseNewMatter}
            onCreated={onMainMenuCaseCreated}
            defaultStatus={newMatterFromQuotes ? 'quote' : 'open'}
          />
        ) : null}
        {quoteWizardOpen && token ? (
          <QuoteWizard
            token={token}
            open={quoteWizardOpen}
            onClose={() => setQuoteWizardOpen(false)}
            onOpenNewMatter={() => {
              setQuoteWizardOpen(false)
              setNewMatterFromQuotes(true)
              setShowNewMatter(true)
            }}
            onCaseCreatedRefresh={onRefreshCases}
            pendingNewCaseId={quoteWizardPendingCaseId}
            onClearPendingNewCase={() => setQuoteWizardPendingCaseId(null)}
            onAwaitingQuoteSave={setQuoteAwaitingSave}
          />
        ) : null}
        {quoteAwaitingSave && token ? (
          <QuoteSendPrompt
            token={token}
            caseId={quoteAwaitingSave.caseId}
            fileId={quoteAwaitingSave.fileId}
            preferredContactId={quoteAwaitingSave.preferredContactId}
            portalEnabled={quoteAwaitingSave.portalEnabled}
            open={quoteSendOpen}
            onClose={() => {
              setQuoteSendOpen(false)
              setQuoteAwaitingSave(null)
            }}
            onSendLetter={(caseId) => {
              openCaseView(caseId)
              setPendingComposeKind({ kind: 'letter' })
            }}
            onSendEmail={(caseId) => {
              openCaseView(caseId)
              setPendingComposeKind({
                kind: 'email',
                preferPrecedentReference: QUOTE_EMAIL_PRECEDENT_REFERENCE,
                attachmentFileId: quoteAwaitingSave.fileId,
              })
            }}
          />
        ) : null}
        {quoteConvertCase && token ? (
          <QuoteConvertModal
            token={token}
            quoteCase={quoteConvertCase}
            users={caseListUsers}
            onClose={() => setQuoteConvertCaseId(null)}
            onConverted={(result) => void onQuoteConverted(result)}
          />
        ) : null}
        {renderMainContent()}
      </main>
      </div>
    </div>
  )
}


export default App
