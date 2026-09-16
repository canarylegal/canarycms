import { useCallback, useRef, type Dispatch, type SetStateAction } from 'react'
import { apiFetch } from '../api'
import { openOnlyOfficeCaseEditor } from '../onlyofficeEditorWindow'
import type {
  CaseOut,
  CasePortalFolderAccessGrantOut,
  FileSummary,
  UserPublic,
} from '../types'
import { composeMatterEmail } from './caseComposeEmail'
import { fetchCaseFileResponse } from './caseDetailHelpers'
import {
  downloadCaseExportZipBlob,
  downloadCaseFilesSequential,
  downloadCaseFolderZipBlob,
  formatFileOpError,
  isCommentFile,
  loadEmlPreviewData,
  notifyPortalFilesAdded,
  openCaseFileBlobInTab,
  openEmlViaDesktopToken,
  tryOpenEmlInOutlookWeb,
  uploadFilesToCaseFolder,
} from './caseDocFileOps'
import type { EmlPreviewData } from './emlPreview'
import { joinFolderPath } from './folderPathCodec'
import { isEmlLikeFileSummary, isOfficeLikeFile } from './officeFiles'
import {
  isPortalSharedFolder,
  portalContactsForFolder,
  portalSharedFolderUploadNotifyMessage,
} from './portalFolderAccess'

export type CaseDocTextPrompt = {
  title: string
  hint?: string
  initial: string
  confirmLabel: string
  onConfirm: (value: string) => void
}

type UseCaseDocFileHandlersArgs = {
  caseId: string | undefined
  caseDetail: CaseOut | null
  token: string
  docFolder: string
  files: FileSummary[]
  portalEnabled: boolean
  portalFolderGrants: CasePortalFolderAccessGrantOut[]
  currentUser: UserPublic | null | undefined
  askConfirm: (opts: {
    title: string
    message: string
    confirmLabel?: string
    cancelLabel?: string
  }) => Promise<boolean>
  pushNotification: (message: string) => void
  onRefresh: () => void
  setBusy: Dispatch<SetStateAction<boolean>>
  setActionErr: Dispatch<SetStateAction<string | null>>
  setTextPrompt: Dispatch<SetStateAction<CaseDocTextPrompt | null>>
  setCommentText: Dispatch<SetStateAction<string>>
  setCommentEditFileId: Dispatch<SetStateAction<string | null>>
  setCommentErr: Dispatch<SetStateAction<string | null>>
  setCommentOpen: Dispatch<SetStateAction<boolean>>
  setEmlPreviewOpen: Dispatch<SetStateAction<boolean>>
  setEmlPreviewFile: Dispatch<SetStateAction<FileSummary | null>>
  setEmlPreviewData: Dispatch<SetStateAction<EmlPreviewData | null>>
  setEmlPreviewErr: Dispatch<SetStateAction<string | null>>
  setEmlPreviewBusy: Dispatch<SetStateAction<boolean>>
  setDocMenu: (menu: null) => void
}

export function useCaseDocFileHandlers({
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
}: UseCaseDocFileHandlersArgs) {
  const previewEmlFileRef = useRef<(f: FileSummary) => void>(() => {})
  const openCaseFileRef = useRef<(f: FileSummary) => void>(() => {})

  const uploadFilesToCurrentFolder = useCallback(
    async (incomingFiles: File[]) => {
      if (incomingFiles.length === 0 || !caseId) return
      let notifyPortalContacts = false
      const sharedContacts = portalEnabled ? portalContactsForFolder(docFolder, portalFolderGrants) : []
      if (portalEnabled && isPortalSharedFolder(docFolder, portalFolderGrants)) {
        const choice = await askConfirm({
          title: 'Notify portal contacts?',
          message: portalSharedFolderUploadNotifyMessage(sharedContacts, incomingFiles.length),
          confirmLabel: 'Send e-mail',
          cancelLabel: 'Skip',
        })
        notifyPortalContacts = choice
      }
      setBusy(true)
      setActionErr(null)
      try {
        await uploadFilesToCaseFolder(caseId, token, docFolder, incomingFiles)
        if (notifyPortalContacts) {
          const notifyOut = await notifyPortalFilesAdded(
            caseId,
            token,
            docFolder,
            incomingFiles.map((f) => f.name),
          )
          if (notifyOut.alerts_skipped_reason) {
            pushNotification(notifyOut.alerts_skipped_reason)
          } else if (notifyOut.contacts_notified > 0) {
            pushNotification(
              notifyOut.contacts_notified === 1
                ? 'Portal contact notified by e-mail.'
                : `${notifyOut.contacts_notified} portal contacts notified by e-mail.`,
            )
          }
        }
        onRefresh()
      } catch (err: any) {
        setActionErr(err?.message ?? 'Upload failed')
      } finally {
        setBusy(false)
      }
    },
    [
      caseId,
      portalEnabled,
      docFolder,
      portalFolderGrants,
      askConfirm,
      setBusy,
      setActionErr,
      token,
      pushNotification,
      onRefresh,
    ],
  )

  const createFolderAtCurrentPath = useCallback(() => {
    setTextPrompt({
      title: 'New folder',
      hint: 'Enter a folder name.',
      initial: '',
      confirmLabel: 'Create',
      onConfirm: (name) => {
        const trimmed = name.trim()
        setTextPrompt(null)
        if (!trimmed) return
        const folder_path = joinFolderPath(docFolder, trimmed)
        if (!folder_path) return
        setBusy(true)
        setActionErr(null)
        apiFetch(`/cases/${caseId}/files/folders`, { token, method: 'POST', json: { folder_path } })
          .then(() => onRefresh())
          .catch((e: any) => setActionErr(e?.message ?? 'Failed to create folder'))
          .finally(() => setBusy(false))
      },
    })
  }, [setTextPrompt, docFolder, setBusy, setActionErr, caseId, token, onRefresh])

  const composeOfficeFile = useCallback(
    async (
      originalFilename: string,
      precedentId: string | null,
      caseContactId?: string | null,
      globalContactId?: string | null,
      precedentMergeAllClients?: boolean,
      composeOfficeRole?: 'letter' | 'document' | null,
    ) => {
      if (!caseId) return
      setBusy(true)
      setActionErr(null)
      try {
        const res = await apiFetch<{ id: string }>(`/cases/${caseId}/files/compose-office`, {
          token,
          json: {
            original_filename: originalFilename,
            folder: docFolder,
            precedent_id: precedentId,
            case_contact_id: caseContactId ?? null,
            global_contact_id: globalContactId ?? null,
            precedent_merge_all_clients: Boolean(precedentMergeAllClients),
            compose_office_role: composeOfficeRole ?? null,
          },
        })
        openOnlyOfficeCaseEditor(caseId, res.id)
      } catch (e: any) {
        setActionErr(e?.message ?? 'Could not create document')
      } finally {
        setBusy(false)
      }
    },
    [caseId, setBusy, setActionErr, token, docFolder],
  )

  const composeEmailMailto = useCallback(
    async (
      precedentId: string | null,
      caseContactId: string | null,
      globalContactId: string | null,
      precedentMergeAllClients: boolean,
      composeOfficeRole?: 'letter' | 'document' | null,
      attachmentFileIds: string[] = [],
    ) => {
      if (!caseId) return
      setBusy(true)
      setActionErr(null)
      try {
        await composeMatterEmail({
          caseId,
          token,
          docFolder,
          currentUser,
          precedentId,
          caseContactId,
          globalContactId,
          precedentMergeAllClients,
          composeOfficeRole,
          attachmentFileIds,
          pushNotification,
          setActionErr,
        })
      } catch (e: unknown) {
        const err = e as { message?: string }
        setActionErr(err?.message ?? 'Could not prepare e-mail')
      } finally {
        setBusy(false)
      }
    },
    [caseId, setBusy, setActionErr, token, docFolder, currentUser, pushNotification],
  )

  const openCommentForEdit = useCallback(
    async (f: FileSummary) => {
      if (!caseId) return
      setBusy(true)
      setActionErr(null)
      try {
        const res = await fetchCaseFileResponse(caseId, f.id, token)
        if (res.status === 401) {
          localStorage.removeItem('token')
          window.location.reload()
          return
        }
        if (!res.ok) throw new Error((await res.text()) || res.statusText)
        const text = await res.text()
        setCommentText(text)
        setCommentEditFileId(f.id)
        setCommentErr(null)
        setCommentOpen(true)
      } catch (e: any) {
        setActionErr(e?.message ?? 'Could not load comment')
      } finally {
        setBusy(false)
      }
    },
    [
      caseId,
      setBusy,
      setActionErr,
      token,
      setCommentText,
      setCommentEditFileId,
      setCommentErr,
      setCommentOpen,
    ],
  )

  const previewEmlFile = useCallback(
    async (f: FileSummary) => {
      if (!caseId) return
      setEmlPreviewOpen(true)
      setEmlPreviewFile(f)
      setEmlPreviewData(null)
      setEmlPreviewErr(null)
      setEmlPreviewBusy(true)
      try {
        const parsed = await loadEmlPreviewData(caseId, f.id, token)
        if (!parsed) return
        setEmlPreviewData(parsed)
      } catch (e: unknown) {
        setEmlPreviewErr(
          e instanceof Error && e.message ? e.message : formatFileOpError(e, 'Could not load preview'),
        )
      } finally {
        setEmlPreviewBusy(false)
      }
    },
    [
      caseId,
      setEmlPreviewOpen,
      setEmlPreviewFile,
      setEmlPreviewData,
      setEmlPreviewErr,
      setEmlPreviewBusy,
      token,
    ],
  )

  const openCaseFile = useCallback(
    async (f: FileSummary) => {
      if (!caseId) return
      const file = files.find((x) => x.id === f.id) ?? f
      if (isCommentFile(file)) {
        void openCommentForEdit(file)
        return
      }
      if (isOfficeLikeFile(file)) {
        openOnlyOfficeCaseEditor(caseId, file.id)
        return
      }

      if (isEmlLikeFileSummary(file)) {
        const pref = currentUser?.email_launch_preference ?? 'desktop'
        if (pref === 'outlook_web') {
          setBusy(true)
          setActionErr(null)
          try {
            const result = await tryOpenEmlInOutlookWeb({
              caseId,
              file,
              token,
              owaBase: currentUser?.email_outlook_web_url ?? null,
              userEmail: currentUser?.email?.trim() || null,
              onPopupBlocked: () =>
                setActionErr(
                  'Your browser blocked the Outlook window. Allow pop-ups for this site, then try again.',
                ),
            })
            if (result === 'opened') return
            await previewEmlFile(file)
            pushNotification(
              'Showing the Canary copy in preview. This filing has no live Outlook message link — file from Outlook read mode, or open the original from your Sent or Inbox.',
            )
          } catch (e: unknown) {
            setActionErr(formatFileOpError(e, 'Open failed'))
          } finally {
            setBusy(false)
          }
          return
        }

        /* Desktop / default: hand off to the OS mail app via a one-shot download (no about:blank tab —
         * attachment responses do not navigate the tab, which left a stray blank page). */
        setBusy(true)
        setActionErr(null)
        try {
          await openEmlViaDesktopToken(caseId, file.id, token)
        } catch (e: unknown) {
          setActionErr(formatFileOpError(e, 'Could not open e-mail'))
        } finally {
          setBusy(false)
        }
        return
      }

      setBusy(true)
      setActionErr(null)
      try {
        await openCaseFileBlobInTab(caseId, file, token)
      } catch (e: unknown) {
        setActionErr(formatFileOpError(e, 'Open failed'))
      } finally {
        setBusy(false)
      }
    },
    [
      caseId,
      files,
      openCommentForEdit,
      currentUser,
      setBusy,
      setActionErr,
      token,
      previewEmlFile,
      pushNotification,
    ],
  )

  previewEmlFileRef.current = previewEmlFile
  openCaseFileRef.current = openCaseFile

  const downloadCaseFiles = useCallback(
    async (targets: FileSummary[]) => {
      if (!caseId || targets.length === 0) return
      setBusy(true)
      setActionErr(null)
      try {
        await downloadCaseFilesSequential(caseId, targets, token)
      } catch (e: unknown) {
        setActionErr(formatFileOpError(e, 'Download failed'))
      } finally {
        setBusy(false)
      }
    },
    [caseId, setBusy, setActionErr, token],
  )

  const downloadCaseExportZip = useCallback(async () => {
    if (!caseId || !caseDetail) return
    setBusy(true)
    setActionErr(null)
    try {
      await downloadCaseExportZipBlob(caseId, caseDetail.case_number, token)
    } catch (e: unknown) {
      setActionErr(formatFileOpError(e, 'Export failed'))
    } finally {
      setBusy(false)
    }
  }, [caseId, caseDetail, setBusy, setActionErr, token])

  const downloadCaseFolderZip = useCallback(
    async (folderPath: string) => {
      if (!caseId) return
      setBusy(true)
      setActionErr(null)
      setDocMenu(null)
      try {
        await downloadCaseFolderZipBlob(caseId, folderPath, token)
      } catch (e: unknown) {
        setActionErr(formatFileOpError(e, 'Download failed'))
      } finally {
        setBusy(false)
      }
    },
    [caseId, setBusy, setActionErr, setDocMenu, token],
  )

  return {
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
  }
}
