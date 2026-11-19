import type { FileSummary } from '../types'
import { decodeFolderPathSegment, splitFolderPath } from './folderPathCodec'
import { documentRequest } from './documentRequests'

export function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 120_000)
}

/** Open a blob in a new tab. Returns false if the browser blocked the popup (caller may download instead). */
export function openBlobInNewTab(blob: Blob): boolean {
  const url = URL.createObjectURL(blob)
  const win = window.open(url, '_blank', 'noopener,noreferrer')
  if (!win) {
    URL.revokeObjectURL(url)
    return false
  }
  window.setTimeout(() => URL.revokeObjectURL(url), 120_000)
  return true
}

export async function downloadCaseFileBlob(
  caseId: string,
  f: FileSummary,
  token: string,
): Promise<void> {
  const blob = await documentRequest(`/cases/${caseId}/files/${f.id}`, token, (res) => res.blob())
  const typed = f.mime_type ? new Blob([blob], { type: f.mime_type }) : blob
  const safeName = f.original_filename.replace(/[/\\]/g, '_').replace(/^\.+/, '') || 'download'
  triggerBlobDownload(typed, safeName)
}

export async function downloadCaseFilesSequential(
  caseId: string,
  targets: FileSummary[],
  token: string,
  gapMs = 350,
  progress: { completed: number } = { completed: 0 },
  current: () => boolean = () => true,
): Promise<void> {
  for (let i = progress.completed; i < targets.length && current(); i++) {
    await downloadCaseFileBlob(caseId, targets[i], token)
    progress.completed = i + 1
    if (i < targets.length - 1) {
      await new Promise((r) => window.setTimeout(r, gapMs))
    }
  }
}

export async function downloadCaseExportZipBlob(caseId: string, caseNumber: string, token: string): Promise<void> {
  const blob = await documentRequest(`/cases/${caseId}/files/export-zip`, token, (res) => res.blob())
  const safeBase = caseNumber.replace(/[/\\]/g, '_').replace(/^\.+/, '').trim() || 'matter'
  triggerBlobDownload(new Blob([blob], { type: 'application/zip' }), `${safeBase}-export.zip`)
}

export async function downloadCaseFolderZipBlob(caseId: string, folderPath: string, token: string): Promise<void> {
  const q = new URLSearchParams({ folder_path: folderPath })
  const blob = await documentRequest(`/cases/${caseId}/files/folders/download-zip?${q}`, token, (res) => res.blob())
  const parts = splitFolderPath(folderPath)
  const safeBase = decodeFolderPathSegment(parts[parts.length - 1] ?? '').replace(/[/\\]/g, '_').replace(/^\.+/, '').trim() || 'folder'
  triggerBlobDownload(new Blob([blob], { type: 'application/zip' }), `${safeBase}.zip`)
}

/** The caller owns progress so an explicit retry never repeats acknowledged files. */
export async function uploadFilesToCaseFolder(
  caseId: string, token: string, folder: string, incomingFiles: File[],
  progress: { completed: number } = { completed: 0 },
  current: () => boolean = () => true,
): Promise<void> {
  while (progress.completed < incomingFiles.length && current()) {
    const form = new FormData()
    form.append('upload', incomingFiles[progress.completed])
    form.append('folder', folder)
    await documentRequest(`/cases/${caseId}/files`, token, async (res) => { await res.text() }, { method: 'POST', body: form })
    progress.completed++
  }
}

export async function openCaseFileBlobInTab(
  caseId: string,
  file: FileSummary,
  token: string,
): Promise<void> {
  const blob = await documentRequest(`/cases/${caseId}/files/${file.id}`, token, (res) => res.blob())
  const typed = file.mime_type ? new Blob([blob], { type: file.mime_type }) : blob
  if (openBlobInNewTab(typed)) return
  // Popup blocked — still deliver the file via download so Open is never a no-op.
  const safeName = file.original_filename.replace(/[/\\]/g, '_').replace(/^\.+/, '') || 'document.pdf'
  triggerBlobDownload(typed, safeName)
}
