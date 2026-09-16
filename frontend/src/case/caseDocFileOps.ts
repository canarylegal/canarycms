import { apiFetch, apiUrl, browserAbsoluteApiUrl } from '../api'
import {
  appendOutlookWebAuthHintsForNav,
  OWA_MESSAGE_WINDOW_FEATURES,
  openOutlookWebAppFromGraphWebLink,
  OWA_MAIL_WINDOW_NAME,
} from '../emailClient'
import {
  buildOutlookWebReadItemUrl,
  isLikelyExchangeRestItemId,
  isUsableOutlookMessageWebLink,
  normalizeOutlookWebReadLink,
} from '../emailLauncher'
import type { CasePortalNotifyFilesOut, FileSummary } from '../types'
import {
  CASE_FILE_FETCH_MS,
  caseAuthHeaders,
  fetchCaseFileResponse,
  fetchEmlTextForPreview,
  fetchTimedOutMessage,
} from './caseDetailHelpers'
import { parseEmlForPreview, type EmlPreviewData } from './emlPreview'
import { decodeFolderPathSegment, splitFolderPath } from './folderPathCodec'

export function isCommentFile(f: FileSummary): boolean {
  return (
    (f.mime_type || '').toLowerCase().startsWith('text/plain') ||
    (f.original_filename || '').toLowerCase().endsWith('.txt')
  )
}

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

export function openBlobInNewTab(blob: Blob): void {
  const url = URL.createObjectURL(blob)
  window.open(url, '_blank', 'noopener,noreferrer')
  window.setTimeout(() => URL.revokeObjectURL(url), 120_000)
}

export async function downloadCaseFileBlob(
  caseId: string,
  f: FileSummary,
  token: string,
): Promise<void> {
  const res = await fetchCaseFileResponse(caseId, f.id, token)
  if (res.status === 401) {
    localStorage.removeItem('token')
    window.location.reload()
    return
  }
  if (!res.ok) throw new Error((await res.text()) || res.statusText)
  const blob = await res.blob()
  const typed = f.mime_type ? new Blob([blob], { type: f.mime_type }) : blob
  const safeName = f.original_filename.replace(/[/\\]/g, '_').replace(/^\.+/, '') || 'download'
  triggerBlobDownload(typed, safeName)
}

export async function downloadCaseFilesSequential(
  caseId: string,
  targets: FileSummary[],
  token: string,
  gapMs = 350,
): Promise<void> {
  for (let i = 0; i < targets.length; i++) {
    await downloadCaseFileBlob(caseId, targets[i], token)
    if (i < targets.length - 1) {
      await new Promise((r) => window.setTimeout(r, gapMs))
    }
  }
}

async function downloadZipResponse(res: Response, downloadName: string): Promise<void> {
  if (res.status === 401) {
    localStorage.removeItem('token')
    window.location.reload()
    return
  }
  if (!res.ok) throw new Error((await res.text()) || res.statusText)
  const blob = await res.blob()
  const typed = new Blob([blob], { type: 'application/zip' })
  triggerBlobDownload(typed, downloadName)
}

export async function downloadCaseExportZipBlob(
  caseId: string,
  caseNumber: string,
  token: string,
): Promise<void> {
  const ctrl = new AbortController()
  const tid = window.setTimeout(() => ctrl.abort(), CASE_FILE_FETCH_MS)
  try {
    const res = await fetch(apiUrl(`/cases/${caseId}/files/export-zip`), {
      headers: caseAuthHeaders(token),
      signal: ctrl.signal,
    })
    const safeBase = caseNumber.replace(/[/\\]/g, '_').replace(/^\.+/, '').trim() || 'matter'
    await downloadZipResponse(res, `${safeBase}-export.zip`)
  } finally {
    clearTimeout(tid)
  }
}

export async function downloadCaseFolderZipBlob(
  caseId: string,
  folderPath: string,
  token: string,
): Promise<void> {
  const ctrl = new AbortController()
  const tid = window.setTimeout(() => ctrl.abort(), CASE_FILE_FETCH_MS)
  try {
    const q = new URLSearchParams({ folder_path: folderPath })
    const res = await fetch(apiUrl(`/cases/${caseId}/files/folders/download-zip?${q}`), {
      headers: caseAuthHeaders(token),
      signal: ctrl.signal,
    })
    const parts = splitFolderPath(folderPath)
    const leaf = parts[parts.length - 1] ?? ''
    const safeBase =
      decodeFolderPathSegment(leaf).replace(/[/\\]/g, '_').replace(/^\.+/, '').trim() || 'folder'
    await downloadZipResponse(res, `${safeBase}.zip`)
  } finally {
    clearTimeout(tid)
  }
}

export async function uploadFilesToCaseFolder(
  caseId: string,
  token: string,
  folder: string,
  incomingFiles: File[],
): Promise<void> {
  for (const f of incomingFiles) {
    const form = new FormData()
    form.append('upload', f)
    form.append('folder', folder)
    await fetch(apiUrl(`/cases/${caseId}/files`), {
      method: 'POST',
      headers: caseAuthHeaders(token),
      body: form,
    }).then(async (r) => {
      if (r.status === 401) {
        localStorage.removeItem('token')
        window.location.reload()
        return
      }
      if (!r.ok) throw new Error((await r.text()) || r.statusText)
    })
  }
}

export async function notifyPortalFilesAdded(
  caseId: string,
  token: string,
  folderPath: string,
  filenames: string[],
): Promise<CasePortalNotifyFilesOut> {
  return apiFetch<CasePortalNotifyFilesOut>(`/cases/${caseId}/portal/notify-files-added`, {
    token,
    method: 'POST',
    json: {
      folder_path: folderPath,
      filenames,
    },
  })
}

export async function openCaseFileBlobInTab(
  caseId: string,
  file: FileSummary,
  token: string,
): Promise<void> {
  const res = await fetchCaseFileResponse(caseId, file.id, token)
  if (res.status === 401) {
    localStorage.removeItem('token')
    window.location.reload()
    return
  }
  if (!res.ok) throw new Error((await res.text()) || res.statusText)
  const blob = await res.blob()
  const typed = file.mime_type ? new Blob([blob], { type: file.mime_type }) : blob
  openBlobInNewTab(typed)
}

export async function openEmlViaDesktopToken(
  caseId: string,
  fileId: string,
  token: string,
): Promise<void> {
  try {
    await apiFetch(`/mail-plugin/pending-send`, {
      token,
      method: 'PUT',
      json: { case_id: caseId, source_file_id: fileId, ttl_seconds: 86400 },
    })
  } catch {
    /* Best-effort: Thunderbird reply prefill uses this when relatedMessageId is unavailable. */
  }
  const data = await apiFetch<{ token: string }>(`/cases/${caseId}/files/${fileId}/eml-open-token`, {
    method: 'POST',
    token,
  })
  const url = browserAbsoluteApiUrl(
    apiUrl(`/cases/${caseId}/files/${fileId}/eml-open?token=${encodeURIComponent(data.token)}`),
  )
  const a = document.createElement('a')
  a.href = url
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
}

/** Resolve Outlook web read URL for a filed .eml and open it; returns whether OWA opened. */
export async function tryOpenEmlInOutlookWeb(args: {
  caseId: string
  file: FileSummary
  token: string
  owaBase: string | null
  userEmail: string | null
  onPopupBlocked: () => void
}): Promise<'opened' | 'no_link'> {
  const { caseId, file, token, owaBase, userEmail, onPopupBlocked } = args
  const owaBaseQ = owaBase ? `?owa_base=${encodeURIComponent(owaBase)}` : ''
  let hints: {
    outlook_graph_message_id: string | null
    outlook_web_link: string | null
    owa_read_url?: string | null
    open_in_owa_supported?: boolean
  } | null = null
  try {
    hints = await apiFetch<{
      outlook_graph_message_id: string | null
      outlook_web_link: string | null
      owa_read_url?: string | null
      open_in_owa_supported?: boolean
    }>(`/cases/${caseId}/files/${file.id}/outlook-open-hints${owaBaseQ}`, { token })
  } catch {
    hints = null
  }
  const gid = (
    (hints?.outlook_graph_message_id ?? file.source_outlook_item_id ?? file.outlook_graph_message_id) ||
    ''
  ).trim()
  const webLink = (hints?.outlook_web_link ?? file.outlook_web_link ?? '').trim()
  let readUrl = (hints?.owa_read_url || '').trim()
  if (!readUrl && isUsableOutlookMessageWebLink(webLink)) {
    readUrl = webLink
  }
  if (!readUrl && webLink) {
    readUrl = normalizeOutlookWebReadLink(webLink, owaBase) || ''
  }
  if (!readUrl && gid && isLikelyExchangeRestItemId(gid)) {
    readUrl = buildOutlookWebReadItemUrl(owaBase, gid, webLink || null)
  }
  if (!readUrl) return 'no_link'
  const abs = appendOutlookWebAuthHintsForNav(browserAbsoluteApiUrl(readUrl), userEmail)
  const ok = openOutlookWebAppFromGraphWebLink(abs, {
    windowFeatures: OWA_MESSAGE_WINDOW_FEATURES,
    windowName: OWA_MAIL_WINDOW_NAME,
  })
  if (!ok) onPopupBlocked()
  return 'opened'
}

export function formatFileOpError(e: unknown, fallback: string): string {
  const msg = fetchTimedOutMessage(e)
  const err = e as { message?: string }
  return msg ?? err.message ?? fallback
}

export async function loadEmlPreviewData(
  caseId: string,
  fileId: string,
  token: string,
): Promise<EmlPreviewData | null> {
  const raw = await fetchEmlTextForPreview(caseId, fileId, token)
  if (!raw) return null
  return parseEmlForPreview(raw)
}
