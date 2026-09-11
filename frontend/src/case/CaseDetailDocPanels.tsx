import type { Dispatch, SetStateAction } from 'react'
import { apiFetch } from '../api'
import { CaseTimePanel } from '../CaseTimePanel'
import { EventsPage } from '../EventsPage'
import { FinancePage } from '../FinancePage'
import { LedgerPage } from '../LedgerPage'
import { SearchInput } from '../SearchInput'
import { SingleSelectDropdown } from '../SingleSelectDropdown'
import { TasksTable } from '../TasksTable'
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
import type { UserUiPreferences } from '../userUiPreferences'
import { CaseContactsAddDocForm, CaseContactsEditDocForm } from './CaseContactsDocForms'
import { CaseDocPanelChrome, CaseDocPanelScroll } from './caseDetailChrome'
import { CasePortalPanel } from './CasePortalPanel'
import { PortalFolderSharePanel } from './PortalFolderSharePanel'
import { PropertyDetailsForm } from './PropertyDetailsForm'

type ExclusiveDropdown = {
  isOpen: (key: 'feeEarner' | 'status' | 'head' | 'source' | 'sub') => boolean
  setOpen: (key: 'feeEarner' | 'status' | 'head' | 'source' | 'sub', next: boolean) => void
}

type EventsPanelProps = {
  caseId: string
  token: string
  currentUser?: UserPublic | null
  caseDetail: CaseOut | null
  backToDocuments: () => void
  openCaseEventModal: () => void
  setCaseDocPanel: (panel: 'documents') => void
  setEventsPreview: (v: CaseEventsOut) => void
}

export function CaseDetailEventsPanel({
  caseId,
  token,
  currentUser,
  caseDetail,
  backToDocuments,
  openCaseEventModal,
  setCaseDocPanel,
  setEventsPreview,
}: EventsPanelProps) {
  return (
    <div className="caseDocPanelInset caseDocPanelHost stack">
      <CaseDocPanelChrome title="Calendar" onClose={backToDocuments} />
      <CaseDocPanelScroll fillHost>
        <EventsPage
          caseId={caseId}
          token={token}
          me={currentUser}
          embedded
          onRequestNewEvent={openCaseEventModal}
          caseLabel={
            caseDetail
              ? `${caseDetail.case_number}${caseDetail.matter_description ? ` — ${caseDetail.matter_description}` : ''}`.trim()
              : ''
          }
          onClose={() => {
            setCaseDocPanel('documents')
            void apiFetch<CaseEventsOut>(`/cases/${caseId}/events`, { token }).then(setEventsPreview).catch(() => {})
          }}
        />
      </CaseDocPanelScroll>
    </div>
  )
}

type FinancePanelProps = {
  caseId: string
  token: string
  backToDocuments: () => void
  setFinancePreview: (v: FinanceOut) => void
}

export function CaseDetailFinancePanel({ caseId, token, backToDocuments, setFinancePreview }: FinancePanelProps) {
  return (
    <div className="caseDocPanelInset caseDocPanelHost stack">
      <CaseDocPanelChrome title="Finance" onClose={backToDocuments} />
      <CaseDocPanelScroll>
        <FinancePage
          caseId={caseId}
          token={token}
          embedded
          onSaved={() => {
            void apiFetch<FinanceOut>(`/cases/${caseId}/finance`, { token })
              .then(setFinancePreview)
              .catch(() => {})
          }}
        />
      </CaseDocPanelScroll>
    </div>
  )
}

type PortalHubPanelProps = {
  caseId: string
  token: string
  busy: boolean
  backToDocuments: () => void
  onRefresh: () => void
}

export function CaseDetailPortalHubPanel({ caseId, token, busy, backToDocuments, onRefresh }: PortalHubPanelProps) {
  return (
    <div className="caseDocPanelInset caseDocPanelHost stack">
      <CaseDocPanelChrome title="Portal" onClose={backToDocuments} closeDisabled={busy} />
      <CaseDocPanelScroll>
        <CasePortalPanel token={token} caseId={caseId} onFilesChanged={onRefresh} />
      </CaseDocPanelScroll>
    </div>
  )
}

type PortalSharePanelProps = {
  caseId: string
  token: string
  busy: boolean
  portalShareFolderPath: string
  backToDocuments: () => void
  refreshPortalFolderGrants: () => void
  onRefresh: () => void
}

export function CaseDetailPortalSharePanel({
  caseId,
  token,
  busy,
  portalShareFolderPath,
  backToDocuments,
  refreshPortalFolderGrants,
  onRefresh,
}: PortalSharePanelProps) {
  return (
    <div className="caseDocPanelInset caseDocPanelHost stack">
      <CaseDocPanelChrome
        title="Share folder"
        subtitle="Portal folder access"
        onClose={backToDocuments}
        closeDisabled={busy}
      />
      <CaseDocPanelScroll>
        <PortalFolderSharePanel
          token={token}
          caseId={caseId}
          folderPath={portalShareFolderPath}
          onChanged={() => {
            refreshPortalFolderGrants()
            onRefresh()
          }}
        />
      </CaseDocPanelScroll>
    </div>
  )
}

type AccountsPanelProps = {
  caseId: string
  token: string
  currentUser?: UserPublic | null
  accountsSubTab: 'ledger' | 'time'
  setAccountsSubTab: (v: 'ledger' | 'time') => void
  backToDocuments: () => void
  onRefresh: () => void
}

export function CaseDetailAccountsPanel({
  caseId,
  token,
  currentUser,
  accountsSubTab,
  setAccountsSubTab,
  backToDocuments,
  onRefresh,
}: AccountsPanelProps) {
  return (
    <div className="caseDocPanelInset caseDocPanelHost stack">
      <CaseDocPanelChrome
        title="Accounts"
        onClose={backToDocuments}
        actions={
          <>
            <button
              type="button"
              className={`btn${accountsSubTab === 'ledger' ? ' primary' : ''}`}
              onClick={() => setAccountsSubTab('ledger')}
            >
              Ledger
            </button>
            <button
              type="button"
              className={`btn${accountsSubTab === 'time' ? ' primary' : ''}`}
              onClick={() => setAccountsSubTab('time')}
            >
              Time
            </button>
          </>
        }
      />
      <div className="caseDocLedgerEmbed">
        <CaseDocPanelScroll>
          {accountsSubTab === 'ledger' ? (
            <LedgerPage
              caseId={caseId}
              token={token}
              currentUserId={currentUser?.id}
              onCaseChanged={onRefresh}
            />
          ) : (
            <CaseTimePanel
              caseId={caseId}
              token={token}
              isAdmin={Boolean(currentUser?.admin_console_access)}
              currentUserId={currentUser?.id ?? ''}
            />
          )}
        </CaseDocPanelScroll>
      </div>
    </div>
  )
}

type EditDetailsPanelProps = {
  caseId: string
  busy: boolean
  setBusy: (v: boolean) => void
  backToDocuments: () => void
  editMatterHeadOptions: { value: string; label: string }[]
  editMatterHeadTypeId: string
  setEditMatterHeadTypeId: (v: string) => void
  setEditPracticeArea: (v: string) => void
  editMatterSubOptions: { value: string; label: string }[]
  editPracticeArea: string
  editMatterDescription: string
  setEditMatterDescription: (v: string) => void
  editFeeEarnerOptions: { value: string; label: string }[]
  editFeeEarner: string
  setEditFeeEarner: (v: string) => void
  editStatusOptions: { value: string; label: string }[]
  editCaseStatus: CaseWorkflowStatus
  setEditCaseStatus: (v: CaseWorkflowStatus) => void
  editSourceOptions: { value: string; label: string }[]
  editSourceId: string
  setEditSourceId: (v: string) => void
  editPortalEnabled: boolean
  onEditPortalEnabledChange: (checked: boolean) => void | Promise<void>
  editCaseDropdown: ExclusiveDropdown
  editCaseErr: string | null
  setEditCaseErr: (v: string | null) => void
  setManageAccessOpen: (v: boolean) => void
  token: string
  onRefresh: () => void
  onCaseListInvalidate?: () => void
}

export function CaseDetailEditDetailsPanel({
  caseId,
  busy,
  setBusy,
  backToDocuments,
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
  token,
  onRefresh,
  onCaseListInvalidate,
}: EditDetailsPanelProps) {
  return (
    <div className="caseDocPanelInset caseDocPanelHost stack">
      <CaseDocPanelChrome title="Case details" onClose={backToDocuments} closeDisabled={busy} />
      <CaseDocPanelScroll>
        <div className="card caseDocEditEmbed">
          <div className="muted" style={{ marginBottom: 12 }}>
            Reference is immutable and generated automatically. Client name comes from matter contacts with type
            &quot;Client&quot;. Use Contacts in the left menu → Edit to change names.
          </div>
          <SingleSelectDropdown
            label="Matter type"
            options={editMatterHeadOptions}
            value={editMatterHeadTypeId}
            onChange={(v) => {
              setEditMatterHeadTypeId(v)
              setEditPracticeArea('')
            }}
            open={editCaseDropdown.isOpen('head')}
            onOpenChange={(next) => editCaseDropdown.setOpen('head', next)}
            disabled={busy}
            placeholder="— select —"
            emptyMessage={
              editMatterHeadOptions.length === 0
                ? 'No matter types available — add them under Admin → Matters.'
                : undefined
            }
          />
          {editMatterHeadTypeId ? (
            <SingleSelectDropdown
              label="Sub-type"
              options={editMatterSubOptions}
              value={editPracticeArea}
              onChange={setEditPracticeArea}
              open={editCaseDropdown.isOpen('sub')}
              onOpenChange={(next) => editCaseDropdown.setOpen('sub', next)}
              disabled={busy}
              placeholder="— select —"
              emptyMessage={
                editMatterSubOptions.length === 0
                  ? 'No sub-types for this matter type — add them under Admin → Matters.'
                  : undefined
              }
            />
          ) : (
            <p className="muted" style={{ margin: 0, fontSize: 13 }}>
              Choose a matter type, then pick a sub-type.
            </p>
          )}
          <label className="field">
            <span>Description</span>
            <input value={editMatterDescription} onChange={(e) => setEditMatterDescription(e.target.value)} />
          </label>
          <SingleSelectDropdown
            label="Fee earner"
            options={editFeeEarnerOptions}
            value={editFeeEarner}
            onChange={setEditFeeEarner}
            open={editCaseDropdown.isOpen('feeEarner')}
            onOpenChange={(next) => editCaseDropdown.setOpen('feeEarner', next)}
            disabled={busy}
            placeholder="Select fee earner"
            emptyMessage={editFeeEarnerOptions.length === 0 ? 'No fee earners available.' : undefined}
          />
          <SingleSelectDropdown
            label="Status"
            options={editStatusOptions}
            value={editCaseStatus}
            onChange={(v) => setEditCaseStatus(v as CaseWorkflowStatus)}
            open={editCaseDropdown.isOpen('status')}
            onOpenChange={(next) => editCaseDropdown.setOpen('status', next)}
            disabled={busy}
            placeholder="— select —"
          />
          <SingleSelectDropdown
            label="Source"
            options={editSourceOptions}
            value={editSourceId}
            onChange={setEditSourceId}
            open={editCaseDropdown.isOpen('source')}
            onOpenChange={(next) => editCaseDropdown.setOpen('source', next)}
            disabled={busy}
            placeholder="— none —"
          />
          <label className="row field" style={{ gap: 10, alignItems: 'center', cursor: busy ? 'default' : 'pointer' }}>
            <input
              type="checkbox"
              checked={editPortalEnabled}
              disabled={busy}
              onChange={(e) => void onEditPortalEnabledChange(e.target.checked)}
            />
            <span>
              Enable portal
              <span className="muted" style={{ display: 'block', fontSize: 13, marginTop: 2 }}>
                Allow folder sharing, client preview, and portal notifications for this matter.
              </span>
            </span>
          </label>
          <div className="row" style={{ justifyContent: 'flex-start', marginTop: 8 }}>
            <button type="button" className="btn" disabled={busy || !caseId} onClick={() => setManageAccessOpen(true)}>
              Manage access…
            </button>
          </div>
          {editCaseErr ? <div className="error">{editCaseErr}</div> : null}
          <div className="row" style={{ justifyContent: 'flex-end', marginTop: 12, gap: 8 }}>
            <button className="btn" onClick={backToDocuments} disabled={busy}>
              Cancel
            </button>
            <button
              className="btn primary"
              disabled={busy || !editMatterDescription.trim() || !editFeeEarner}
              onClick={async () => {
                if (!editFeeEarner) {
                  setEditCaseErr('Select a fee earner.')
                  return
                }
                setBusy(true)
                setEditCaseErr(null)
                try {
                  await apiFetch(`/cases/${caseId}`, {
                    token,
                    method: 'PATCH',
                    json: {
                      matter_description: editMatterDescription.trim(),
                      fee_earner_user_id: editFeeEarner,
                      status: editCaseStatus,
                      source_id: editSourceId.trim() ? editSourceId.trim() : null,
                      ...(editPracticeArea.trim()
                        ? { matter_sub_type_id: editPracticeArea.trim() }
                        : { matter_sub_type_id: null, matter_head_type_id: null }),
                      portal_enabled: editPortalEnabled,
                    },
                  })
                  backToDocuments()
                  onRefresh()
                  onCaseListInvalidate?.()
                } catch (e: unknown) {
                  const err = e as { message?: string }
                  setEditCaseErr(err?.message ?? 'Failed to update case')
                } finally {
                  setBusy(false)
                }
              }}
            >
              Save
            </button>
          </div>
        </div>
      </CaseDocPanelScroll>
    </div>
  )
}

type TasksPanelProps = {
  caseId: string
  token: string
  busy: boolean
  backToDocuments: () => void
  openTaskCreateModal: () => void
  uiPrefs: Pick<UserUiPreferences, 'case_tasks_layout' | 'case_tasks_sort_key' | 'case_tasks_sort_dir'>
  setUiPreference: <K extends keyof UserUiPreferences>(key: K, value: UserUiPreferences[K]) => void
  caseTasksLayoutOpen: boolean
  setCaseTasksLayoutOpen: (v: boolean) => void
  caseTasksSearch: string
  setCaseTasksSearch: (v: string) => void
  caseTaskMenuRows: TaskMenuRow[]
  setCaseTaskMenuRows: (v: TaskMenuRow[]) => void
  askConfirm: (opts: { title: string; message: string }) => Promise<boolean>
  onRefresh: () => void
  onTaskMenuInvalidate?: () => void
  currentUser?: UserPublic | null
  users: UserSummary[]
  tasksGridColumns: string | undefined
  tasksStartResize: (colIndex: number, startClientX: number, measureRow?: HTMLElement | null) => void
}

export function CaseDetailTasksPanel({
  caseId,
  token,
  busy,
  backToDocuments,
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
  onRefresh,
  onTaskMenuInvalidate,
  currentUser,
  users,
  tasksGridColumns,
  tasksStartResize,
}: TasksPanelProps) {
  return (
    <div className="caseDocPanelInset caseDocPanelHost stack">
      <CaseDocPanelChrome
        title="Tasks"
        onClose={backToDocuments}
        actions={
          <>
            <button type="button" className="btn primary" disabled={busy} onClick={() => openTaskCreateModal()}>
              New task
            </button>
            <div className="tasksToolbarLayoutGroup">
              <span className="tasksToolbarLayoutLabel">View</span>
              <SingleSelectDropdown
                hideLabel
                label="Task layout"
                options={[
                  { value: 'list', label: 'List' },
                  { value: 'kanban', label: 'Kanban' },
                ]}
                value={uiPrefs.case_tasks_layout}
                onChange={(v) => setUiPreference('case_tasks_layout', v as 'list' | 'kanban')}
                open={caseTasksLayoutOpen}
                onOpenChange={setCaseTasksLayoutOpen}
              />
            </div>
            <SearchInput
              placeholder="Search tasks…"
              value={caseTasksSearch}
              onChange={(e) => setCaseTasksSearch(e.target.value)}
              onClear={() => setCaseTasksSearch('')}
              style={{ flex: 1, minWidth: 160 }}
              aria-label="Search tasks for this matter"
            />
            <button
              type="button"
              className="btn"
              onClick={() => {
                void apiFetch<TaskMenuRow[]>(`/tasks?case_id=${encodeURIComponent(caseId)}`, { token })
                  .then((data) => setCaseTaskMenuRows(Array.isArray(data) ? data : []))
                  .catch(() => setCaseTaskMenuRows([]))
              }}
            >
              Refresh
            </button>
            <button
              type="button"
              className="btn"
              onClick={() =>
                void (async () => {
                  const ok = await askConfirm({
                    title: 'Clear completed tasks',
                    message:
                      'Remove all completed tasks for this matter from the list? Only tasks on this matter are affected.',
                  })
                  if (!ok) return
                  try {
                    await apiFetch(`/tasks/completed?case_id=${encodeURIComponent(caseId)}`, {
                      token,
                      method: 'DELETE',
                    })
                    void apiFetch<TaskMenuRow[]>(`/tasks?case_id=${encodeURIComponent(caseId)}`, { token })
                      .then((data) => setCaseTaskMenuRows(Array.isArray(data) ? data : []))
                      .catch(() => setCaseTaskMenuRows([]))
                    onRefresh()
                    onTaskMenuInvalidate?.()
                  } catch {
                    // ignore
                  }
                })()
              }
            >
              Clear completed
            </button>
          </>
        }
      />
      <CaseDocPanelScroll>
        <TasksTable
          token={token}
          currentUserId={currentUser?.id ?? ''}
          users={users}
          rows={caseTaskMenuRows}
          layoutMode={uiPrefs.case_tasks_layout}
          search={caseTasksSearch}
          filterMatterType=""
          onSelectCase={() => {}}
          sortKey={uiPrefs.case_tasks_sort_key}
          sortDir={uiPrefs.case_tasks_sort_dir}
          onSort={(k) => {
            if (k === uiPrefs.case_tasks_sort_key) {
              setUiPreference('case_tasks_sort_dir', uiPrefs.case_tasks_sort_dir === 'asc' ? 'desc' : 'asc')
            } else {
              setUiPreference('case_tasks_sort_key', k)
              setUiPreference('case_tasks_sort_dir', k === 'priority' ? 'desc' : 'asc')
            }
          }}
          gridTemplateColumns={tasksGridColumns}
          startColumnResize={tasksStartResize}
          onInvalidate={() => {
            void apiFetch<TaskMenuRow[]>(`/tasks?case_id=${encodeURIComponent(caseId)}`, { token })
              .then((data) => setCaseTaskMenuRows(Array.isArray(data) ? data : []))
              .catch(() => setCaseTaskMenuRows([]))
            onRefresh()
            onTaskMenuInvalidate?.()
          }}
          embedded
          suppressCaseOpen
        />
      </CaseDocPanelScroll>
    </div>
  )
}

type PropertyPanelProps = {
  caseId: string | undefined
  token: string
  busy: boolean
  setBusy: (v: boolean) => void
  propertyDraft: CasePropertyPayload
  setPropertyDraft: (d: CasePropertyPayload) => void
  propertyBaseline: CasePropertyPayload | null
  setPropertyDetails: (v: CasePropertyDetailsOut) => void
  setCaseDocPanel: (panel: 'documents') => void
  setActionErr: (v: string | null) => void
  backToDocuments: () => void
  caseContacts: CaseContactOut[]
  onRefresh: () => void
}

export function CaseDetailPropertyPanel({
  caseId,
  token,
  busy,
  setBusy,
  propertyDraft,
  setPropertyDraft,
  propertyBaseline,
  setPropertyDetails,
  setCaseDocPanel,
  setActionErr,
  backToDocuments,
  caseContacts,
  onRefresh,
}: PropertyPanelProps) {
  return (
    <div className="caseDocPanelInset caseDocPanelHost stack">
      <CaseDocPanelChrome
        title="Property details"
        onClose={backToDocuments}
        closeDisabled={busy}
        actions={
          <>
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={() => {
                if (propertyBaseline) {
                  setPropertyDraft(JSON.parse(JSON.stringify(propertyBaseline)) as CasePropertyPayload)
                }
                setCaseDocPanel('documents')
              }}
            >
              Discard
            </button>
            <button
              type="button"
              className="btn primary"
              disabled={busy}
              onClick={async () => {
                if (!caseId) return
                setBusy(true)
                setActionErr(null)
                try {
                  const lines = [...propertyDraft.free_lines]
                  while (lines.length < 6) lines.push('')
                  const out = await apiFetch<CasePropertyDetailsOut>(`/cases/${caseId}/property-details`, {
                    method: 'PUT',
                    token,
                    json: { ...propertyDraft, free_lines: lines.slice(0, 6) },
                  })
                  setPropertyDetails(out)
                  setCaseDocPanel('documents')
                } catch (e: any) {
                  setActionErr(e?.message ?? 'Save failed')
                } finally {
                  setBusy(false)
                }
              }}
            >
              Save and close
            </button>
          </>
        }
      />
      <CaseDocPanelScroll>
        <div className="card caseDocPropertyEmbed">
          <PropertyDetailsForm
            draft={propertyDraft}
            onChange={setPropertyDraft}
            disabled={busy}
            token={token}
            caseId={caseId}
            caseContacts={caseContacts}
            onCaseContactsChange={onRefresh}
          />
        </div>
      </CaseDocPanelScroll>
    </div>
  )
}

type ContactsPanelProps = {
  caseId: string
  token: string
  portalEnabled: boolean
  busy: boolean
  setBusy: (v: boolean) => void
  contactAddOpen: boolean
  setContactAddErr: (v: string | null) => void
  backToDocuments: () => void
  finishContactsDoc: () => void
  matterContactType: string
  setMatterContactType: (v: string) => void
  matterContactReference: string
  setMatterContactReference: (v: string) => void
  lawyerLinkClientIds: string[]
  setLawyerLinkClientIds: Dispatch<SetStateAction<string[]>>
  selectedGlobalContactId: string | null
  setSelectedGlobalContactId: (v: string | null) => void
  matterTypeOptions: { value: string; label: string }[]
  lawyerLinkableContacts: CaseContactOut[]
  contactAddErr: string | null
  setActionErr: (v: string | null) => void
  editSnapshot: CaseContactOut | null
  setEditSnapshot: Dispatch<SetStateAction<CaseContactOut | null>>
  editLawyerLinkClientIds: string[]
  setEditLawyerLinkClientIds: Dispatch<SetStateAction<string[]>>
  pushToGlobal: boolean
  setPushToGlobal: (v: boolean) => void
  resolvedEditSnapshotName: string
}

export function CaseDetailContactsPanel({
  caseId,
  token,
  portalEnabled,
  busy,
  setBusy,
  contactAddOpen,
  setContactAddErr,
  backToDocuments,
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
  lawyerLinkableContacts,
  contactAddErr,
  setActionErr,
  editSnapshot,
  setEditSnapshot,
  editLawyerLinkClientIds,
  setEditLawyerLinkClientIds,
  pushToGlobal,
  setPushToGlobal,
  resolvedEditSnapshotName,
}: ContactsPanelProps) {
  return (
    <div className="caseDocPanelInset caseDocPanelHost stack">
      <CaseDocPanelChrome
        title={contactAddOpen ? 'Add contact' : 'Edit contact'}
        subtitle={
          contactAddOpen
            ? 'Link an existing global contact or create a new one.'
            : 'Update the snapshot on this matter.'
        }
        onClose={() => {
          if (contactAddOpen) {
            setContactAddErr(null)
          }
          backToDocuments()
        }}
        closeDisabled={busy}
      />
      <CaseDocPanelScroll>
        <div className="card caseDocPropertyEmbed" style={{ maxWidth: '100%' }}>
          {contactAddOpen ? (
            <CaseContactsAddDocForm
              token={token}
              caseId={caseId}
              busy={busy}
              setBusy={setBusy}
              onDone={finishContactsDoc}
              matterContactType={matterContactType}
              setMatterContactType={setMatterContactType}
              matterContactReference={matterContactReference}
              setMatterContactReference={setMatterContactReference}
              lawyerLinkClientIds={lawyerLinkClientIds}
              setLawyerLinkClientIds={setLawyerLinkClientIds}
              selectedGlobalContactId={selectedGlobalContactId}
              setSelectedGlobalContactId={setSelectedGlobalContactId}
              matterTypeOptions={matterTypeOptions}
              lawyerLinkableContacts={lawyerLinkableContacts}
              contactAddErr={contactAddErr}
              setContactAddErr={setContactAddErr}
              setActionErr={setActionErr}
              onGlobalContactsUpdated={() => {}}
            />
          ) : editSnapshot ? (
            <CaseContactsEditDocForm
              token={token}
              caseId={caseId}
              portalEnabled={portalEnabled}
              busy={busy}
              setBusy={setBusy}
              editSnapshot={editSnapshot}
              setEditSnapshot={setEditSnapshot}
              editLawyerLinkClientIds={editLawyerLinkClientIds}
              setEditLawyerLinkClientIds={setEditLawyerLinkClientIds}
              pushToGlobal={pushToGlobal}
              setPushToGlobal={setPushToGlobal}
              resolvedEditSnapshotName={resolvedEditSnapshotName}
              matterTypeOptions={matterTypeOptions}
              lawyerLinkableContacts={lawyerLinkableContacts}
              onDone={finishContactsDoc}
              setActionErr={setActionErr}
            />
          ) : null}
        </div>
      </CaseDocPanelScroll>
    </div>
  )
}
