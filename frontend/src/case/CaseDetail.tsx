import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { lockBodyWaitCursor, unlockBodyWaitCursor } from '../bodyCursorLock'
import { resolveContactNameWithFallback } from '../GlobalContactCreateForm'
import { MATTER_CONTACT_TYPE_OPTIONS_FALLBACK } from '../matterContactTypeOptions'
import { apiFetch } from '../api'
import { useDialogs } from '../DialogProvider'
import { useNotifications } from '../NotificationsProvider'
import {
  matterHeadDropdownOptions,
  matterHeadIdForSubType,
  matterSubDropdownOptions,
} from '../matterTypeOptions'
import { useExclusiveDropdownOpen } from '../useExclusiveDropdownOpen'
import { useQuoteAwaitingSave, type QuoteAwaitingSaveContext } from '../quoteAwaitingSave'
import { type PendingCaseCompose } from '../quoteEmailPrecedent'
import { type CaseWorkflowStatus } from '../types'
import type {
  CaseContactOut,
  CaseEventsOut,
  CaseNoteOut,
  CaseOut,
  CasePropertyDetailsOut,
  CasePropertyPayload,
  CaseSourceOut,
  CaseTaskOut,
  ContactOut,
  FileSummary,
  FinanceOut,
  LedgerOut,
  MatterContactTypeOut,
  MatterHeadTypeOut,
  TaskMenuRow,
  UserPublic,
  UserSummary,
  CasePortalFolderAccessGrantOut,
  CasePortalShareStatusOut,
} from '../types'
import { useUserUiPreferences } from '../useUserUiPreferences'
import { useColumnWidths } from '../useColumnWidths'
import { LEGACY_AUTO_TASKS_MENU_COLUMN_WIDTHS, effectiveColumnWidths } from '../columnGridDefaults'
import { TASKS_MENU_COLUMN_COUNT, TASKS_MENU_COLUMN_WIDTHS_DEFAULT } from '../userUiPreferences'
import { computeDocContextMenuStyle } from './docContextMenu'
import { matterContactTypeLabel } from './matterLabels'
import type { EmlPreviewData } from './emlPreview'
import { isClientMatterContact } from './caseDetailHelpers'
import { isCommentFile } from './caseDocFileOps'
import { linkPickedGlobalContactIfNeeded } from './caseContactPickOps'
import { useCaseDocFileHandlers } from './useCaseDocFileHandlers'
import { useCaseDocsFolderData } from './useCaseDocsFolderData'
import { useCaseDocsSelection } from './useCaseDocsSelection'
import { useCasePrecedentPicker } from './useCasePrecedentPicker'
import { CaseDetailDocuments } from './CaseDetailDocuments'
import { CaseDetailLeftNav } from './CaseDetailLeftNav'
import type { CaseDetailLeftDocPanel } from './CaseDetailLeftNav'
import { CaseDetailPanelHost } from './CaseDetailPanelHost'
import { CaseMatterHero } from './CaseMatterHero'
import { CaseDocsContextMenu } from './CaseDocsContextMenu'
import { CaseDetailOverlayModals } from './CaseDetailOverlayModals'

export type CaseOpenDocPanel = 'accounts'

export function CaseDetail({
  token,
  caseDetail,
  notes: _notes,
  tasks: _tasks,
  files,
  caseContacts,
  error,
  onRefresh,
  onCaseListInvalidate,
  onTaskMenuInvalidate,
  /** When set, case view waits until this matches ``caseDetail.id`` so we do not fetch the wrong matter while switching cases. */
  selectedCaseId,
  currentUser,
  openDocPanel,
  onOpenDocPanelConsumed,
  pendingComposeKind,
  onPendingComposeConsumed,
  onBackToMainMenu,
  backNavLabel = 'Back to main menu',
}: {
  token: string
  caseDetail: CaseOut | null
  notes: CaseNoteOut[]
  tasks: CaseTaskOut[]
  files: FileSummary[]
  caseContacts: CaseContactOut[]
  error: string | null
  onRefresh: () => void
  onCaseListInvalidate?: () => void
  onTaskMenuInvalidate?: () => void
  selectedCaseId?: string | null
  /** Used for e-mail launch preference when opening filed ``.eml`` files (Outlook web vs desktop). */
  currentUser?: UserPublic | null
  /** When set from the main menu, open this documents sub-panel once the matter has loaded. */
  openDocPanel?: CaseOpenDocPanel | null
  onOpenDocPanelConsumed?: () => void
  /** After quote wizard: open letter or e-mail precedent picker once the matter has loaded. */
  pendingComposeKind?: PendingCaseCompose | null
  onPendingComposeConsumed?: () => void
  /** Leave the matter and return to the cases or quotes list. */
  onBackToMainMenu?: () => void
  backNavLabel?: string
}) {
  void _notes
  void _tasks
  const { askConfirm } = useDialogs()
  const { push: pushNotification } = useNotifications()
  const caseId = caseDetail?.id
  const portalEnabled = Boolean(caseDetail?.portal_enabled)
  /** Resolved matter id for API calls: null while ``caseDetail`` is stale vs. ``selectedCaseId``. */
  const matterScopeId = useMemo(() => {
    if (!caseId) return null
    if (selectedCaseId === undefined || selectedCaseId === null) return caseId
    return String(selectedCaseId) === String(caseId) ? caseId : null
  }, [caseId, selectedCaseId])

  const [busy, setBusy] = useState(false)
  const [portalFolderGrants, setPortalFolderGrants] = useState<CasePortalFolderAccessGrantOut[]>([])
  const refreshPortalFolderGrants = useCallback(() => {
    if (!matterScopeId || !token || !portalEnabled) {
      setPortalFolderGrants([])
      return
    }
    void apiFetch<CasePortalFolderAccessGrantOut[]>(`/cases/${matterScopeId}/files/portal-folder-access`, { token })
      .then((rows) => setPortalFolderGrants(rows))
      .catch(() => setPortalFolderGrants([]))
  }, [matterScopeId, token, portalEnabled])
  useEffect(() => {
    refreshPortalFolderGrants()
  }, [refreshPortalFolderGrants, files])
  useEffect(() => {
    if (!token) {
      setDocusignEnabled(false)
      return
    }
    void apiFetch<{ enabled: boolean }>('/docusign/options', { token })
      .then((o) => setDocusignEnabled(Boolean(o.enabled)))
      .catch(() => setDocusignEnabled(false))
  }, [token])
  useEffect(() => {
    if (!token) {
      setCanarySignEnabled(false)
      return
    }
    void apiFetch<{ enabled: boolean }>('/canary-sign/options', { token })
      .then((o) => setCanarySignEnabled(Boolean(o.enabled)))
      .catch(() => setCanarySignEnabled(true))
  }, [token])
  useEffect(() => {
    if (!busy) return
    lockBodyWaitCursor()
    return () => unlockBodyWaitCursor()
  }, [busy])

  // File drag: prevent the browser from navigating / opening the file when dropping outside a valid target.
  useEffect(() => {
    function preventFileDropNavigate(e: DragEvent) {
      if (!e.dataTransfer || !Array.from(e.dataTransfer.types).includes('Files')) return
      e.preventDefault()
    }
    window.addEventListener('dragover', preventFileDropNavigate)
    window.addEventListener('drop', preventFileDropNavigate)
    return () => {
      window.removeEventListener('dragover', preventFileDropNavigate)
      window.removeEventListener('drop', preventFileDropNavigate)
    }
  }, [])

  const [actionErr, setActionErr] = useState<string | null>(null)
  const [textPrompt, setTextPrompt] = useState<
    | null
    | {
        title: string
        hint?: string
        initial: string
        confirmLabel: string
        onConfirm: (value: string) => void
      }
  >(null)
  const [editSnapshot, setEditSnapshot] = useState<CaseContactOut | null>(null)
  const [pushToGlobal, setPushToGlobal] = useState(false)

  const resolvedEditSnapshotName = useMemo(() => {
    if (!editSnapshot) return ''
    return resolveContactNameWithFallback(
      editSnapshot.type,
      {
        title: editSnapshot.title ?? '',
        first_name: editSnapshot.first_name ?? '',
        middle_name: editSnapshot.middle_name ?? '',
        last_name: editSnapshot.last_name ?? '',
      },
      {
        company_name: editSnapshot.company_name ?? '',
        trading_name: editSnapshot.trading_name ?? '',
      },
      editSnapshot.name,
    )
  }, [editSnapshot])

  /** Match precedent client 1,2,… order (created_at asc among clients); other types after, newest first. */
  const caseContactsMenuOrder = useMemo(() => {
    const clients = caseContacts.filter(isClientMatterContact).sort((a, b) => a.created_at.localeCompare(b.created_at))
    const others = caseContacts
      .filter((c) => !isClientMatterContact(c))
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
    return [...clients, ...others]
  }, [caseContacts])

  const lawyerLinkableMatterContacts = useMemo(() => {
    const excludeId = editSnapshot?.id
    return caseContacts
      .filter((c) => c.id !== excludeId)
      .sort((a, b) => a.created_at.localeCompare(b.created_at))
  }, [caseContacts, editSnapshot?.id])

  useEffect(() => {
    if (!editSnapshot) {
      setEditLawyerLinkClientIds([])
      return
    }
    setEditLawyerLinkClientIds((editSnapshot.lawyer_client_ids ?? []).map((x) => String(x)))
  }, [editSnapshot])

  const [docSearch, setDocSearch] = useState('')
  const [docFolder, setDocFolder] = useState<string>('') // "" == Home (top-level documents)
  const [docMenu, setDocMenu] = useState<
    | null
    | { kind: 'file'; fileId: string; x: number; y: number }
    | { kind: 'folder'; folderPath: string; x: number; y: number }
    | { kind: 'surface'; x: number; y: number }
  >(null)
  const [docSortKey, setDocSortKey] = useState<'description' | 'size' | 'created' | 'user'>('created')
  const [docSortDir, setDocSortDir] = useState<'asc' | 'desc'>('desc')
  const [moveMenu, setMoveMenu] = useState<{ kind: 'file'; fileId: string } | { kind: 'folder'; folderPath: string } | null>(null)
  const [portalMenu, setPortalMenu] = useState<{ folderPath: string } | null>(null)
  const docMenuRef = useRef<HTMLDivElement | null>(null)
  const [docMenuStyle, setDocMenuStyle] = useState<{ left: number; top: number; maxHeight?: number } | null>(null)
  const [quoteWizardOpen, setQuoteWizardOpen] = useState(false)
  const [formSendOpen, setFormSendOpen] = useState(false)
  const [quoteAwaitingSave, setQuoteAwaitingSave] = useState<QuoteAwaitingSaveContext | null>(null)
  const [quoteSendOpen, setQuoteSendOpen] = useState(false)
  const quoteWasCreatedRef = useRef(false)
  const closeQuoteWizard = useCallback(() => {
    setQuoteWizardOpen(false)
    if (quoteWasCreatedRef.current) {
      quoteWasCreatedRef.current = false
      onRefresh()
    }
  }, [onRefresh])

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
  const [taskCreateOpen, setTaskCreateOpen] = useState(false)
  const [taskCreatePreset, setTaskCreatePreset] = useState<{ standardTaskId?: string; title?: string } | null>(null)
  const [commentOpen, setCommentOpen] = useState(false)
  const [commentText, setCommentText] = useState('')
  const [commentBusy, setCommentBusy] = useState(false)
  const [commentErr, setCommentErr] = useState<string | null>(null)
  // When set, the comment modal is in edit mode for this file ID
  const [commentEditFileId, setCommentEditFileId] = useState<string | null>(null)
  const [emlPreviewOpen, setEmlPreviewOpen] = useState(false)
  const [emlPreviewFile, setEmlPreviewFile] = useState<FileSummary | null>(null)
  const [emlPreviewData, setEmlPreviewData] = useState<EmlPreviewData | null>(null)
  const [emlPreviewBusy, setEmlPreviewBusy] = useState(false)
  const [emlPreviewErr, setEmlPreviewErr] = useState<string | null>(null)
  const [users, setUsers] = useState<UserSummary[]>([])
  const [leftOpen, setLeftOpen] = useState<{
    contacts: boolean
    accounts: boolean
    tasks: boolean
    property: boolean
    events: boolean
    finance: boolean
  }>(() => ({
    contacts: false,
    accounts: openDocPanel === 'accounts',
    tasks: false,
    property: false,
    events: false,
    finance: false,
  }))

  type LeftAccordionKey = 'contacts' | 'accounts' | 'tasks' | 'property' | 'events' | 'finance'
  const toggleLeftAccordion = useCallback((key: LeftAccordionKey) => {
    setLeftOpen((prev) => {
      if (prev[key]) {
        return { ...prev, [key]: false }
      }
      return {
        contacts: key === 'contacts',
        accounts: key === 'accounts',
        tasks: key === 'tasks',
        property: key === 'property',
        events: key === 'events',
        finance: key === 'finance',
      }
    })
  }, [])

  const openTaskCreateModal = useCallback(() => {
    setTaskCreatePreset(null)
    setTaskCreateOpen(true)
  }, [])

  const [caseDocPanel, setCaseDocPanel] = useState<CaseDetailLeftDocPanel>(() =>
    openDocPanel === 'accounts' ? 'accounts' : 'documents',
  )
  const goToOverview = useCallback(() => {
    setLeftOpen({
      contacts: false,
      accounts: false,
      tasks: false,
      property: false,
      events: false,
      finance: false,
    })
    setCaseDocPanel('documents')
  }, [])
  const [accountsSubTab, setAccountsSubTab] = useState<'ledger' | 'time'>('ledger')
  const [portalShareFolderPath, setPortalShareFolderPath] = useState<string | null>(null)
  const [portalQuoteSend, setPortalQuoteSend] = useState<{ fileId: string; fileName: string; folderPath: string } | null>(
    null,
  )
  const [docusignEnabled, setDocusignEnabled] = useState(false)
  const [docusignSend, setDocusignSend] = useState<{
    fileId: string
    fileName: string
    amendFromId?: string | null
  } | null>(null)
  const [canarySignEnabled, setCanarySignEnabled] = useState(true)
  const [canarySignSend, setCanarySignSend] = useState<{
    fileId: string
    fileName: string
    amendFromId?: string | null
  } | null>(null)
  const [caseTaskMenuRows, setCaseTaskMenuRows] = useState<TaskMenuRow[]>([])
  const [caseTasksSearch, setCaseTasksSearch] = useState('')
  const [caseTasksLayoutOpen, setCaseTasksLayoutOpen] = useState(false)
  const { prefs: uiPrefs, setPreference: setUiPreference, setPreferenceDebounced: setUiPreferenceDebounced } =
    useUserUiPreferences(currentUser, token)
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
  const [eventsPreview, setEventsPreview] = useState<CaseEventsOut | null>(null)
  const [caseEventModalOpen, setCaseEventModalOpen] = useState(false)
  const openCaseEventModal = useCallback(() => setCaseEventModalOpen(true), [])
  const [accountsPreview, setAccountsPreview] = useState<LedgerOut | null>(null)
  const [accountsPreviewErr, setAccountsPreviewErr] = useState<string | null>(null)
  const [financePreview, setFinancePreview] = useState<FinanceOut | null>(null)
  const [propertyDetails, setPropertyDetails] = useState<CasePropertyDetailsOut | null>(null)
  const [propertyLoading, setPropertyLoading] = useState(false)
  const [propertyDraft, setPropertyDraft] = useState<CasePropertyPayload | null>(null)
  const [propertyBaseline, setPropertyBaseline] = useState<CasePropertyPayload | null>(null)
  const [matterHeadTypes, setMatterHeadTypes] = useState<MatterHeadTypeOut[]>([])
  const {
    precedentPicker,
    setPrecedentPicker,
    precedentPickerSubTypeGroups,
    precedentPickerExpandedSubTypes,
    precedentCategoriesBySubType,
    togglePrecedentPickerSubTypeExpanded,
    selectPrecedentPickerNav,
    precedentPickerSubTypeId,
    precedentPickerCategoryId,
    precedentSearch,
    setPrecedentSearch,
    precedentChosenId,
    setPrecedentChosenId,
    filteredPrecedentChoices,
  } = useCasePrecedentPicker({ token, caseDetail, matterHeadTypes })
  const [contactPickModal, setContactPickModal] = useState<
    null | { precedentId: string | null; composeKind: 'letter' | 'email'; attachmentFileIds?: string[] }
  >(null)
  const [pickMatterCcId, setPickMatterCcId] = useState<string>('none') // 'none' | 'all_clients' | case contact id
  const [pickSelectedContact, setPickSelectedContact] = useState<ContactOut | null>(null)
  const [pickLinkGlobal, setPickLinkGlobal] = useState(false)
  const [pickLinkType, setPickLinkType] = useState('')
  const [pickLawyerClientIds, setPickLawyerClientIds] = useState<string[]>([])
  const [contactPickErr, setContactPickErr] = useState<string | null>(null)
  const [contactPickMatterOpen, setContactPickMatterOpen] = useState(false)
  const [contactPickTypeOpen, setContactPickTypeOpen] = useState(false)
  const [manageAccessOpen, setManageAccessOpen] = useState(false)
  const [editMatterDescription, setEditMatterDescription] = useState('')
  const [editMatterHeadTypeId, setEditMatterHeadTypeId] = useState('')
  const [editPracticeArea, setEditPracticeArea] = useState('')
  const [editFeeEarner, setEditFeeEarner] = useState<string>('')
  const [editCaseStatus, setEditCaseStatus] = useState<CaseWorkflowStatus>('open')
  const [editSourceId, setEditSourceId] = useState('')
  const [editPortalEnabled, setEditPortalEnabled] = useState(false)
  const editCaseDropdown = useExclusiveDropdownOpen<'head' | 'sub' | 'feeEarner' | 'status' | 'source'>()
  const [caseSources, setCaseSources] = useState<CaseSourceOut[]>([])
  /** Edit-case save/API errors only (shown inside the edit card, never in the case shell). */
  const [editCaseErr, setEditCaseErr] = useState<string | null>(null)

  const [contactAddOpen, setContactAddOpen] = useState(false)
  const [selectedGlobalContactId, setSelectedGlobalContactId] = useState<string | null>(null)
  const [contactAddErr, setContactAddErr] = useState<string | null>(null)
  const [matterContactType, setMatterContactType] = useState('')
  const [matterContactReference, setMatterContactReference] = useState('')
  const [matterTypeOptions, setMatterTypeOptions] = useState<{ value: string; label: string }[]>(
    MATTER_CONTACT_TYPE_OPTIONS_FALLBACK,
  )

  const contactPickMatterOptions = useMemo(
    () => [
      { value: 'none', label: 'None' },
      { value: 'all_clients', label: 'All clients' },
      ...caseContactsMenuOrder.map((cc) => ({
        value: cc.id,
        label: cc.name,
        hint: matterContactTypeLabel(cc.matter_contact_type, matterTypeOptions),
      })),
    ],
    [caseContactsMenuOrder, matterTypeOptions],
  )

  const contactPickTypeOptions = useMemo(
    () => matterTypeOptions.map((o) => ({ value: o.value, label: o.label })),
    [matterTypeOptions],
  )

  const [lawyerLinkClientIds, setLawyerLinkClientIds] = useState<string[]>([])
  const [editLawyerLinkClientIds, setEditLawyerLinkClientIds] = useState<string[]>([])
  const [contactRowMenu, setContactRowMenu] = useState<null | { cc: CaseContactOut; x: number; y: number }>(null)
  const contactRowMenuRef = useRef<HTMLDivElement | null>(null)

  const backToDocuments = useCallback(() => {
    if (caseDocPanel === 'edit-details') setEditCaseErr(null)
    if (caseDocPanel === 'property' && propertyBaseline) {
      setPropertyDraft(JSON.parse(JSON.stringify(propertyBaseline)) as CasePropertyPayload)
    }
    setCaseDocPanel('documents')
    setContactAddOpen(false)
    setEditSnapshot(null)
    setPortalShareFolderPath(null)
  }, [caseDocPanel, propertyBaseline])

  useEffect(() => {
    if (portalEnabled) return
    if (caseDocPanel === 'portal-hub' || caseDocPanel === 'portal-share') {
      setCaseDocPanel('documents')
      setPortalShareFolderPath(null)
    }
  }, [portalEnabled, caseDocPanel])

  const openPortalSharePanel = useCallback((folderPath: string) => {
    if (!portalEnabled) return
    setPortalShareFolderPath(folderPath)
    setCaseDocPanel('portal-share')
    setDocMenu(null)
    setPortalMenu(null)
  }, [portalEnabled])

  async function onEditPortalEnabledChange(checked: boolean) {
    if (checked) {
      setEditPortalEnabled(true)
      return
    }
    if (!caseDetail?.portal_enabled) {
      setEditPortalEnabled(false)
      return
    }
    if (!caseId) return
    let grantCount = portalFolderGrants.length
    let contactCount = new Set(portalFolderGrants.map((g) => g.contact_id)).size
    if (grantCount === 0) {
      try {
        const status = await apiFetch<CasePortalShareStatusOut>(`/cases/${caseId}/portal/share-status`, { token })
        grantCount = status.active_grant_count
        contactCount = status.contact_count
      } catch {
        /* proceed with zero counts */
      }
    }
    if (grantCount > 0) {
      const shareNoun = grantCount === 1 ? '1 active folder share' : `${grantCount} active folder shares`
      const contactNoun = contactCount === 1 ? '1 contact' : `${contactCount} contacts`
      const ok = await askConfirm({
        title: 'Disable portal for this matter?',
        message: [
          `This matter has ${shareNoun} for ${contactNoun}.`,
          '',
          'Clients will immediately lose access to shared documents through the portal.',
          'Folder sharing settings are kept but inactive until portal is re-enabled.',
          '',
          'Disable portal for this matter?',
        ].join('\n'),
        danger: true,
        confirmLabel: 'Disable portal',
        cancelLabel: 'Keep portal enabled',
      })
      if (!ok) return
    }
    setEditPortalEnabled(false)
  }

  const finishContactsDoc = useCallback(() => {
    setContactAddOpen(false)
    setEditSnapshot(null)
    setCaseDocPanel('documents')
    onRefresh()
  }, [onRefresh])

  useEffect(() => {
    if (caseDocPanel !== 'tasks' || !caseId) return
    let cancelled = false
    void apiFetch<TaskMenuRow[]>(`/tasks?case_id=${encodeURIComponent(caseId)}`, { token })
      .then((data) => {
        if (!cancelled) setCaseTaskMenuRows(Array.isArray(data) ? data : [])
      })
      .catch(() => {
        if (!cancelled) setCaseTaskMenuRows([])
      })
    return () => {
      cancelled = true
    }
  }, [caseDocPanel, caseId, token])

  const syncedMatterIdRef = useRef<string | null>(null)
  useLayoutEffect(() => {
    if (!caseId || selectedCaseId == null || String(caseId) !== String(selectedCaseId)) return

    if (openDocPanel === 'accounts') {
      setLeftOpen({
        contacts: false,
        accounts: true,
        tasks: false,
        property: false,
        events: false,
        finance: false,
      })
      setCaseDocPanel('accounts')
      syncedMatterIdRef.current = caseId
      onOpenDocPanelConsumed?.()
      return
    }

    if (syncedMatterIdRef.current === caseId) return
    syncedMatterIdRef.current = caseId
    setCaseDocPanel('documents')
  }, [caseId, selectedCaseId, openDocPanel, onOpenDocPanelConsumed])

  useEffect(() => {
    if (!pendingComposeKind || !matterScopeId) return
    setCaseDocPanel('documents')
    setPrecedentPicker({
      kind: pendingComposeKind.kind,
      preferPrecedentReference: pendingComposeKind.preferPrecedentReference,
      attachmentFileId: pendingComposeKind.attachmentFileId,
    })
    onPendingComposeConsumed?.()
  }, [pendingComposeKind, matterScopeId, onPendingComposeConsumed])

  useEffect(() => {
    if (!contactRowMenu) return
    function onDown(e: MouseEvent) {
      const t = e.target as Node
      if (contactRowMenuRef.current?.contains(t)) return
      setContactRowMenu(null)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [contactRowMenu])

  useEffect(() => {
    let cancelled = false
    async function loadUsers() {
      try {
        const data = await apiFetch<UserSummary[]>('/users', { token })
        if (!cancelled) setUsers(Array.isArray(data) ? data : [])
      } catch {
        // ignore
      }
    }
    void loadUsers()
    return () => {
      cancelled = true
    }
  }, [token])

  useEffect(() => {
    let cancelled = false
    async function loadMatterTypes() {
      try {
        const data = await apiFetch<MatterHeadTypeOut[]>('/matter-types', { token })
        if (!cancelled) setMatterHeadTypes(data)
      } catch {
        // ignore
      }
    }
    void loadMatterTypes()
    return () => {
      cancelled = true
    }
  }, [token])

  useEffect(() => {
    let cancelled = false
    async function loadMatterContactTypes() {
      try {
        const data = await apiFetch<MatterContactTypeOut[]>('/matter-contact-types', { token })
        if (!cancelled) {
          setMatterTypeOptions(data.map((r) => ({ value: r.slug, label: r.label })))
        }
      } catch {
        if (!cancelled) setMatterTypeOptions(MATTER_CONTACT_TYPE_OPTIONS_FALLBACK)
      }
    }
    void loadMatterContactTypes()
    return () => {
      cancelled = true
    }
  }, [token])

  const editMatterHeadOptions = useMemo(() => matterHeadDropdownOptions(matterHeadTypes), [matterHeadTypes])
  const editMatterSubOptions = useMemo(
    () => matterSubDropdownOptions(matterHeadTypes, editMatterHeadTypeId),
    [matterHeadTypes, editMatterHeadTypeId],
  )
  const editFeeEarnerOptions = useMemo(
    () =>
      users
        .filter(
          (u) =>
            u.is_active &&
            (u.can_be_fee_earner !== false || u.id === caseDetail?.fee_earner_user_id),
        )
        .map((u) => ({ value: u.id, label: `${u.display_name} (${u.email})` })),
    [users, caseDetail?.fee_earner_user_id],
  )
  const editStatusOptions = useMemo(() => {
    const opts: { value: CaseWorkflowStatus; label: string }[] = [
      { value: 'open', label: 'Active' },
      ...(caseDetail?.status === 'quote' ? [{ value: 'quote' as const, label: 'Quote' }] : []),
      ...(caseDetail?.status === 'quote_closed' ? [{ value: 'quote_closed' as const, label: 'Closed' }] : []),
      { value: 'post_completion', label: 'Post-completion' },
      { value: 'closed', label: 'Closed' },
      { value: 'archived', label: 'Archived' },
    ]
    return opts
  }, [caseDetail?.status])
  const editSourceOptions = useMemo(
    () => [
      { value: '', label: '— none —' },
      ...caseSources.map((s) => ({ value: s.id, label: s.name })),
    ],
    [caseSources],
  )

  const hasPropertyMenu = useMemo(
    () => Boolean(caseDetail?.matter_menus?.some((m) => m.name.trim().toLowerCase() === 'property')),
    [caseDetail?.matter_menus],
  )

  const hasFinanceMenu = useMemo(
    () => Boolean(caseDetail?.matter_menus?.some((m) => m.name.trim().toLowerCase() === 'finance')),
    [caseDetail?.matter_menus],
  )

  const hasEventsMenu = useMemo(
    () =>
      Boolean(
        caseDetail?.matter_menus?.some((m) => {
          const n = m.name.trim().toLowerCase()
          return n === 'events' || n === 'calendar'
        }),
      ),
    [caseDetail?.matter_menus],
  )

  const hasTasksMenu = useMemo(
    () => Boolean(caseDetail?.matter_menus?.some((m) => m.name.trim().toLowerCase() === 'tasks')),
    [caseDetail?.matter_menus],
  )

  const [sidebarTaskRows, setSidebarTaskRows] = useState<TaskMenuRow[]>([])
  useEffect(() => {
    if (!caseId || !leftOpen.tasks || !hasTasksMenu) return
    let cancelled = false
    void apiFetch<TaskMenuRow[]>(`/tasks?case_id=${encodeURIComponent(caseId)}`, { token })
      .then((data) => {
        if (!cancelled) setSidebarTaskRows(Array.isArray(data) ? data : [])
      })
      .catch(() => {
        if (!cancelled) setSidebarTaskRows([])
      })
    return () => {
      cancelled = true
    }
  }, [caseId, leftOpen.tasks, hasTasksMenu, token])

  useEffect(() => {
    if (!caseId || !hasPropertyMenu || !leftOpen.property) return
    let cancelled = false
    async function load() {
      setPropertyLoading(true)
      try {
        const d = await apiFetch<CasePropertyDetailsOut>(`/cases/${caseId}/property-details`, { token })
        if (!cancelled) setPropertyDetails(d)
      } catch {
        if (!cancelled) setPropertyDetails(null)
      } finally {
        if (!cancelled) setPropertyLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [caseId, token, hasPropertyMenu, leftOpen.property])

  useEffect(() => {
    if (!caseId || !leftOpen.events) return
    let cancelled = false
    void apiFetch<CaseEventsOut>(`/cases/${caseId}/events`, { token })
      .then((d) => {
        if (!cancelled) setEventsPreview(d)
      })
      .catch(() => {
        if (!cancelled) setEventsPreview(null)
      })
    return () => {
      cancelled = true
    }
  }, [caseId, token, leftOpen.events])

  useEffect(() => {
    if (!caseId || !leftOpen.finance) return
    let cancelled = false
    void apiFetch<FinanceOut>(`/cases/${caseId}/finance`, { token })
      .then((d) => {
        if (!cancelled) setFinancePreview(d)
      })
      .catch(() => {
        if (!cancelled) setFinancePreview(null)
      })
    return () => {
      cancelled = true
    }
  }, [caseId, token, leftOpen.finance])

  useEffect(() => {
    if (!caseId || !leftOpen.accounts) {
      setAccountsPreview(null)
      setAccountsPreviewErr(null)
      return
    }
    let cancelled = false
    setAccountsPreview(null)
    setAccountsPreviewErr(null)
    void apiFetch<LedgerOut>(`/cases/${caseId}/ledger`, { token })
      .then((d) => {
        if (!cancelled) {
          setAccountsPreview(d)
          setAccountsPreviewErr(null)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setAccountsPreview(null)
          setAccountsPreviewErr('Could not load balances.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [caseId, token, leftOpen.accounts])

  useEffect(() => {
    if (caseDocPanel !== 'edit-details') return
    editCaseDropdown.closeAll()
    setEditMatterDescription(caseDetail?.matter_description ?? '')
    const subId = caseDetail?.matter_sub_type_id ?? ''
    setEditPracticeArea(subId)
    setEditMatterHeadTypeId(
      caseDetail?.matter_head_type_id ?? matterHeadIdForSubType(matterHeadTypes, subId),
    )
    setEditFeeEarner(caseDetail?.fee_earner_user_id ? String(caseDetail.fee_earner_user_id) : '')
    setEditCaseStatus(caseDetail?.status ?? 'open')
    setEditSourceId(caseDetail?.source_id ?? '')
    setEditPortalEnabled(Boolean(caseDetail?.portal_enabled))
  }, [caseDocPanel, caseDetail, matterHeadTypes, editCaseDropdown.closeAll])

  useEffect(() => {
    if (caseDocPanel !== 'edit-details' || !token) return
    void apiFetch<CaseSourceOut[]>('/case-sources', { token })
      .then(setCaseSources)
      .catch(() => setCaseSources([]))
  }, [caseDocPanel, token])

  useLayoutEffect(() => {
    if (!docMenu) {
      setDocMenuStyle(null)
      return
    }
    function reposition() {
      const m = docMenu
      const el = docMenuRef.current
      if (!m || !el) return
      setDocMenuStyle(computeDocContextMenuStyle(el, m.x, m.y))
    }
    reposition()
    window.addEventListener('resize', reposition)
    return () => window.removeEventListener('resize', reposition)
  }, [docMenu])

  useEffect(() => {
    if (!docMenu) return
    function onDocMouseDown() {
      setDocMenu(null)
      setMoveMenu(null)
      setPortalMenu(null)
    }
    window.addEventListener('mousedown', onDocMouseDown)
    return () => window.removeEventListener('mousedown', onDocMouseDown)
  }, [docMenu])

  const {
    childFolders,
    allFolderPaths,
    sortedChildFolders,
    sortedPinnedInFolder,
    sortedRegularInFolder,
    breadcrumbParts,
    allDocKeys,
  } = useCaseDocsFolderData({
    files,
    docSearch,
    docFolder,
    docSortKey,
    docSortDir,
  })

  const {
    previewEmlFileRef,
    openCaseFileRef,
    uploadFilesToCurrentFolder,
    createFolderAtCurrentPath,
    composeOfficeFile,
    composeEmailMailto,
    previewEmlFile,
    openCaseFile,
    downloadCaseFiles,
    downloadCaseExportZip,
    downloadCaseFolderZip,
  } = useCaseDocFileHandlers({
    caseId,
    caseDetail,
    token,
    docFolder,
    files,
    portalEnabled,
    portalFolderGrants,
    currentUser,
    askConfirm,
    pushNotification,
    onRefresh,
    setBusy,
    setActionErr,
    setTextPrompt,
    setCommentText,
    setCommentEditFileId,
    setCommentErr,
    setCommentOpen,
    setEmlPreviewOpen,
    setEmlPreviewFile,
    setEmlPreviewData,
    setEmlPreviewErr,
    setEmlPreviewBusy,
    setDocMenu,
  })

  const {
    selectedDocSet,
    setSelectedDocSet,
    docFocusKey,
    handleDocsKeyDown,
    handleDocItemClick,
  } = useCaseDocsSelection({
    allDocKeys,
    caseDocPanel,
    docMenu,
    commentOpen,
    precedentPicker,
    contactPickModal,
    files,
    setDocFolder,
    previewEmlFile: (f) => previewEmlFileRef.current(f),
    openCaseFile: (f) => openCaseFileRef.current(f),
  })

  function resetContactPickForm() {
    setPickMatterCcId('none')
    setPickSelectedContact(null)
    setPickLinkGlobal(false)
    setPickLinkType('')
    setPickLawyerClientIds([])
    setContactPickErr(null)
    setContactPickMatterOpen(false)
    setContactPickTypeOpen(false)
  }

  function confirmPrecedentPicker() {
    if (!precedentPicker) return
    const pid = precedentChosenId
    const attachmentFileIds = precedentPicker.attachmentFileId ? [precedentPicker.attachmentFileId] : []
    if (precedentPicker.kind === 'document') {
      setPrecedentPicker(null)
      void composeOfficeFile(`Document — ${new Date().toISOString().slice(0, 10)}.docx`, pid, undefined, undefined, undefined, 'document')
      return
    }
    if (precedentPicker.kind === 'letter') {
      setPrecedentPicker(null)
      resetContactPickForm()
      setContactPickModal({ precedentId: pid, composeKind: 'letter' })
      return
    }
    if (precedentPicker.kind === 'email') {
      setPrecedentPicker(null)
      resetContactPickForm()
      setContactPickModal({ precedentId: pid, composeKind: 'email', attachmentFileIds })
      return
    }
  }

  async function confirmContactPick() {
    if (!contactPickModal || !caseId) return
    setBusy(true)
    setActionErr(null)
    setContactPickErr(null)
    try {
      const linkErr = await linkPickedGlobalContactIfNeeded({
        caseId,
        token,
        pickSelectedContact,
        pickLinkGlobal,
        pickLinkType,
        pickLawyerClientIds,
        onRefresh,
      })
      if (linkErr) {
        setContactPickErr(linkErr)
        return
      }

      let label = 'Letter'
      let caseContactIdForMerge: string | null = null
      let globalContactIdForMerge: string | null = null
      let mergeAllClients = false
      if (pickMatterCcId === 'all_clients') {
        label = 'All clients'
        mergeAllClients = true
      } else if (pickMatterCcId && pickMatterCcId !== 'none') {
        label = caseContacts.find((c) => c.id === pickMatterCcId)?.name ?? 'Letter'
        caseContactIdForMerge = pickMatterCcId
      } else if (pickSelectedContact) {
        label = pickSelectedContact.name ?? 'Letter'
        globalContactIdForMerge = pickSelectedContact.id
      }

      const composeKind = contactPickModal.composeKind ?? 'letter'
      if (composeKind === 'email') {
        await composeEmailMailto(
          contactPickModal.precedentId,
          caseContactIdForMerge,
          globalContactIdForMerge,
          mergeAllClients,
          null,
          contactPickModal.attachmentFileIds ?? [],
        )
        setContactPickModal(null)
        resetContactPickForm()
        return
      }

      const fn = `Letter — ${label.replace(/[/\\]/g, '_').slice(0, 120)}.docx`
      await composeOfficeFile(
        fn,
        contactPickModal.precedentId,
        caseContactIdForMerge,
        globalContactIdForMerge,
        mergeAllClients,
        'letter',
      )
      setContactPickModal(null)
      resetContactPickForm()
    } catch (e: any) {
      setActionErr(e?.message ?? 'Failed')
    } finally {
      setBusy(false)
    }
  }

  if (!caseId || !matterScopeId) return error ? <div className="error">{error}</div> : null

  return (
    <div className="caseShell">
      {error ? <div className="error">{error}</div> : null}
      {caseDocPanel !== 'edit-details' && actionErr ? <div className="error">{actionErr}</div> : null}
      <div
        className="caseGrid"
        onDragOver={(e) => {
          e.preventDefault()
          e.stopPropagation()
        }}
        onDrop={(e) => {
          e.preventDefault()
          e.stopPropagation()
        }}
      >
        <div className="caseLeft caseLeft--rail">
          <CaseMatterHero
            caseDetail={caseDetail}
            users={users}
            busy={busy}
            backNavLabel={backNavLabel}
            onBackToMainMenu={onBackToMainMenu}
            onEditMatterDetails={() => {
              setActionErr(null)
              setEditCaseErr(null)
              setCaseDocPanel('edit-details')
            }}
          />

          <CaseDetailLeftNav
            busy={busy}
            caseDocPanel={caseDocPanel}
            leftOpen={leftOpen}
            toggleLeftAccordion={toggleLeftAccordion}
            goToOverview={goToOverview}
            setCaseDocPanel={setCaseDocPanel}
            caseContacts={caseContacts}
            caseContactsMenuOrder={caseContactsMenuOrder}
            matterTypeOptions={matterTypeOptions}
            contactRowMenu={contactRowMenu}
            setContactRowMenu={setContactRowMenu}
            contactRowMenuRef={contactRowMenuRef}
            setContactAddOpen={setContactAddOpen}
            setEditSnapshot={setEditSnapshot}
            setPushToGlobal={setPushToGlobal}
            setMatterContactType={setMatterContactType}
            setMatterContactReference={setMatterContactReference}
            setLawyerLinkClientIds={setLawyerLinkClientIds}
            setContactAddErr={setContactAddErr}
            setSelectedGlobalContactId={setSelectedGlobalContactId}
            accountsPreview={accountsPreview}
            accountsPreviewErr={accountsPreviewErr}
            hasTasksMenu={hasTasksMenu}
            sidebarTaskRows={sidebarTaskRows}
            hasPropertyMenu={hasPropertyMenu}
            propertyLoading={propertyLoading}
            propertyDetails={propertyDetails}
            setPropertyDraft={setPropertyDraft}
            setPropertyBaseline={setPropertyBaseline}
            hasEventsMenu={hasEventsMenu}
            eventsPreview={eventsPreview}
            openCaseEventModal={openCaseEventModal}
            hasFinanceMenu={hasFinanceMenu}
            financePreview={financePreview}
          />

        </div>

        <div className="caseRight">
          {caseDocPanel === 'documents' ? (
            <CaseDetailDocuments
              busy={busy}
              portalEnabled={portalEnabled}
              caseDetail={caseDetail}
              createFolderAtCurrentPath={createFolderAtCurrentPath}
              openTaskCreateModal={openTaskCreateModal}
              openCaseEventModal={openCaseEventModal}
              setQuoteWizardOpen={setQuoteWizardOpen}
              setFormSendOpen={setFormSendOpen}
              setPrecedentPicker={setPrecedentPicker}
              setCommentText={setCommentText}
              setCommentErr={setCommentErr}
              setCommentOpen={setCommentOpen}
              downloadCaseExportZip={downloadCaseExportZip}
              setCaseDocPanel={setCaseDocPanel}
              onRefresh={onRefresh}
              docSearch={docSearch}
              setDocSearch={setDocSearch}
              docSortKey={docSortKey}
              setDocSortKey={setDocSortKey}
              docSortDir={docSortDir}
              setDocSortDir={setDocSortDir}
              breadcrumbParts={breadcrumbParts}
              setDocFolder={setDocFolder}
              sortedPinnedInFolder={sortedPinnedInFolder}
              sortedChildFolders={sortedChildFolders}
              sortedRegularInFolder={sortedRegularInFolder}
              childFolders={childFolders}
              docFolder={docFolder}
              selectedDocSet={selectedDocSet}
              setSelectedDocSet={setSelectedDocSet}
              docFocusKey={docFocusKey}
              handleDocItemClick={handleDocItemClick}
              handleDocsKeyDown={handleDocsKeyDown}
              previewEmlFile={previewEmlFile}
              openCaseFile={openCaseFile}
              setDocMenu={setDocMenu}
              portalFolderGrants={portalFolderGrants}
              files={files}
              uploadFilesToCurrentFolder={uploadFilesToCurrentFolder}
              setActionErr={setActionErr}
            />
          ) : (
            <CaseDetailPanelHost
              caseDocPanel={caseDocPanel}
              caseId={caseId}
              token={token}
              currentUser={currentUser}
              caseDetail={caseDetail}
              busy={busy}
              setBusy={setBusy}
              portalEnabled={portalEnabled}
              backToDocuments={backToDocuments}
              openCaseEventModal={openCaseEventModal}
              setCaseDocPanel={setCaseDocPanel}
              setEventsPreview={setEventsPreview}
              setFinancePreview={setFinancePreview}
              editMatterHeadOptions={editMatterHeadOptions}
              editMatterHeadTypeId={editMatterHeadTypeId}
              setEditMatterHeadTypeId={setEditMatterHeadTypeId}
              setEditPracticeArea={setEditPracticeArea}
              editMatterSubOptions={editMatterSubOptions}
              editPracticeArea={editPracticeArea}
              editMatterDescription={editMatterDescription}
              setEditMatterDescription={setEditMatterDescription}
              editFeeEarnerOptions={editFeeEarnerOptions}
              editFeeEarner={editFeeEarner}
              setEditFeeEarner={setEditFeeEarner}
              editStatusOptions={editStatusOptions}
              editCaseStatus={editCaseStatus}
              setEditCaseStatus={setEditCaseStatus}
              editSourceOptions={editSourceOptions}
              editSourceId={editSourceId}
              setEditSourceId={setEditSourceId}
              editPortalEnabled={editPortalEnabled}
              onEditPortalEnabledChange={onEditPortalEnabledChange}
              editCaseDropdown={editCaseDropdown}
              editCaseErr={editCaseErr}
              setEditCaseErr={setEditCaseErr}
              setManageAccessOpen={setManageAccessOpen}
              onRefresh={onRefresh}
              onCaseListInvalidate={onCaseListInvalidate}
              portalShareFolderPath={portalShareFolderPath}
              refreshPortalFolderGrants={refreshPortalFolderGrants}
              accountsSubTab={accountsSubTab}
              setAccountsSubTab={setAccountsSubTab}
              openTaskCreateModal={openTaskCreateModal}
              uiPrefs={uiPrefs}
              setUiPreference={setUiPreference}
              caseTasksLayoutOpen={caseTasksLayoutOpen}
              setCaseTasksLayoutOpen={setCaseTasksLayoutOpen}
              caseTasksSearch={caseTasksSearch}
              setCaseTasksSearch={setCaseTasksSearch}
              caseTaskMenuRows={caseTaskMenuRows}
              setCaseTaskMenuRows={setCaseTaskMenuRows}
              askConfirm={askConfirm}
              onTaskMenuInvalidate={onTaskMenuInvalidate}
              users={users}
              tasksGridColumns={tasksGridColumns}
              tasksStartResize={tasksStartResize}
              propertyDraft={propertyDraft}
              setPropertyDraft={setPropertyDraft}
              propertyBaseline={propertyBaseline}
              setPropertyDetails={setPropertyDetails}
              setActionErr={setActionErr}
              caseContacts={caseContacts}
              contactAddOpen={contactAddOpen}
              setContactAddErr={setContactAddErr}
              finishContactsDoc={finishContactsDoc}
              matterContactType={matterContactType}
              setMatterContactType={setMatterContactType}
              matterContactReference={matterContactReference}
              setMatterContactReference={setMatterContactReference}
              lawyerLinkClientIds={lawyerLinkClientIds}
              setLawyerLinkClientIds={setLawyerLinkClientIds}
              selectedGlobalContactId={selectedGlobalContactId}
              setSelectedGlobalContactId={setSelectedGlobalContactId}
              matterTypeOptions={matterTypeOptions}
              lawyerLinkableMatterContacts={lawyerLinkableMatterContacts}
              contactAddErr={contactAddErr}
              editSnapshot={editSnapshot}
              setEditSnapshot={setEditSnapshot}
              editLawyerLinkClientIds={editLawyerLinkClientIds}
              setEditLawyerLinkClientIds={setEditLawyerLinkClientIds}
              pushToGlobal={pushToGlobal}
              setPushToGlobal={setPushToGlobal}
              resolvedEditSnapshotName={resolvedEditSnapshotName}
            />
          )}
        </div>

        <CaseDetailOverlayModals
          caseId={caseId}
          token={token}
          caseDetail={caseDetail}
          files={files}
          caseContacts={caseContacts}
          users={users}
          currentUser={currentUser}
          busy={busy}
          onRefresh={onRefresh}
          onCaseListInvalidate={onCaseListInvalidate}
          onTaskMenuInvalidate={onTaskMenuInvalidate}
          commentOpen={commentOpen}
          docFolder={docFolder}
          commentEditFileId={commentEditFileId}
          commentBusy={commentBusy}
          setCommentBusy={setCommentBusy}
          commentErr={commentErr}
          setCommentErr={setCommentErr}
          commentText={commentText}
          setCommentText={setCommentText}
          setCommentOpen={setCommentOpen}
          setCommentEditFileId={setCommentEditFileId}
          emlPreviewOpen={emlPreviewOpen}
          emlPreviewFile={emlPreviewFile}
          emlPreviewData={emlPreviewData}
          emlPreviewBusy={emlPreviewBusy}
          emlPreviewErr={emlPreviewErr}
          setEmlPreviewOpen={setEmlPreviewOpen}
          setEmlPreviewFile={setEmlPreviewFile}
          setEmlPreviewData={setEmlPreviewData}
          setEmlPreviewErr={setEmlPreviewErr}
          openCaseFile={openCaseFile}
          taskCreateOpen={taskCreateOpen}
          taskCreatePreset={taskCreatePreset}
          setTaskCreateOpen={setTaskCreateOpen}
          setTaskCreatePreset={setTaskCreatePreset}
          setCaseTaskMenuRows={setCaseTaskMenuRows}
          portalQuoteSend={portalQuoteSend}
          setPortalQuoteSend={setPortalQuoteSend}
          docusignSend={docusignSend}
          setDocusignSend={setDocusignSend}
          canarySignSend={canarySignSend}
          setCanarySignSend={setCanarySignSend}
          caseEventModalOpen={caseEventModalOpen}
          setCaseEventModalOpen={setCaseEventModalOpen}
          setEventsPreview={setEventsPreview}
          quoteWizardOpen={quoteWizardOpen}
          closeQuoteWizard={closeQuoteWizard}
          quoteWasCreatedRef={quoteWasCreatedRef}
          setQuoteAwaitingSave={setQuoteAwaitingSave}
          quoteAwaitingSave={quoteAwaitingSave}
          quoteSendOpen={quoteSendOpen}
          setQuoteSendOpen={setQuoteSendOpen}
          setCaseDocPanel={setCaseDocPanel}
          setPrecedentPicker={setPrecedentPicker}
          formSendOpen={formSendOpen}
          setFormSendOpen={setFormSendOpen}
          precedentPicker={precedentPicker}
          precedentPickerSubTypeGroups={precedentPickerSubTypeGroups}
          precedentPickerExpandedSubTypes={precedentPickerExpandedSubTypes}
          precedentCategoriesBySubType={precedentCategoriesBySubType}
          togglePrecedentPickerSubTypeExpanded={togglePrecedentPickerSubTypeExpanded}
          selectPrecedentPickerNav={selectPrecedentPickerNav}
          precedentPickerSubTypeId={precedentPickerSubTypeId}
          precedentPickerCategoryId={precedentPickerCategoryId}
          precedentSearch={precedentSearch}
          setPrecedentSearch={setPrecedentSearch}
          precedentChosenId={precedentChosenId}
          setPrecedentChosenId={setPrecedentChosenId}
          filteredPrecedentChoices={filteredPrecedentChoices}
          confirmPrecedentPicker={confirmPrecedentPicker}
          contactPickModal={contactPickModal}
          contactPickErr={contactPickErr}
          contactPickMatterOptions={contactPickMatterOptions}
          pickMatterCcId={pickMatterCcId}
          setPickMatterCcId={setPickMatterCcId}
          contactPickMatterOpen={contactPickMatterOpen}
          setContactPickMatterOpen={setContactPickMatterOpen}
          pickSelectedContact={pickSelectedContact}
          setPickSelectedContact={setPickSelectedContact}
          pickLinkType={pickLinkType}
          pickLinkGlobal={pickLinkGlobal}
          setPickLinkGlobal={setPickLinkGlobal}
          contactPickTypeOptions={contactPickTypeOptions}
          setPickLinkType={setPickLinkType}
          setContactPickErr={setContactPickErr}
          pickLawyerClientIds={pickLawyerClientIds}
          setPickLawyerClientIds={setPickLawyerClientIds}
          contactPickTypeOpen={contactPickTypeOpen}
          setContactPickTypeOpen={setContactPickTypeOpen}
          lawyerLinkableMatterContacts={lawyerLinkableMatterContacts}
          matterTypeOptions={matterTypeOptions}
          setContactPickModal={setContactPickModal}
          resetContactPickForm={resetContactPickForm}
          confirmContactPick={confirmContactPick}
          textPrompt={textPrompt}
          setTextPrompt={setTextPrompt}
          manageAccessOpen={manageAccessOpen}
          setManageAccessOpen={setManageAccessOpen}
        />

        {docMenu ? (
          <CaseDocsContextMenu
            docMenu={docMenu}
            docMenuRef={docMenuRef}
            docMenuStyle={docMenuStyle}
            moveMenu={moveMenu}
            setMoveMenu={setMoveMenu}
            portalMenu={portalMenu}
            setPortalMenu={setPortalMenu}
            setDocMenu={setDocMenu}
            createFolderAtCurrentPath={createFolderAtCurrentPath}
            setDocFolder={setDocFolder}
            downloadCaseFolderZip={downloadCaseFolderZip}
            docFolder={docFolder}
            setTextPrompt={setTextPrompt}
            caseId={caseId}
            token={token}
            onRefresh={onRefresh}
            setBusy={setBusy}
            setActionErr={setActionErr}
            allFolderPaths={allFolderPaths}
            portalEnabled={portalEnabled}
            setCaseDocPanel={setCaseDocPanel}
            openPortalSharePanel={openPortalSharePanel}
            portalFolderGrants={portalFolderGrants}
            askConfirm={askConfirm}
            files={files}
            selectedDocSet={selectedDocSet}
            setSelectedDocSet={setSelectedDocSet}
            previewEmlFile={previewEmlFile}
            openCaseFile={openCaseFile}
            downloadCaseFiles={downloadCaseFiles}
            setPortalQuoteSend={setPortalQuoteSend}
            docusignEnabled={docusignEnabled}
            pushNotification={pushNotification}
            setDocusignSend={setDocusignSend}
            canarySignEnabled={canarySignEnabled}
            setCanarySignSend={setCanarySignSend}
            setTaskCreatePreset={setTaskCreatePreset}
            setTaskCreateOpen={setTaskCreateOpen}
            isCommentFile={isCommentFile}
          />
        ) : null}
      </div>
    </div>
  )
}
