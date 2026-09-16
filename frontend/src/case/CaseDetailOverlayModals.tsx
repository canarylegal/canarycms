import type { Dispatch, SetStateAction } from 'react'
import { CaseEventCreateModal } from '../CaseEventCreateModal'
import { ManageCaseAccessModal } from '../ManageCaseAccessModal'
import { apiFetch } from '../api'
import { SendQuoteViaPortalModal } from '../SendQuoteViaPortalModal'
import { SendPortalFormModal } from '../SendPortalFormModal'
import { SendDocusignModal } from '../SendDocusignModal'
import { SendCanarySignModal } from '../SendCanarySignModal'
import { TaskCreateModal } from '../TaskCreateModal'
import { QuoteWizard } from '../QuoteWizard'
import { QuoteSendPrompt } from '../QuoteSendPrompt'
import type { QuoteAwaitingSaveContext } from '../quoteAwaitingSave'
import { QUOTE_EMAIL_PRECEDENT_REFERENCE, type PrecedentPickerState } from '../quoteEmailPrecedent'
import { TextPromptModal } from '../TextPromptModal'
import type {
  CaseContactOut,
  CaseEventsOut,
  CaseOut,
  ContactOut,
  FileSummary,
  PrecedentCategoryOut,
  PrecedentOut,
  TaskMenuRow,
  UserPublic,
  UserSummary,
} from '../types'
import type { EmlPreviewData } from './emlPreview'
import { EmlPreviewModal } from './emlPreview'
import { CaseCommentModal } from './CaseCommentModal'
import { CaseContactPickModal } from './CaseContactPickModal'
import { CasePrecedentPickerModal } from './CasePrecedentPickerModal'

export type CaseDetailOverlayModalsProps = {
  caseId: string | null
  token: string
  caseDetail: CaseOut | null
  files: FileSummary[]
  caseContacts: CaseContactOut[]
  users: UserSummary[]
  currentUser?: UserPublic | null
  busy: boolean
  onRefresh: () => void
  onCaseListInvalidate?: () => void
  onTaskMenuInvalidate?: () => void

  commentOpen: boolean
  docFolder: string
  commentEditFileId: string | null
  commentBusy: boolean
  setCommentBusy: (v: boolean) => void
  commentErr: string | null
  setCommentErr: (v: string | null) => void
  commentText: string
  setCommentText: (v: string) => void
  setCommentOpen: (v: boolean) => void
  setCommentEditFileId: (v: string | null) => void

  emlPreviewOpen: boolean
  emlPreviewFile: FileSummary | null
  emlPreviewData: EmlPreviewData | null
  emlPreviewBusy: boolean
  emlPreviewErr: string | null
  setEmlPreviewOpen: (v: boolean) => void
  setEmlPreviewFile: (v: FileSummary | null) => void
  setEmlPreviewData: (v: EmlPreviewData | null) => void
  setEmlPreviewErr: (v: string | null) => void
  openCaseFile: (f: FileSummary) => void

  taskCreateOpen: boolean
  taskCreatePreset: { standardTaskId?: string; title?: string } | null
  setTaskCreateOpen: (v: boolean) => void
  setTaskCreatePreset: (v: { standardTaskId?: string; title?: string } | null) => void
  setCaseTaskMenuRows: Dispatch<SetStateAction<TaskMenuRow[]>>

  portalQuoteSend: { fileId: string; fileName: string; folderPath: string } | null
  setPortalQuoteSend: (v: { fileId: string; fileName: string; folderPath: string } | null) => void

  docusignSend: { fileId: string; fileName: string; amendFromId?: string | null } | null
  setDocusignSend: (
    v: { fileId: string; fileName: string; amendFromId?: string | null } | null,
  ) => void

  canarySignSend: { fileId: string; fileName: string; amendFromId?: string | null } | null
  setCanarySignSend: (
    v: { fileId: string; fileName: string; amendFromId?: string | null } | null,
  ) => void

  caseEventModalOpen: boolean
  setCaseEventModalOpen: (v: boolean) => void
  setEventsPreview: (v: CaseEventsOut | null) => void

  quoteWizardOpen: boolean
  closeQuoteWizard: () => void
  quoteWasCreatedRef: { current: boolean }
  setQuoteAwaitingSave: (v: QuoteAwaitingSaveContext | null) => void

  quoteAwaitingSave: QuoteAwaitingSaveContext | null
  quoteSendOpen: boolean
  setQuoteSendOpen: (v: boolean) => void
  setCaseDocPanel: (v: 'documents') => void
  setPrecedentPicker: (v: PrecedentPickerState | null) => void

  formSendOpen: boolean
  setFormSendOpen: (v: boolean) => void

  precedentPicker: PrecedentPickerState | null
  precedentPickerSubTypeGroups: { subId: string; subName: string }[]
  precedentPickerExpandedSubTypes: Set<string>
  precedentCategoriesBySubType: Record<string, PrecedentCategoryOut[]>
  togglePrecedentPickerSubTypeExpanded: (subTypeId: string) => void
  selectPrecedentPickerNav: (subTypeId: string, categoryId: string | null) => void
  precedentPickerSubTypeId: string | null
  precedentPickerCategoryId: string | null
  precedentSearch: string
  setPrecedentSearch: (v: string) => void
  precedentChosenId: string | null
  setPrecedentChosenId: (v: string | null) => void
  filteredPrecedentChoices: PrecedentOut[]
  confirmPrecedentPicker: () => void

  contactPickModal: {
    precedentId: string | null
    composeKind: 'letter' | 'email'
    attachmentFileIds?: string[]
  } | null
  contactPickErr: string | null
  contactPickMatterOptions: { value: string; label: string; hint?: string }[]
  pickMatterCcId: string
  setPickMatterCcId: (v: string) => void
  contactPickMatterOpen: boolean
  setContactPickMatterOpen: (v: boolean) => void
  pickSelectedContact: ContactOut | null
  setPickSelectedContact: (v: ContactOut | null) => void
  pickLinkType: string
  pickLinkGlobal: boolean
  setPickLinkGlobal: (v: boolean) => void
  contactPickTypeOptions: { value: string; label: string }[]
  setPickLinkType: (v: string) => void
  setContactPickErr: (v: string | null) => void
  pickLawyerClientIds: string[]
  setPickLawyerClientIds: Dispatch<SetStateAction<string[]>>
  contactPickTypeOpen: boolean
  setContactPickTypeOpen: (v: boolean) => void
  lawyerLinkableMatterContacts: CaseContactOut[]
  matterTypeOptions: { value: string; label: string }[]
  setContactPickModal: (
    v: {
      precedentId: string | null
      composeKind: 'letter' | 'email'
      attachmentFileIds?: string[]
    } | null,
  ) => void
  resetContactPickForm: () => void
  confirmContactPick: () => void

  textPrompt: {
    title: string
    hint?: string
    initial: string
    confirmLabel: string
    onConfirm: (value: string) => void
  } | null
  setTextPrompt: Dispatch<
    SetStateAction<{
      title: string
      hint?: string
      initial: string
      confirmLabel: string
      onConfirm: (value: string) => void
    } | null>
  >

  manageAccessOpen: boolean
  setManageAccessOpen: (v: boolean) => void
}

function clearEmlPreview(props: {
  setEmlPreviewOpen: (v: boolean) => void
  setEmlPreviewFile: (v: FileSummary | null) => void
  setEmlPreviewData: (v: EmlPreviewData | null) => void
  setEmlPreviewErr: (v: string | null) => void
}) {
  props.setEmlPreviewOpen(false)
  props.setEmlPreviewFile(null)
  props.setEmlPreviewData(null)
  props.setEmlPreviewErr(null)
}

export function CaseDetailOverlayModals(props: CaseDetailOverlayModalsProps) {
  const {
    caseId,
    token,
    caseDetail,
    files,
    caseContacts,
    users,
    currentUser,
    busy,
    onRefresh,
    onCaseListInvalidate,
    onTaskMenuInvalidate,
  } = props

  return (
    <>
      {props.commentOpen && caseId ? (
        <CaseCommentModal
          caseId={caseId}
          token={token}
          docFolder={props.docFolder}
          commentEditFileId={props.commentEditFileId}
          commentBusy={props.commentBusy}
          setCommentBusy={props.setCommentBusy}
          commentErr={props.commentErr}
          setCommentErr={props.setCommentErr}
          commentText={props.commentText}
          setCommentText={props.setCommentText}
          onClose={() => {
            props.setCommentOpen(false)
            props.setCommentEditFileId(null)
          }}
          onSaved={onRefresh}
        />
      ) : null}

      {props.emlPreviewOpen && props.emlPreviewFile ? (
        <EmlPreviewModal
          file={props.emlPreviewFile}
          data={props.emlPreviewData}
          loading={props.emlPreviewBusy}
          error={props.emlPreviewErr}
          onClose={() => clearEmlPreview(props)}
          onOpenExternal={() => {
            const f = props.emlPreviewFile
            clearEmlPreview(props)
            if (f) void props.openCaseFile(f)
          }}
        />
      ) : null}

      <TaskCreateModal
        open={props.taskCreateOpen}
        token={token}
        users={users}
        caseIdFixed={caseId ?? null}
        preset={props.taskCreatePreset}
        onClose={() => {
          props.setTaskCreateOpen(false)
          props.setTaskCreatePreset(null)
        }}
        onCreated={() => {
          onRefresh()
          onTaskMenuInvalidate?.()
          if (caseId) {
            void apiFetch<TaskMenuRow[]>(`/tasks?case_id=${encodeURIComponent(caseId)}`, { token })
              .then((data) => props.setCaseTaskMenuRows(Array.isArray(data) ? data : []))
              .catch(() => props.setCaseTaskMenuRows([]))
          }
        }}
      />

      {caseId && props.portalQuoteSend ? (
        <SendQuoteViaPortalModal
          token={token}
          caseId={caseId}
          fileId={props.portalQuoteSend.fileId}
          fileName={props.portalQuoteSend.fileName}
          folderPath={props.portalQuoteSend.folderPath}
          open
          onClose={() => props.setPortalQuoteSend(null)}
          onSent={() => {
            onRefresh()
          }}
        />
      ) : null}

      {caseId && props.docusignSend ? (
        <SendDocusignModal
          token={token}
          caseId={caseId}
          fileId={props.docusignSend.fileId}
          fileName={props.docusignSend.fileName}
          caseContacts={caseContacts}
          amendFromId={props.docusignSend.amendFromId ?? null}
          existing={files.find((x) => x.id === props.docusignSend!.fileId)?.docusign_signing ?? null}
          open
          onClose={() => props.setDocusignSend(null)}
          onSent={() => {
            onRefresh()
          }}
        />
      ) : null}

      {caseId && props.canarySignSend ? (
        <SendCanarySignModal
          token={token}
          caseId={caseId}
          fileId={props.canarySignSend.fileId}
          fileName={props.canarySignSend.fileName}
          caseContacts={caseContacts}
          amendFromId={props.canarySignSend.amendFromId ?? null}
          existing={files.find((x) => x.id === props.canarySignSend!.fileId)?.canary_signing ?? null}
          open
          onClose={() => props.setCanarySignSend(null)}
          onSent={() => {
            props.setCanarySignSend(null)
            onRefresh()
          }}
        />
      ) : null}

      {caseId ? (
        <CaseEventCreateModal
          open={props.caseEventModalOpen}
          caseId={caseId}
          token={token}
          caseLabel={
            caseDetail
              ? `${caseDetail.case_number}${caseDetail.matter_description ? ` — ${caseDetail.matter_description}` : ''}`.trim()
              : ''
          }
          onClose={() => props.setCaseEventModalOpen(false)}
          onSaved={() => {
            void apiFetch<CaseEventsOut>(`/cases/${caseId}/events`, { token })
              .then(props.setEventsPreview)
              .catch(() => {})
            onRefresh()
          }}
        />
      ) : null}

      {props.quoteWizardOpen && caseDetail ? (
        <QuoteWizard
          token={token}
          open={props.quoteWizardOpen}
          presetCase={caseDetail}
          onClose={props.closeQuoteWizard}
          onOpenNewMatter={() => {}}
          onCaseCreatedRefresh={() => {}}
          pendingNewCaseId={null}
          onClearPendingNewCase={() => {}}
          onQuoteCreated={() => {
            props.quoteWasCreatedRef.current = true
          }}
          onAwaitingQuoteSave={props.setQuoteAwaitingSave}
        />
      ) : null}

      {props.quoteAwaitingSave ? (
        <QuoteSendPrompt
          token={token}
          caseId={props.quoteAwaitingSave.caseId}
          fileId={props.quoteAwaitingSave.fileId}
          preferredContactId={props.quoteAwaitingSave.preferredContactId}
          portalEnabled={props.quoteAwaitingSave.portalEnabled}
          open={props.quoteSendOpen}
          onClose={() => {
            props.setQuoteSendOpen(false)
            props.setQuoteAwaitingSave(null)
          }}
          onSendLetter={(_caseId) => {
            props.setCaseDocPanel('documents')
            props.setPrecedentPicker({ kind: 'letter' })
          }}
          onSendEmail={(_caseId) => {
            props.setCaseDocPanel('documents')
            props.setPrecedentPicker({
              kind: 'email',
              preferPrecedentReference: QUOTE_EMAIL_PRECEDENT_REFERENCE,
              attachmentFileId: props.quoteAwaitingSave?.fileId,
            })
          }}
          onSent={() => {
            props.quoteWasCreatedRef.current = true
            onRefresh()
          }}
        />
      ) : null}

      {props.formSendOpen && caseId ? (
        <SendPortalFormModal
          token={token}
          caseId={caseId}
          open={props.formSendOpen}
          onClose={() => props.setFormSendOpen(false)}
          onSent={() => onRefresh()}
        />
      ) : null}

      {props.precedentPicker ? (
        <CasePrecedentPickerModal
          caseDetail={caseDetail}
          precedentPickerSubTypeGroups={props.precedentPickerSubTypeGroups}
          precedentPickerExpandedSubTypes={props.precedentPickerExpandedSubTypes}
          precedentCategoriesBySubType={props.precedentCategoriesBySubType}
          togglePrecedentPickerSubTypeExpanded={props.togglePrecedentPickerSubTypeExpanded}
          selectPrecedentPickerNav={props.selectPrecedentPickerNav}
          precedentPickerSubTypeId={props.precedentPickerSubTypeId}
          precedentPickerCategoryId={props.precedentPickerCategoryId}
          precedentSearch={props.precedentSearch}
          setPrecedentSearch={props.setPrecedentSearch}
          precedentChosenId={props.precedentChosenId}
          setPrecedentChosenId={props.setPrecedentChosenId}
          filteredPrecedentChoices={props.filteredPrecedentChoices}
          onClose={() => props.setPrecedentPicker(null)}
          onContinue={() => props.confirmPrecedentPicker()}
        />
      ) : null}

      {props.contactPickModal ? (
        <CaseContactPickModal
          contactPickModal={props.contactPickModal}
          currentUser={currentUser}
          contactPickErr={props.contactPickErr}
          contactPickMatterOptions={props.contactPickMatterOptions}
          pickMatterCcId={props.pickMatterCcId}
          setPickMatterCcId={props.setPickMatterCcId}
          contactPickMatterOpen={props.contactPickMatterOpen}
          setContactPickMatterOpen={props.setContactPickMatterOpen}
          token={token}
          pickSelectedContact={props.pickSelectedContact}
          setPickSelectedContact={props.setPickSelectedContact}
          busy={busy}
          pickLinkType={props.pickLinkType}
          pickLinkGlobal={props.pickLinkGlobal}
          setPickLinkGlobal={props.setPickLinkGlobal}
          contactPickTypeOptions={props.contactPickTypeOptions}
          setPickLinkType={props.setPickLinkType}
          setContactPickErr={props.setContactPickErr}
          pickLawyerClientIds={props.pickLawyerClientIds}
          setPickLawyerClientIds={props.setPickLawyerClientIds}
          contactPickTypeOpen={props.contactPickTypeOpen}
          setContactPickTypeOpen={props.setContactPickTypeOpen}
          lawyerLinkableMatterContacts={props.lawyerLinkableMatterContacts}
          matterTypeOptions={props.matterTypeOptions}
          onClose={() => {
            props.setContactPickModal(null)
            props.resetContactPickForm()
          }}
          onContinue={() => void props.confirmContactPick()}
        />
      ) : null}

      {props.textPrompt ? (
        <TextPromptModal
          title={props.textPrompt.title}
          hint={props.textPrompt.hint}
          initial={props.textPrompt.initial}
          confirmLabel={props.textPrompt.confirmLabel}
          busy={busy}
          onConfirm={props.textPrompt.onConfirm}
          onCancel={() => props.setTextPrompt(null)}
        />
      ) : null}

      {props.manageAccessOpen && caseId && caseDetail ? (
        <ManageCaseAccessModal
          token={token}
          caseId={caseId}
          users={users}
          feeEarnerUserId={caseDetail.fee_earner_user_id}
          lockMode={caseDetail.lock_mode}
          canSetLockMode={Boolean(
            currentUser?.admin_console_access ||
              currentUser?.role === 'admin' ||
              (caseDetail.fee_earner_user_id && currentUser?.id === caseDetail.fee_earner_user_id),
          )}
          onClose={() => props.setManageAccessOpen(false)}
          onSaved={() => {
            onRefresh()
            onCaseListInvalidate?.()
          }}
        />
      ) : null}
    </>
  )
}
