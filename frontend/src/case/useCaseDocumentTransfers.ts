import { useCallback, useEffect, useRef } from 'react'
import type { FileSummary } from '../types'
import type { UseCaseDocFileHandlersArgs } from './useCaseDocFileHandlers'
import { downloadCaseExportZipBlob, downloadCaseFilesSequential, downloadCaseFolderZipBlob, uploadFilesToCaseFolder } from './documentTransferOps'
import { documentErrorMessage, DocumentRequestError } from './documentRequests'
import { notifyPortalFilesAdded } from './caseDocFileOps'
import { isPortalSharedFolder, portalContactsForFolder, portalSharedFolderUploadNotifyMessage } from './portalFolderAccess'

type Args = Pick<UseCaseDocFileHandlersArgs, 'caseId' | 'caseDetail' | 'token' | 'docFolder' | 'portalEnabled' | 'portalFolderGrants' | 'askConfirm' | 'pushNotification' | 'onRefresh' | 'setBusy' | 'setActionErr' | 'setDocMenu'>

export function useCaseDocumentTransfers({ caseId, caseDetail, token, docFolder, portalEnabled, portalFolderGrants, askConfirm, pushNotification, onRefresh, setBusy, setActionErr, setDocMenu }: Args) {
  // A ref closes the gap before React renders disabled controls, including repeated drops.
  const inFlight = useRef(false)
  const scope = useRef('')
  scope.current = `${caseId}/${docFolder}`
  const mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])

  const runTransfer = useCallback(async (work: (current: () => boolean) => Promise<void>) => {
    if (inFlight.current || !caseId) return
    inFlight.current = true
    const startedIn = scope.current
    const current = () => mounted.current && scope.current === startedIn
    setBusy(true)
    setActionErr(null)
    try { await work(current) }
    catch (error) { if (current()) setActionErr(documentErrorMessage(error, 'The document operation failed. Please try again.')) }
    finally { inFlight.current = false; if (mounted.current) setBusy(false) }
  }, [caseId, setBusy, setActionErr])

  const retryTransfer = useCallback(async (operation: () => Promise<void>, current: () => boolean, title: string, progress?: { completed: number }) => {
    while (current()) {
      try { await operation(); return true }
      catch (error) {
        if (!current()) return false
        // A lost upload response is ambiguous. Never offer to replay it as though it failed.
        if (!(error instanceof DocumentRequestError) || !error.retryable) throw error
        const message = documentErrorMessage(error, 'The document operation failed.')
        const retry = await askConfirm({ title, message: `${message}${progress ? ` ${progress.completed} file(s) completed; retry resumes with the remaining files.` : ''}`, confirmLabel: 'Retry', cancelLabel: 'Cancel' })
        if (!retry) return false
      }
    }
    return false
  }, [askConfirm])

  const uploadFilesToCurrentFolder = useCallback(async (incomingFiles: File[]) => {
    if (!caseId || incomingFiles.length === 0) return
    await runTransfer(async (current) => {
      const progress = { completed: 0 }
      let notify = false
      if (portalEnabled && isPortalSharedFolder(docFolder, portalFolderGrants)) {
        notify = await askConfirm({ title: 'Notify portal contacts?', message: portalSharedFolderUploadNotifyMessage(portalContactsForFolder(docFolder, portalFolderGrants), incomingFiles.length), confirmLabel: 'Send e-mail', cancelLabel: 'Skip' })
      }
      if (!current()) return
      let completed = false
      let refreshAllowed = true
      try {
        completed = await retryTransfer(() => uploadFilesToCaseFolder(caseId, token, docFolder, incomingFiles, progress, current), current, 'Upload interrupted', progress)
      } catch (error) {
        // Refresh uses the general API client, whose 401 handling reloads the page.
        // Keep this view intact so session recovery does not erase local state.
        refreshAllowed = !(error instanceof DocumentRequestError && error.status === 401)
        throw new Error(`${progress.completed} of ${incomingFiles.length} files uploaded. ${documentErrorMessage(error, 'Upload failed.')} Files already uploaded will remain in the list.`)
      } finally {
        // Also reconcile an unknown outcome; a server may have accepted the last file.
        if (current() && refreshAllowed) onRefresh()
      }
      if (!completed || !current() || !notify) return
      try {
        const out = await notifyPortalFilesAdded(caseId, token, docFolder, incomingFiles.map((f) => f.name))
        if (!current()) return
        if (out.alerts_skipped_reason) pushNotification(out.alerts_skipped_reason)
        else if (out.contacts_notified > 0) pushNotification(out.contacts_notified === 1 ? 'Portal contact notified by e-mail.' : `${out.contacts_notified} portal contacts notified by e-mail.`)
      } catch {
        if (current()) setActionErr('The files were uploaded, but the portal e-mail notification could not be confirmed. Do not upload the files again; check with the portal contacts before sending another notification.')
      }
    })
  }, [caseId, token, docFolder, portalEnabled, portalFolderGrants, askConfirm, runTransfer, retryTransfer, onRefresh, pushNotification, setActionErr])

  const downloadCaseFiles = useCallback(async (files: FileSummary[]) => {
    if (!caseId || !files.length) return
    const progress = { completed: 0 }
    await runTransfer(async (current) => { await retryTransfer(() => downloadCaseFilesSequential(caseId, files, token, 350, progress, current), current, 'Download interrupted', progress) })
  }, [caseId, token, runTransfer, retryTransfer])

  const downloadCaseExportZip = useCallback(async () => {
    if (!caseId || !caseDetail) return
    await runTransfer(async (current) => { await retryTransfer(() => downloadCaseExportZipBlob(caseId, caseDetail.case_number, token), current, 'Export interrupted') })
  }, [caseId, caseDetail, token, runTransfer, retryTransfer])

  const downloadCaseFolderZip = useCallback(async (folderPath: string) => {
    if (!caseId) return
    setDocMenu(null)
    await runTransfer(async (current) => { await retryTransfer(() => downloadCaseFolderZipBlob(caseId, folderPath, token), current, 'Download interrupted') })
  }, [caseId, token, setDocMenu, runTransfer, retryTransfer])

  return { uploadFilesToCurrentFolder, downloadCaseFiles, downloadCaseExportZip, downloadCaseFolderZip }
}
