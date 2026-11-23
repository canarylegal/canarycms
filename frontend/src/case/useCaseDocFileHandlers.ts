import { uploadScanLabel, uploadIsUnavailable } from '../uploadScanStatus'
import { useCallback, useRef, useEffect, type Dispatch, type SetStateAction } from 'react'
import { apiFetch } from '../api'
import { openOnlyOfficeCaseEditor } from '../onlyofficeEditorWindow'
import type {
  CaseOut,
  CasePortalFolderAccessGrantOut,
  FileSummary,
  UserPublic,
} from '../types'
import { composeMatterEmail } from './caseComposeEmail'
import {
  formatFileOpError,
  isCommentFile,
  loadEmlPreviewData,
  openCaseFileBlobInTab,
  downloadEmlViaToken,
  openEmlViaDesktopToken,
  tryOpenEmlInOutlookWeb,
} from './caseDocFileOps'
import type { EmlPreviewData } from './emlPreview'
import { joinFolderPath } from './folderPathCodec'
import { isEmlLikeFileSummary, isOfficeLikeFile } from './officeFiles'
import { useCaseDocumentTransfers } from './useCaseDocumentTransfers'

export type CaseDocTextPrompt = {
  title: string
  hint?: string
  initial: string
  confirmLabel: string
  onConfirm: (value: string) => void
}

export type UseCaseDocFileHandlersArgs = {
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
  setCommentVersion: Dispatch<SetStateAction<number | null>>
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
  setCommentVersion,
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
  useEffect(() => {
    if (!files.some((f) => f.scan_state === 'pending' || (f.scan_state === 'error' && (f.scan_attempts ?? 0) < 3))) return
    const timer = window.setInterval(onRefresh, 3000)
    return () => window.clearInterval(timer)
  }, [files, onRefresh])
  const previewEmlFileRef = useRef<(f: FileSummary) => void>(() => {})
  const openCaseFileRef = useRef<(f: FileSummary) => void>(() => {})

  const { uploadFilesToCurrentFolder, downloadCaseFiles, downloadCaseExportZip, downloadCaseFolderZip } = useCaseDocumentTransfers({
    caseId, caseDetail, token, docFolder, portalEnabled, portalFolderGrants, askConfirm,
    pushNotification, onRefresh, setBusy, setActionErr, setDocMenu,
  })

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
      if (uploadIsUnavailable(f)) { setActionErr(uploadScanLabel(f)); return }
      if (!caseId) return
      setBusy(true)
      setActionErr(null)
      try {
        const comment = await apiFetch<{ text: string; version: number }>(`/cases/${caseId}/files/${f.id}/comment`, { token })
        setCommentText(comment.text)
        setCommentVersion(comment.version)
        setCommentEditFileId(f.id)
        setCommentErr(null)
        setCommentOpen(true)
      } catch (e: any) {
        setActionErr(formatFileOpError(e, 'Could not load comment'))
      } finally {
        setBusy(false)
      }
    },
    [
      caseId,
      setBusy,
      setActionErr,
      token,
      setCommentVersion,
      setCommentText,
      setCommentEditFileId,
      setCommentErr,
      setCommentOpen,
    ],
  )

  const previewEmlFile = useCallback(
    async (f: FileSummary) => {
      if (uploadIsUnavailable(f)) { setActionErr(uploadScanLabel(f)); return }
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
      setActionErr,
      setEmlPreviewOpen,
      setEmlPreviewFile,
      setEmlPreviewData,
      setEmlPreviewErr,
      setEmlPreviewBusy,
      token,
    ],
  )

  const openEmlInFlightRef = useRef<string | null>(null)
  const openEmlWithMailApp = useCallback(
    async (f: FileSummary) => {
      if (uploadIsUnavailable(f)) { setActionErr(uploadScanLabel(f)); return }
      if (!caseId) return
      if (openEmlInFlightRef.current === f.id) return
      openEmlInFlightRef.current = f.id
      setBusy(true)
      setActionErr(null)
      try {
        const how = await openEmlViaDesktopToken(caseId, f.id, token, {
          filename: f.original_filename,
        })
        // Success is silent — the message window is the feedback.
        if (how === 'needs_addon') {
          pushNotification(
            'Thunderbird did not pick up the e-mail. Confirm “Open Link” / canary-eml if prompted, or open Thunderbird and sign in via the Canary toolbar, then try again.',
          )
        } else if (how === 'launching') {
          pushNotification(
            'Starting Thunderbird — confirm “Open Link” if your browser prompts for canary-eml.',
          )
        }
      } catch (e: unknown) {
        setActionErr(formatFileOpError(e, 'Could not open e-mail in Thunderbird'))
      } finally {
        if (openEmlInFlightRef.current === f.id) openEmlInFlightRef.current = null
        setBusy(false)
      }
    },
    [caseId, setBusy, setActionErr, token, pushNotification],
  )

  const downloadEmlFile = useCallback(
    async (f: FileSummary) => {
      if (uploadIsUnavailable(f)) { setActionErr(uploadScanLabel(f)); return }
      if (!caseId) return
      setBusy(true)
      setActionErr(null)
      try {
        await downloadEmlViaToken(caseId, f.id, token, { filename: f.original_filename })
      } catch (e: unknown) {
        setActionErr(formatFileOpError(e, 'Could not download e-mail'))
      } finally {
        setBusy(false)
      }
    },
    [caseId, setBusy, setActionErr, token],
  )

  const openCaseFile = useCallback(
    async (f: FileSummary) => {
      if (uploadIsUnavailable(f)) { setActionErr(uploadScanLabel(f)); return }
      if (!caseId) return
      const file = files.find((x) => x.id === f.id) ?? f
      if (isCommentFile(file)) {
        void openCommentForEdit(file)
        return
      }
      if (isOfficeLikeFile(file)) {
        const win = openOnlyOfficeCaseEditor(caseId, file.id)
        if (win) {
          try {
            win.focus()
          } catch {
            /* ignore */
          }
          return
        }
        // Popup blocked — fall back to blob preview / download so Open is never silent.
        setBusy(true)
        setActionErr(null)
        try {
          await openCaseFileBlobInTab(caseId, file, token)
          pushNotification('Pop-ups are blocked, so the file was opened here instead of the editor.')
        } catch (e: unknown) {
          setActionErr(formatFileOpError(e, 'Open failed — allow pop-ups for this site, then try again.'))
        } finally {
          setBusy(false)
        }
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

        /* Desktop / default: show in-app preview. OS mail-app handoff often just downloads the .eml
         * (especially on Linux); use "Open with mail app" in the preview modal for that path. */
        await previewEmlFile(file)
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

  return {
    previewEmlFileRef,
    openCaseFileRef,
    uploadFilesToCurrentFolder,
    createFolderAtCurrentPath,
    composeOfficeFile,
    composeEmailMailto,
    previewEmlFile,
    openCaseFile,
    openEmlWithMailApp,
    downloadEmlFile,
    downloadCaseFiles,
    downloadCaseExportZip,
    downloadCaseFolderZip,
  }
}
