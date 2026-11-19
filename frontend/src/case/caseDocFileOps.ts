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
  fetchEmlTextForPreview,
} from './caseDetailHelpers'
import { parseEmlForPreview, type EmlPreviewData } from './emlPreview'
import { documentErrorMessage } from './documentRequests'

export function isCommentFile(f: FileSummary): boolean {
  return (
    (f.mime_type || '').toLowerCase().startsWith('text/plain') ||
    (f.original_filename || '').toLowerCase().endsWith('.txt')
  )
}

export { triggerBlobDownload, openBlobInNewTab, downloadCaseFileBlob, downloadCaseFilesSequential, downloadCaseExportZipBlob, downloadCaseFolderZipBlob, uploadFilesToCaseFolder, openCaseFileBlobInTab } from './documentTransferOps'

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

/** True when the Canary Thunderbird content-script bridge is present in this page. */
export function pingThunderbirdBridge(timeoutMs = 400): Promise<boolean> {
  if (typeof window === 'undefined') return Promise.resolve(false)
  return new Promise((resolve) => {
    let settled = false
    const finish = (ok: boolean) => {
      if (settled) return
      settled = true
      window.removeEventListener('message', onMsg)
      resolve(ok)
    }
    const onMsg = (ev: MessageEvent) => {
      if (ev.source !== window) return
      const d = ev.data as { type?: string } | null
      if (!d || d.type !== 'canary-tb-bridge-ready') return
      finish(true)
    }
    window.addEventListener('message', onMsg)
    window.postMessage({ type: 'canary-tb-bridge-ping' }, '*')
    window.setTimeout(() => finish(false), timeoutMs)
  })
}

/** Ask the Canary Thunderbird content-script bridge to open an .eml (messageDisplay.open). */
export function tryOpenEmlInThunderbirdBridge(openUrl: string, filename: string): Promise<boolean> {
  if (typeof window === 'undefined') return Promise.resolve(false)
  return new Promise((resolve) => {
    const requestId =
      typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : `tb-${Date.now()}-${Math.random().toString(36).slice(2)}`
    let settled = false
    const finish = (ok: boolean) => {
      if (settled) return
      settled = true
      window.removeEventListener('message', onMsg)
      resolve(ok)
    }
    const onMsg = (ev: MessageEvent) => {
      if (ev.source !== window) return
      const d = ev.data as { type?: string; requestId?: string; ok?: boolean } | null
      if (!d || d.type !== 'canary-tb-open-eml-result' || d.requestId !== requestId) return
      finish(!!d.ok)
    }
    window.addEventListener('message', onMsg)
    window.postMessage(
      { type: 'canary-tb-open-eml', requestId, url: openUrl, filename: filename || 'message.eml' },
      '*',
    )
    // Retries inside the add-on can take several seconds when Thunderbird is busy.
    window.setTimeout(() => finish(false), 8000)
  })
}

function clickProtocolHref(href: string): void {
  if (typeof document === 'undefined') return
  try {
    const a = document.createElement('a')
    a.href = href
    a.rel = 'noopener'
    a.style.display = 'none'
    document.body.appendChild(a)
    a.click()
    a.remove()
  } catch {
    /* Browsers may block unknown schemes until a handler is registered. */
  }
}

/**
 * Ask the OS / Thunderbird to wake and poll the pending-eml queue.
 *
 * Prefer canary-eml: — that is an OS-level handler (Linux .desktop). Firefox treats
 * ext+… as its own extension scheme and will NOT launch Thunderbird when TB is closed.
 * Still fire ext+canary as a secondary nudge for environments where TB already owns it.
 */
export function wakeThunderbirdViaProtocol(): void {
  clickProtocolHref('canary-eml:pending-eml-open')
  window.setTimeout(() => {
    clickProtocolHref('ext+canary:pending-eml-open')
  }, 250)
}

async function sleepMs(ms: number): Promise<void> {
  await new Promise((r) => window.setTimeout(r, ms))
}

/**
 * Wait until the add-on has claimed the queue and the open likely stuck.
 * Claim clears the queue before messageDisplay.open finishes; failed opens re-queue,
 * so we only treat "inactive" as success after it stays clear briefly.
 */
async function waitForPendingEmlClaimed(
  token: string,
  fileId: string,
  timeoutMs = 9000,
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      const st = await apiFetch<{ active: boolean; file_id?: string | null }>(
        `/mail-plugin/pending-eml-open`,
        { token },
      )
      const oursGone =
        !st.active || (!!st.file_id && String(st.file_id) !== String(fileId))
      if (oursGone) {
        await sleepMs(1200)
        const st2 = await apiFetch<{ active: boolean; file_id?: string | null }>(
          `/mail-plugin/pending-eml-open`,
          { token },
        )
        const stillGone =
          !st2.active || (!!st2.file_id && String(st2.file_id) !== String(fileId))
        if (stillGone) return true
        // Re-queued after a failed open — keep waiting for the next claim cycle.
      }
    } catch {
      /* keep waiting */
    }
    await sleepMs(350)
  }
  try {
    const st = await apiFetch<{ active: boolean }>(`/mail-plugin/pending-eml-open`, { token })
    return !st.active
  } catch {
    return false
  }
}

/**
 * Open a filed .eml in Thunderbird:
 * 1) Instant bridge when Canary is open inside Thunderbird (no queue — avoids poller double-open)
 * 2) Otherwise queue for the add-on poller
 * 3) After a brief wait, fire ext+canary (starts TB if closed; also nudges an open TB to poll)
 * 4) Keep waiting after the wake — closed TB should still pick the queue up once it starts
 */
export async function openEmlViaDesktopToken(
  caseId: string,
  fileId: string,
  token: string,
  opts?: { filename?: string | null },
): Promise<'thunderbird' | 'queued' | 'launching' | 'needs_addon'> {
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
  let filename = (opts?.filename || 'message.eml').trim() || 'message.eml'
  if (!/\.eml$/i.test(filename)) filename = `${filename.replace(/\.[^.]+$/, '') || 'message'}.eml`

  // Bridge first, and do NOT queue while bridging — that race was opening the message twice.
  if (await pingThunderbirdBridge(350)) {
    if (await tryOpenEmlInThunderbirdBridge(url, filename)) {
      return 'thunderbird'
    }
  }

  await apiFetch(`/mail-plugin/pending-eml-open`, {
    token,
    method: 'PUT',
    json: { case_id: caseId, file_id: fileId, ttl_seconds: 120 },
  })

  // Fast path: Thunderbird already running + signed-in poller claims without an OS prompt.
  if (await waitForPendingEmlClaimed(token, fileId, 2200)) {
    return 'thunderbird'
  }

  // Wake / nudge Thunderbird whether it looks open or not. Closed TB should launch via
  // canary-eml: (OS). Cold start often takes well over 10s.
  wakeThunderbirdViaProtocol()

  if (await waitForPendingEmlClaimed(token, fileId, 12000)) {
    return 'thunderbird'
  }

  // Second nudge after a slow start; keep waiting for a cold Thunderbird launch.
  wakeThunderbirdViaProtocol()
  if (await waitForPendingEmlClaimed(token, fileId, 25000)) {
    return 'thunderbird'
  }

  // Still queued: add-on never claimed (not installed, not signed in, wrong origin, or
  // OS protocol handler missing — install linux/install-protocol-handler.sh).
  try {
    const st = await apiFetch<{ active: boolean; file_id?: string | null }>(
      `/mail-plugin/pending-eml-open`,
      { token },
    )
    const stillOurs =
      st.active && (!st.file_id || String(st.file_id) === String(fileId))
    if (stillOurs) return 'needs_addon'
  } catch {
    /* fall through */
  }
  return 'launching'
}

/** Force-download the .eml (browser save dialog). */
export async function downloadEmlViaToken(
  caseId: string,
  fileId: string,
  token: string,
  opts?: { filename?: string | null },
): Promise<void> {
  const data = await apiFetch<{ token: string }>(`/cases/${caseId}/files/${fileId}/eml-open-token`, {
    method: 'POST',
    token,
  })
  const url = browserAbsoluteApiUrl(
    apiUrl(`/cases/${caseId}/files/${fileId}/eml-open?token=${encodeURIComponent(data.token)}`),
  )
  let filename = (opts?.filename || 'message.eml').trim() || 'message.eml'
  if (!/\.eml$/i.test(filename)) filename = `${filename.replace(/\.[^.]+$/, '') || 'message'}.eml`
  const a = document.createElement('a')
  a.href = url
  a.rel = 'noopener'
  a.download = filename
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
  return documentErrorMessage(e, fallback)
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
