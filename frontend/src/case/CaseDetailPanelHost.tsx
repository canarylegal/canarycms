import type { Dispatch, SetStateAction } from 'react'
import type { ConfirmOptions } from '../DialogProvider'
import type { UserUiPreferences } from '../userUiPreferences'
import type {
  CaseContactOut,
  CaseEventsOut,
  CaseOut,
  CasePropertyDetailsOut,
  CasePropertyPayload,
  CaseWorkflowStatus,
  FinanceOut,
  TaskMenuRow,
  UserPublic,
  UserSummary,
} from '../types'
import {
  CaseDetailAccountsPanel,
  CaseDetailContactsPanel,
  CaseDetailEditDetailsPanel,
  CaseDetailEventsPanel,
  CaseDetailFinancePanel,
  CaseDetailPortalHubPanel,
  CaseDetailPortalSharePanel,
  CaseDetailPropertyPanel,
  CaseDetailTasksPanel,
} from './CaseDetailDocPanels'
import type { CaseDetailLeftDocPanel } from './CaseDetailLeftNav'

type DropdownOption = { value: string; label: string }

type ExclusiveDropdown = {
  isOpen: (key: 'feeEarner' | 'status' | 'head' | 'source' | 'sub') => boolean
  setOpen: (key: 'feeEarner' | 'status' | 'head' | 'source' | 'sub', next: boolean) => void
  closeAll: () => void
}

export type CaseDetailPanelHostProps = {
  caseDocPanel: CaseDetailLeftDocPanel
  caseId: string
  token: string
  currentUser?: UserPublic | null
  caseDetail: CaseOut | null
  busy: boolean
  setBusy: Dispatch<SetStateAction<boolean>>
  portalEnabled: boolean
  backToDocuments: () => void
  openCaseEventModal: () => void
  setCaseDocPanel: Dispatch<SetStateAction<CaseDetailLeftDocPanel>>
  setEventsPreview: Dispatch<SetStateAction<CaseEventsOut | null>>
  setFinancePreview: Dispatch<SetStateAction<FinanceOut | null>>
  editMatterHeadOptions: DropdownOption[]
  editMatterHeadTypeId: string
  setEditMatterHeadTypeId: Dispatch<SetStateAction<string>>
  setEditPracticeArea: Dispatch<SetStateAction<string>>
  editMatterSubOptions: DropdownOption[]
  editPracticeArea: string
  editMatterDescription: string
  setEditMatterDescription: Dispatch<SetStateAction<string>>
  editFeeEarnerOptions: DropdownOption[]
  editFeeEarner: string
  setEditFeeEarner: Dispatch<SetStateAction<string>>
  editStatusOptions: { value: CaseWorkflowStatus; label: string }[]
  editCaseStatus: CaseWorkflowStatus
  setEditCaseStatus: Dispatch<SetStateAction<CaseWorkflowStatus>>
  editSourceOptions: DropdownOption[]
  editSourceId: string
  setEditSourceId: Dispatch<SetStateAction<string>>
  editPortalEnabled: boolean
  onEditPortalEnabledChange: (next: boolean) => void | Promise<void>
  editCaseDropdown: ExclusiveDropdown
  editCaseErr: string | null
  setEditCaseErr: Dispatch<SetStateAction<string | null>>
  setManageAccessOpen: Dispatch<SetStateAction<boolean>>
  onRefresh: () => void
  onCaseListInvalidate?: () => void
  portalShareFolderPath: string | null
  refreshPortalFolderGrants: () => void
  accountsSubTab: 'ledger' | 'time'
  setAccountsSubTab: Dispatch<SetStateAction<'ledger' | 'time'>>
  openTaskCreateModal: () => void
  uiPrefs: Pick<UserUiPreferences, 'case_tasks_layout' | 'case_tasks_sort_key' | 'case_tasks_sort_dir'>
  setUiPreference: <K extends keyof UserUiPreferences>(key: K, value: UserUiPreferences[K]) => void
  caseTasksLayoutOpen: boolean
  setCaseTasksLayoutOpen: Dispatch<SetStateAction<boolean>>
  caseTasksSearch: string
  setCaseTasksSearch: Dispatch<SetStateAction<string>>
  caseTaskMenuRows: TaskMenuRow[]
  setCaseTaskMenuRows: Dispatch<SetStateAction<TaskMenuRow[]>>
  askConfirm: (opts: ConfirmOptions) => Promise<boolean>
  onTaskMenuInvalidate?: () => void
  users: UserSummary[]
  tasksGridColumns: string | undefined
  tasksStartResize: (index: number, clientX: number) => void
  propertyDraft: CasePropertyPayload | null
  setPropertyDraft: Dispatch<SetStateAction<CasePropertyPayload | null>>
  propertyBaseline: CasePropertyPayload | null
  setPropertyDetails: Dispatch<SetStateAction<CasePropertyDetailsOut | null>>
  setActionErr: Dispatch<SetStateAction<string | null>>
  caseContacts: CaseContactOut[]
  contactAddOpen: boolean
  setContactAddErr: Dispatch<SetStateAction<string | null>>
  finishContactsDoc: () => void
  matterContactType: string
  setMatterContactType: Dispatch<SetStateAction<string>>
  matterContactReference: string
  setMatterContactReference: Dispatch<SetStateAction<string>>
  lawyerLinkClientIds: string[]
  setLawyerLinkClientIds: Dispatch<SetStateAction<string[]>>
  selectedGlobalContactId: string | null
  setSelectedGlobalContactId: Dispatch<SetStateAction<string | null>>
  matterTypeOptions: DropdownOption[]
  lawyerLinkableMatterContacts: CaseContactOut[]
  contactAddErr: string | null
  editSnapshot: CaseContactOut | null
  setEditSnapshot: Dispatch<SetStateAction<CaseContactOut | null>>
  editLawyerLinkClientIds: string[]
  setEditLawyerLinkClientIds: Dispatch<SetStateAction<string[]>>
  pushToGlobal: boolean
  setPushToGlobal: Dispatch<SetStateAction<boolean>>
  resolvedEditSnapshotName: string
}

export function CaseDetailPanelHost(props: CaseDetailPanelHostProps) {
  const {
    caseDocPanel,
    caseId,
    token,
    currentUser,
    caseDetail,
    busy,
    setBusy,
    portalEnabled,
    backToDocuments,
    openCaseEventModal,
    setCaseDocPanel,
    setEventsPreview,
    setFinancePreview,
    editMatterHeadOptions,
    editMatterHeadTypeId,
    setEditMatterHeadTypeId,
    setEditPracticeArea,
    editMatterSubOptions,
    editPracticeArea,
    editMatterDescription,
    setEditMatterDescription,
    editFeeEarnerOptions,
    editFeeEarner,
    setEditFeeEarner,
    editStatusOptions,
    editCaseStatus,
    setEditCaseStatus,
    editSourceOptions,
    editSourceId,
    setEditSourceId,
    editPortalEnabled,
    onEditPortalEnabledChange,
    editCaseDropdown,
    editCaseErr,
    setEditCaseErr,
    setManageAccessOpen,
    onRefresh,
    onCaseListInvalidate,
    portalShareFolderPath,
    refreshPortalFolderGrants,
    accountsSubTab,
    setAccountsSubTab,
    openTaskCreateModal,
    uiPrefs,
    setUiPreference,
    caseTasksLayoutOpen,
    setCaseTasksLayoutOpen,
    caseTasksSearch,
    setCaseTasksSearch,
    caseTaskMenuRows,
    setCaseTaskMenuRows,
    askConfirm,
    onTaskMenuInvalidate,
    users,
    tasksGridColumns,
    tasksStartResize,
    propertyDraft,
    setPropertyDraft,
    propertyBaseline,
    setPropertyDetails,
    setActionErr,
    caseContacts,
    contactAddOpen,
    setContactAddErr,
    finishContactsDoc,
    matterContactType,
    setMatterContactType,
    matterContactReference,
    setMatterContactReference,
    lawyerLinkClientIds,
    setLawyerLinkClientIds,
    selectedGlobalContactId,
    setSelectedGlobalContactId,
    matterTypeOptions,
    lawyerLinkableMatterContacts,
    contactAddErr,
    editSnapshot,
    setEditSnapshot,
    editLawyerLinkClientIds,
    setEditLawyerLinkClientIds,
    pushToGlobal,
    setPushToGlobal,
    resolvedEditSnapshotName,
  } = props

  return (
    <div className="card caseDocsCard">
      <div className="caseDocsScroll caseDocsScroll--panelOnly">
        {caseDocPanel === 'events' && caseId ? (
          <CaseDetailEventsPanel
            caseId={caseId}
            token={token}
            currentUser={currentUser}
            caseDetail={caseDetail}
            backToDocuments={backToDocuments}
            openCaseEventModal={openCaseEventModal}
            setCaseDocPanel={setCaseDocPanel}
            setEventsPreview={setEventsPreview}
          />
        ) : caseDocPanel === 'finance' && caseId ? (
          <CaseDetailFinancePanel
            caseId={caseId}
            token={token}
            backToDocuments={backToDocuments}
            setFinancePreview={setFinancePreview}
          />
        ) : caseDocPanel === 'edit-details' && caseId ? (
          <CaseDetailEditDetailsPanel
            caseId={caseId}
            busy={busy}
            setBusy={setBusy}
            backToDocuments={backToDocuments}
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
            token={token}
            onRefresh={onRefresh}
            onCaseListInvalidate={onCaseListInvalidate}
          />
        ) : caseDocPanel === 'portal-hub' && caseId && portalEnabled ? (
          <CaseDetailPortalHubPanel
            caseId={caseId}
            token={token}
            busy={busy}
            backToDocuments={backToDocuments}
            onRefresh={onRefresh}
          />
        ) : caseDocPanel === 'portal-share' && caseId && portalEnabled && portalShareFolderPath !== null ? (
          <CaseDetailPortalSharePanel
            caseId={caseId}
            token={token}
            busy={busy}
            portalShareFolderPath={portalShareFolderPath}
            backToDocuments={backToDocuments}
            refreshPortalFolderGrants={refreshPortalFolderGrants}
            onRefresh={onRefresh}
          />
        ) : caseDocPanel === 'accounts' && caseId ? (
          <CaseDetailAccountsPanel
            caseId={caseId}
            token={token}
            currentUser={currentUser}
            accountsSubTab={accountsSubTab}
            setAccountsSubTab={setAccountsSubTab}
            backToDocuments={backToDocuments}
            onRefresh={onRefresh}
          />
        ) : caseDocPanel === 'tasks' && caseId ? (
          <CaseDetailTasksPanel
            caseId={caseId}
            token={token}
            busy={busy}
            backToDocuments={backToDocuments}
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
            onRefresh={onRefresh}
            onTaskMenuInvalidate={onTaskMenuInvalidate}
            currentUser={currentUser}
            users={users}
            tasksGridColumns={tasksGridColumns}
            tasksStartResize={tasksStartResize}
          />
        ) : caseDocPanel === 'property' && propertyDraft ? (
          <CaseDetailPropertyPanel
            caseId={caseId}
            token={token}
            busy={busy}
            setBusy={setBusy}
            propertyDraft={propertyDraft}
            setPropertyDraft={setPropertyDraft}
            propertyBaseline={propertyBaseline}
            setPropertyDetails={setPropertyDetails}
            setCaseDocPanel={setCaseDocPanel}
            setActionErr={setActionErr}
            backToDocuments={backToDocuments}
            caseContacts={caseContacts}
            onRefresh={onRefresh}
          />
        ) : caseDocPanel === 'contacts' && caseId && (contactAddOpen || editSnapshot) ? (
          <CaseDetailContactsPanel
            caseId={caseId}
            token={token}
            portalEnabled={portalEnabled}
            busy={busy}
            setBusy={setBusy}
            contactAddOpen={contactAddOpen}
            setContactAddErr={setContactAddErr}
            backToDocuments={backToDocuments}
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
            lawyerLinkableContacts={lawyerLinkableMatterContacts}
            contactAddErr={contactAddErr}
            setActionErr={setActionErr}
            editSnapshot={editSnapshot}
            setEditSnapshot={setEditSnapshot}
            editLawyerLinkClientIds={editLawyerLinkClientIds}
            setEditLawyerLinkClientIds={setEditLawyerLinkClientIds}
            pushToGlobal={pushToGlobal}
            setPushToGlobal={setPushToGlobal}
            resolvedEditSnapshotName={resolvedEditSnapshotName}
          />
        ) : null}
      </div>
    </div>
  )
}
