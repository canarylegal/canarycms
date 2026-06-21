/** Per-user UI layout preferences synced with the server. */

export type CalendarView = 'dayGridMonth' | 'timeGridWeek' | 'timeGridDay' | 'listYear'
export type TaskLayout = 'list' | 'kanban'
export type TaskSortKey = 'reference' | 'client' | 'matter' | 'task' | 'date' | 'assigned' | 'priority'
export type MainMenuSortKey = 'reference' | 'client' | 'matter' | 'feeEarner' | 'status' | 'source' | 'created'
export type ContactsSortKey = 'name' | 'type' | 'email' | 'phone'
export type CaseStatusFilter = '' | 'open' | 'closed' | 'archived' | 'quote' | 'quote_closed' | 'post_completion'
export type MainMenuCaseStatusFilter = Exclude<CaseStatusFilter, ''>
export type SortDir = 'asc' | 'desc'

export const MAIN_MENU_COLUMN_WIDTHS_DEFAULT = [110, 165, 300, 130, 225] as const
export const TASKS_MENU_COLUMN_WIDTHS_DEFAULT = [90, 66, 90, 210, 300, 183, 73] as const
export const CONTACTS_COLUMN_WIDTHS_DEFAULT = [270, 210, 210, 210] as const

export const MAIN_MENU_COLUMN_COUNT = MAIN_MENU_COLUMN_WIDTHS_DEFAULT.length
export const TASKS_MENU_COLUMN_COUNT = TASKS_MENU_COLUMN_WIDTHS_DEFAULT.length
export const CONTACTS_COLUMN_COUNT = CONTACTS_COLUMN_WIDTHS_DEFAULT.length

export type UserUiPreferences = {
  calendar_view: CalendarView
  case_calendar_view: CalendarView
  tasks_menu_layout: TaskLayout
  case_tasks_layout: TaskLayout
  tasks_menu_sort_key: TaskSortKey
  tasks_menu_sort_dir: SortDir
  case_tasks_sort_key: TaskSortKey
  case_tasks_sort_dir: SortDir
  main_menu_sort_key: MainMenuSortKey
  main_menu_sort_dir: SortDir
  main_menu_search: string
  main_menu_filter_matter_type: string
  main_menu_filter_fee_earner_user_id: string
  main_menu_filter_case_status: CaseStatusFilter
  main_menu_filter_matter_types: string[]
  main_menu_filter_fee_earner_user_ids: string[]
  main_menu_filter_case_statuses: MainMenuCaseStatusFilter[]
  tasks_menu_search: string
  tasks_menu_filter_matter_type: string
  contacts_search: string
  contacts_sort_key: ContactsSortKey
  contacts_sort_dir: SortDir
  calendar_selected_calendar_ids: string[]
  main_menu_column_widths: number[]
  tasks_menu_column_widths: number[]
  contacts_column_widths: number[]
}

export const DEFAULT_UI_PREFERENCES: UserUiPreferences = {
  calendar_view: 'dayGridMonth',
  case_calendar_view: 'dayGridMonth',
  tasks_menu_layout: 'list',
  case_tasks_layout: 'list',
  tasks_menu_sort_key: 'priority',
  tasks_menu_sort_dir: 'asc',
  case_tasks_sort_key: 'priority',
  case_tasks_sort_dir: 'asc',
  main_menu_sort_key: 'created',
  main_menu_sort_dir: 'desc',
  main_menu_search: '',
  main_menu_filter_matter_type: '',
  main_menu_filter_fee_earner_user_id: '',
  main_menu_filter_case_status: '',
  main_menu_filter_matter_types: [],
  main_menu_filter_fee_earner_user_ids: [],
  main_menu_filter_case_statuses: [],
  tasks_menu_search: '',
  tasks_menu_filter_matter_type: '',
  contacts_search: '',
  contacts_sort_key: 'name',
  contacts_sort_dir: 'asc',
  calendar_selected_calendar_ids: [],
  main_menu_column_widths: [],
  tasks_menu_column_widths: [],
  contacts_column_widths: [],
}

const CACHE_KEY = 'canary.uiPreferences.v2'

/** Dispatched after menu column widths are reset so all tables revert immediately. */
export const MENU_COLUMN_RESET_EVENT = 'canary-menu-columns-reset'

export function notifyMenuColumnReset(): void {
  window.dispatchEvent(new Event(MENU_COLUMN_RESET_EVENT))
}
export const LEGACY_TASKS_MENU_LAYOUT_KEY = 'canary.tasks.menuLayout'
const SEARCH_MAX = 500

const CALENDAR_VIEWS = new Set<CalendarView>(['dayGridMonth', 'timeGridWeek', 'timeGridDay', 'listYear'])

function pickCalendarView(raw: unknown, fallback: CalendarView): CalendarView {
  if (typeof raw === 'string' && raw === 'listWeek') return 'listYear'
  return pick(raw, CALENDAR_VIEWS, fallback)
}
const TASK_LAYOUTS = new Set<TaskLayout>(['list', 'kanban'])
const TASK_SORT_KEYS = new Set<TaskSortKey>([
  'reference',
  'client',
  'matter',
  'task',
  'date',
  'assigned',
  'priority',
])
const MAIN_MENU_SORT_KEYS = new Set<MainMenuSortKey>([
  'reference',
  'client',
  'matter',
  'feeEarner',
  'status',
  'source',
  'created',
])
const CONTACTS_SORT_KEYS = new Set<ContactsSortKey>(['name', 'type', 'email', 'phone'])
const CASE_STATUS_FILTERS = new Set<CaseStatusFilter>([
  '',
  'open',
  'closed',
  'archived',
  'quote',
  'quote_closed',
  'post_completion',
])
const SORT_DIRS = new Set<SortDir>(['asc', 'desc'])
const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

function pick<T extends string>(raw: unknown, allowed: Set<T>, fallback: T): T {
  return typeof raw === 'string' && allowed.has(raw as T) ? (raw as T) : fallback
}

function pickSearch(raw: unknown): string {
  return typeof raw === 'string' ? raw.trim().slice(0, SEARCH_MAX) : ''
}

function pickFilterText(raw: unknown): string {
  return typeof raw === 'string' ? raw.trim().slice(0, 200) : ''
}

function pickFeeEarnerId(raw: unknown): string {
  if (typeof raw !== 'string') return ''
  const s = raw.trim()
  return UUID_RE.test(s) ? s : ''
}

function pickFilterTextList(raw: unknown): string[] {
  if (!Array.isArray(raw)) return []
  const out: string[] = []
  for (const item of raw) {
    const s = pickFilterText(item)
    if (s && !out.includes(s)) out.push(s)
  }
  return out
}

function pickFeeEarnerIdList(raw: unknown): string[] {
  if (!Array.isArray(raw)) return []
  const out: string[] = []
  for (const item of raw) {
    const s = pickFeeEarnerId(item)
    if (s && !out.includes(s)) out.push(s)
  }
  return out
}

function pickCaseStatusList(raw: unknown): MainMenuCaseStatusFilter[] {
  if (!Array.isArray(raw)) return []
  const out: MainMenuCaseStatusFilter[] = []
  for (const item of raw) {
    if (typeof item === 'string' && item !== '' && CASE_STATUS_FILTERS.has(item as CaseStatusFilter)) {
      const v = item as MainMenuCaseStatusFilter
      if (!out.includes(v)) out.push(v)
    }
  }
  return out
}

function legacyMainMenuMatterTypes(data: Record<string, unknown>): string[] {
  const fromList = pickFilterTextList(data.main_menu_filter_matter_types)
  if (fromList.length) return fromList
  const one = pickFilterText(data.main_menu_filter_matter_type)
  return one ? [one] : []
}

function legacyMainMenuFeeEarnerIds(data: Record<string, unknown>): string[] {
  const fromList = pickFeeEarnerIdList(data.main_menu_filter_fee_earner_user_ids)
  if (fromList.length) return fromList
  const one = pickFeeEarnerId(data.main_menu_filter_fee_earner_user_id)
  return one ? [one] : []
}

function legacyMainMenuCaseStatuses(data: Record<string, unknown>): MainMenuCaseStatusFilter[] {
  const fromList = pickCaseStatusList(data.main_menu_filter_case_statuses)
  if (fromList.length) return fromList
  const one = pick(
    data.main_menu_filter_case_status,
    CASE_STATUS_FILTERS,
    DEFAULT_UI_PREFERENCES.main_menu_filter_case_status,
  )
  return one ? [one as MainMenuCaseStatusFilter] : []
}

function normalizeIdList(raw: unknown): string[] {
  if (!Array.isArray(raw)) return []
  return raw.filter((x): x is string => typeof x === 'string' && x.trim().length > 0).map((x) => x.trim())
}

function normalizeWidths(raw: unknown, expected: number): number[] {
  if (!Array.isArray(raw) || raw.length !== expected) return []
  const out: number[] = []
  for (const item of raw) {
    if (typeof item !== 'number' || !Number.isFinite(item)) return []
    out.push(Math.max(48, Math.min(2000, Math.round(item))))
  }
  return out
}

export function normalizeUiPreferences(raw: unknown): UserUiPreferences {
  const data = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
  return {
    calendar_view: pickCalendarView(data.calendar_view, DEFAULT_UI_PREFERENCES.calendar_view),
    case_calendar_view: pickCalendarView(data.case_calendar_view, DEFAULT_UI_PREFERENCES.case_calendar_view),
    tasks_menu_layout: pick(data.tasks_menu_layout, TASK_LAYOUTS, DEFAULT_UI_PREFERENCES.tasks_menu_layout),
    case_tasks_layout: pick(data.case_tasks_layout, TASK_LAYOUTS, DEFAULT_UI_PREFERENCES.case_tasks_layout),
    tasks_menu_sort_key: pick(data.tasks_menu_sort_key, TASK_SORT_KEYS, DEFAULT_UI_PREFERENCES.tasks_menu_sort_key),
    tasks_menu_sort_dir: pick(data.tasks_menu_sort_dir, SORT_DIRS, DEFAULT_UI_PREFERENCES.tasks_menu_sort_dir),
    case_tasks_sort_key: pick(data.case_tasks_sort_key, TASK_SORT_KEYS, DEFAULT_UI_PREFERENCES.case_tasks_sort_key),
    case_tasks_sort_dir: pick(data.case_tasks_sort_dir, SORT_DIRS, DEFAULT_UI_PREFERENCES.case_tasks_sort_dir),
    main_menu_sort_key: pick(data.main_menu_sort_key, MAIN_MENU_SORT_KEYS, DEFAULT_UI_PREFERENCES.main_menu_sort_key),
    main_menu_sort_dir: pick(data.main_menu_sort_dir, SORT_DIRS, DEFAULT_UI_PREFERENCES.main_menu_sort_dir),
    main_menu_search: pickSearch(data.main_menu_search),
    main_menu_filter_matter_type: pickFilterText(data.main_menu_filter_matter_type),
    main_menu_filter_fee_earner_user_id: pickFeeEarnerId(data.main_menu_filter_fee_earner_user_id),
    main_menu_filter_case_status: pick(
      data.main_menu_filter_case_status,
      CASE_STATUS_FILTERS,
      DEFAULT_UI_PREFERENCES.main_menu_filter_case_status,
    ),
    main_menu_filter_matter_types: legacyMainMenuMatterTypes(data),
    main_menu_filter_fee_earner_user_ids: legacyMainMenuFeeEarnerIds(data),
    main_menu_filter_case_statuses: legacyMainMenuCaseStatuses(data),
    tasks_menu_search: pickSearch(data.tasks_menu_search),
    tasks_menu_filter_matter_type: pickFilterText(data.tasks_menu_filter_matter_type),
    contacts_search: pickSearch(data.contacts_search),
    contacts_sort_key: pick(data.contacts_sort_key, CONTACTS_SORT_KEYS, DEFAULT_UI_PREFERENCES.contacts_sort_key),
    contacts_sort_dir: pick(data.contacts_sort_dir, SORT_DIRS, DEFAULT_UI_PREFERENCES.contacts_sort_dir),
    calendar_selected_calendar_ids: normalizeIdList(data.calendar_selected_calendar_ids),
    main_menu_column_widths: normalizeWidths(
      data.main_menu_column_widths,
      MAIN_MENU_COLUMN_COUNT,
    ),
    tasks_menu_column_widths: normalizeWidths(
      data.tasks_menu_column_widths,
      TASKS_MENU_COLUMN_COUNT,
    ),
    contacts_column_widths: normalizeWidths(
      data.contacts_column_widths,
      CONTACTS_COLUMN_COUNT,
    ),
  }
}

export function uiPreferencesEqual(a: UserUiPreferences, b: UserUiPreferences): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

export function readCachedUiPreferences(): UserUiPreferences {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    if (raw) return normalizeUiPreferences(JSON.parse(raw))
  } catch {
    /* ignore */
  }
  return { ...DEFAULT_UI_PREFERENCES }
}

export function writeCachedUiPreferences(prefs: UserUiPreferences): void {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(prefs))
  } catch {
    /* ignore */
  }
}

export function legacyUiPreferenceOverrides(): Partial<UserUiPreferences> {
  const out: Partial<UserUiPreferences> = {}
  try {
    const legacyTasks = localStorage.getItem(LEGACY_TASKS_MENU_LAYOUT_KEY)
    if (legacyTasks === 'kanban') out.tasks_menu_layout = 'kanban'
  } catch {
    /* ignore */
  }
  return out
}

export async function persistUserUiPreferences(
  token: string,
  patch: Partial<UserUiPreferences>,
): Promise<UserUiPreferences> {
  const { apiFetch } = await import('./api')
  const user = await apiFetch<{ ui_preferences?: UserUiPreferences }>('/users/me/ui-preferences', {
    token,
    method: 'PUT',
    json: patch,
  })
  const prefs = normalizeUiPreferences(user.ui_preferences)
  writeCachedUiPreferences(prefs)
  return prefs
}

/** Clear saved column widths for all resizable menu tables (main menu, quotes, tasks, contacts). */
export async function resetMenuColumnWidths(token: string): Promise<UserUiPreferences> {
  const prefs = await persistUserUiPreferences(token, {
    main_menu_column_widths: [],
    tasks_menu_column_widths: [],
    contacts_column_widths: [],
  })
  notifyMenuColumnReset()
  return prefs
}
