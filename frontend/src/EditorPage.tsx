import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch } from './api'
import { useDialogsOptional, type ConfirmOptions } from './DialogProvider'
import { isPortalSharedFolder, portalSharedFolderUploadNotifyMessage, portalContactsForFolder } from './case/portalFolderAccess'
import type { CasePortalFolderAccessGrantOut } from './types'
import { BusyIcon } from './BusyIcon'
import { signalCaseFilesChanged } from './caseFilesCrossTab'
import { canaryDocumentTitle } from './tabTitle'

type DocsApiEditor = {
  destroyEditor?: () => void
  /** Requires `events.onDownloadAs`; opens conversion pipeline (e.g. format `"pdf"` for print fallback). */
  downloadAs?: (format?: string) => void
}

type OoConfig = {
  document_server_url: string
  token: string
  document_type: string
  document: Record<string, unknown>
  editor_config: Record<string, unknown>
  /** Case compose-office: file is hidden until Save publishes it — closing should still confirm save. */
  oo_compose_pending?: boolean
  folder_path?: string
  original_filename?: string
}

type EditorTarget =
  | { mode: 'case'; caseId: string; fileId: string }
  | { mode: 'precedent'; precedentId: string }
  | { mode: 'fee-scale'; feeScaleId: string }

function editorConfigUrl(params: EditorTarget): string {
  if (params.mode === 'precedent') return `/precedents/${params.precedentId}/onlyoffice-config`
  if (params.mode === 'fee-scale') return `/fee-scales/${params.feeScaleId}/onlyoffice-config`
  return `/cases/${params.caseId}/files/${params.fileId}/onlyoffice-config`
}

function editorPersistPath(params: EditorTarget): string {
  if (params.mode === 'precedent') return `/precedents/${params.precedentId}/oo-persist-download`
  if (params.mode === 'fee-scale') return `/fee-scales/${params.feeScaleId}/oo-persist-download`
  return `/cases/${params.caseId}/files/${params.fileId}/oo-persist-download`
}

function editorForceSaveBase(params: EditorTarget): string {
  if (params.mode === 'precedent') return `/precedents/${params.precedentId}/oo-force-save`
  if (params.mode === 'fee-scale') return `/fee-scales/${params.feeScaleId}/oo-force-save`
  return `/cases/${params.caseId}/files/${params.fileId}/oo-force-save`
}

function parseEditorPath(): EditorTarget | null {
  const parts = window.location.pathname.split('/').filter(Boolean)
  // /editor/fee-scale/{feeScaleId}
  if (parts[0] === 'editor' && parts[1] === 'fee-scale' && parts[2]) {
    return { mode: 'fee-scale', feeScaleId: parts[2] }
  }
  // /editor/precedent/{precedentId}
  if (parts[0] === 'editor' && parts[1] === 'precedent' && parts[2]) {
    return { mode: 'precedent', precedentId: parts[2] }
  }
  // /editor/{caseId}/{fileId}
  if (parts[0] === 'editor' && parts[1] && parts[2]) {
    return { mode: 'case', caseId: parts[1], fileId: parts[2] }
  }
  return null
}

function resolveOoScriptBase(apiDocServerUrl: string): string {
  const directUrl = (import.meta.env.VITE_ONLYOFFICE_DIRECT_URL as string | undefined)?.trim()
  if (directUrl) return directUrl.replace(/\/$/, '')

  const directPort = (import.meta.env.VITE_ONLYOFFICE_DIRECT_PORT as string | undefined)?.trim()
  if (directPort && /^\d+$/.test(directPort)) {
    const { protocol, hostname } = window.location
    return `${protocol}//${hostname}:${directPort}`.replace(/\/$/, '')
  }

  const v = (import.meta.env.VITE_ONLYOFFICE_URL as string | undefined)?.trim()
  if (v?.startsWith('/')) return `${window.location.origin.replace(/\/$/, '')}${v}`
  if (v) return v.replace(/\/$/, '')
  return apiDocServerUrl.replace(/\/$/, '')
}

type DocsApiGlobal = {
  DocEditor?: { version?: () => string }
}

function onlyofficeDsMajor(): number {
  const g = window as Window & { DocsAPI?: DocsApiGlobal }
  const ver = g.DocsAPI?.DocEditor?.version?.() ?? ''
  const n = parseInt(ver.split('.')[0] || '0', 10)
  return Number.isFinite(n) ? n : 0
}

/** DocsAPI validates documentType client-side; pre-8 api.js (often CDN-cached) rejects ``pdf``. */
function isPdfOoConfig(cfg: OoConfig): boolean {
  const ft = String((cfg.document as { fileType?: string }).fileType || '')
    .trim()
    .toLowerCase()
  const dt = (cfg.document_type || '').trim().toLowerCase()
  return ft === 'pdf' || dt === 'pdf'
}

const OO_PERSIST_SAVE_TIMEOUT_MS = 90_000
const OO_SAVE_POLL_MS = 300
/** Brief poll after programmatic toolbar Save (matches native OO Save callback). */
const OO_PDF_TOOLBAR_POLL_MS = 12_000
/** Office formats: allow longer for CommandService forcesave + callback persist. */
const OO_OFFICE_SAVE_POLL_MS = 45_000
const OO_SYNC_WAIT_MS = 3_000

type OoForceSaveArmOut = { base_version: number }
type OoSaveStatusOut = { saved: boolean; version: number }

const OO_TOOLBAR_SAVE_SELECTORS = [
  '#id-toolbar-btn-save',
  '#slot-btn-save',
  'li[data-id="save"]',
  'button[data-layout-name="toolbar-save"]',
  '[data-hint="Save"]',
  'button[aria-label="Save"]',
]

/** Walk ONLYOFFICE nested iframes and click the native Save control (forcesave callback path). */
function triggerOnlyofficeToolbarSave(): boolean {
  function findSaveButton(doc: Document): HTMLElement | null {
    for (const sel of OO_TOOLBAR_SAVE_SELECTORS) {
      const el = doc.querySelector(sel) as HTMLElement | null
      if (el) return el
    }
    for (const iframe of doc.querySelectorAll('iframe')) {
      try {
        const nested = iframe.contentDocument
        if (!nested) continue
        const found = findSaveButton(nested)
        if (found) return found
      } catch {
        /* cross-origin */
      }
    }
    return null
  }

  const host = document.getElementById('oo-editor-page')
  for (const iframe of host?.querySelectorAll('iframe') ?? []) {
    try {
      const doc = iframe.contentDocument
      if (!doc) continue
      const btn = findSaveButton(doc)
      if (btn) {
        btn.click()
        return true
      }
    } catch {
      /* ignore */
    }
  }
  return false
}

function ooForceSavePath(base: string, docKey: string, phase: 'arm' | 'command'): string {
  const q = new URLSearchParams({ doc_key: docKey, phase })
  return `${base}?${q}`
}

function ooSaveStatusPath(forceSaveUrl: string, baseVersion: number): string {
  const url = forceSaveUrl.replace(/\/oo-force-save$/, '/oo-save-status')
  return `${url}?base_version=${encodeURIComponent(String(baseVersion))}`
}

async function pollOnlyofficeSaveConfirmed(
  statusUrl: string,
  baseVersion: number,
  token: string | undefined,
  timeoutMs: number,
): Promise<void> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const st = await apiFetch<OoSaveStatusOut>(statusUrl, { token })
    if (st.saved && st.version > baseVersion) return
    await new Promise((r) => setTimeout(r, OO_SAVE_POLL_MS))
  }
  throw new Error('ONLYOFFICE forcesave did not confirm within the expected time.')
}

function resolveOoDocumentType(cfg: OoConfig, dsMajor: number): string {
  const fromApi = (cfg.document_type || '').trim().toLowerCase()
  if (isPdfOoConfig(cfg) && dsMajor > 0 && dsMajor < 8) return 'word'
  if (
    fromApi === 'word' ||
    fromApi === 'cell' ||
    fromApi === 'slide' ||
    fromApi === 'pdf' ||
    fromApi === 'diagram'
  ) {
    return fromApi
  }
  if (isPdfOoConfig(cfg)) return dsMajor >= 8 ? 'pdf' : 'word'
  return fromApi || 'word'
}

function ooApiScriptUrl(base: string): string {
  const bust =
    (import.meta.env.VITE_ONLYOFFICE_API_CACHE_BUST as string | undefined)?.trim() || '9.0.3'
  return `${base}/web-apps/apps/api/documents/api.js?v=${encodeURIComponent(bust)}`
}

function loadOoScript(base: string): Promise<void> {
  const g = window as Window & { DocsAPI?: DocsApiGlobal }
  if (g.DocsAPI) {
    try {
      if (onlyofficeDsMajor() >= 8) return Promise.resolve()
    } catch {
      /* drop stale DocsAPI and reload */
    }
    delete (window as { DocsAPI?: DocsApiGlobal }).DocsAPI
  }
  const url = ooApiScriptUrl(base)
  return new Promise((resolve, reject) => {
    const s = document.createElement('script')
    s.src = url
    s.async = true
    s.dataset.canaryOoApi = '1'
    s.onload = () => resolve()
    s.onerror = () =>
      reject(
        new Error(
          `Failed to load ONLYOFFICE script from ${url}. ` +
            'Ensure the onlyoffice service is running and the /office-ds Vite proxy is reachable.',
        ),
      )
    document.body.appendChild(s)
  })
}

/**
 * ONLYOFFICE `onDocumentStateChange`: `true` while the user is actively editing; `false` once
 * changes are synced to the document server — not “nothing to save”. Parse defensively because
 * embedders may stringify or wrap `data`.
 */
function parseOnlyofficeDocumentStateEvent(event: unknown): boolean | null {
  if (event === true || event === false) return event
  if (typeof event === 'string') {
    const s = event.trim().toLowerCase()
    if (s === 'true') return true
    if (s === 'false') return false
    try {
      return parseOnlyofficeDocumentStateEvent(JSON.parse(event) as unknown)
    } catch {
      return null
    }
  }
  if (event && typeof event === 'object' && 'data' in event) {
    return parseOnlyofficeDocumentStateEvent((event as { data: unknown }).data)
  }
  return null
}

function formatOoError(event: unknown): string {
  try {
    const e = event as {
      data?: { errorCode?: number; errorDescription?: string } | string
      errorCode?: number
      errorDescription?: string
    }
    const d = e?.data
    if (d && typeof d === 'object' && typeof d.errorCode === 'number') {
      return `ONLYOFFICE (${d.errorCode}): ${(d.errorDescription || '').trim() || 'unknown'}`
    }
    if (typeof e?.errorCode === 'number') {
      return `ONLYOFFICE (${e.errorCode}): ${(e.errorDescription || '').trim() || 'unknown'}`
    }
  } catch { /* ignore */ }
  try {
    return typeof event === 'object' ? JSON.stringify(event) : String(event)
  } catch {
    return 'ONLYOFFICE reported an error (see browser console).'
  }
}

export default function EditorPage() {
  const params = parseEditorPath()
  const dialogs = useDialogsOptional()
  const askConfirm = useCallback(
    async (opts: ConfirmOptions) => {
      if (dialogs) return dialogs.askConfirm(opts)
      const body = opts.message.trim()
      const prompt = body ? `${opts.title}\n\n${body}` : opts.title
      return window.confirm(prompt)
    },
    [dialogs],
  )
  const [cfg, setCfg] = useState<OoConfig | null>(null)
  const [filename, setFilename] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [closing, setClosing] = useState(false)
  /** Save from the “unsaved changes” strip — separate from ``closing`` so Cancel stays enabled (no soft-lock). */
  const [unsavedSaveBusy, setUnsavedSaveBusy] = useState(false)
  /**
   * Session has edits that are not committed via our Save path yet. Latched when ONLYOFFICE reports
   * active editing; not cleared on DS sync (`event.data === false` — that is not “saved to Canary”).
   */
  const [documentDirty, setDocumentDirty] = useState(false)
  /** New compose document not yet published — treat like unsaved for Close even if OO reports no edits. */
  const [composePublishPending, setComposePublishPending] = useState(false)
  const hasUncommittedOoEditsRef = useRef(false)
  const [unsavedCloseOpen, setUnsavedCloseOpen] = useState(false)
  const [pdfExportBusy, setPdfExportBusy] = useState(false)
  const [saveAsPdfNotice, setSaveAsPdfNotice] = useState<string | null>(null)
  const [saveAsPdfBusy, setSaveAsPdfBusy] = useState(false)
  const apiRef = useRef<DocsApiEditor | null>(null)
  const pdfExportTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const saveAsPdfNoticeTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  /** After downloadAs: print staging, Save as PDF (new file), or persist edits to Canary storage. */
  const pendingDownloadAsRef = useRef<'print' | 'saveAsPdf' | 'persist' | null>(null)
  const persistSaveWaitRef = useRef<{
    resolve: () => void
    reject: (err: Error) => void
    timeout: ReturnType<typeof setTimeout>
  } | null>(null)
  /** ONLYOFFICE ``onDocumentStateChange``: true while the user is actively typing. */
  const ooEditorBusyRef = useRef(false)
  const printTabRef = useRef<Window | null>(null)
  const token = localStorage.getItem('token') ?? undefined

  // Fetch editor config on mount. AbortController avoids overlapping onlyoffice-config calls
  // (React Strict Mode remount, fast tab switches) minting extra WebDAV sessions server-side.
  useEffect(() => {
    if (!params) {
      setErr('Invalid editor URL — expected /editor/{caseId}/{fileId}, /editor/precedent/{precedentId}, or /editor/fee-scale/{feeScaleId}')
      return
    }
    const ac = new AbortController()
    apiFetch<OoConfig>(editorConfigUrl(params), { token, signal: ac.signal })
      .then((data) => {
        if (ac.signal.aborted) return
        setErr(null)
        setCfg(data)
        setFilename((data.document as { title?: string }).title ?? '')
        setComposePublishPending(Boolean(data.oo_compose_pending))
      })
      .catch((e: unknown) => {
        if (ac.signal.aborted) return
        const name = e && typeof e === 'object' && 'name' in e ? String((e as { name: unknown }).name) : ''
        if (name === 'AbortError') return
        const m = (e as { message?: string }).message?.trim()
        setErr(m || 'Could not load editor config')
      })
    return () => ac.abort()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const t = filename.trim()
    if (!t) return
    const previous = document.title
    document.title = canaryDocumentTitle(t)
    return () => {
      document.title = previous
    }
  }, [filename])

  // Host Ctrl/Cmd+P → Canary print path (same as toolbar Print); avoids ONLYOFFICE /printfile PDF MIME issues.
  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      const isP = ev.key === 'p' || ev.key === 'P'
      if (!isP || ev.altKey) return
      if (!ev.ctrlKey && !ev.metaKey) return
      if (!cfg || !apiRef.current?.downloadAs || pdfExportBusy || saving || closing || unsavedSaveBusy) return
      ev.preventDefault()
      const w = window.open(
        'about:blank',
        'canary_oo_print',
        'popup=yes,width=1080,height=1440,left=60,top=40',
      )
      printTabRef.current = w
      if (!w) {
        setErr('Print needs a new window — allow pop-ups for this site, then try again.')
        return
      }
      pendingDownloadAsRef.current = 'print'
      setPdfExportBusy(true)
      if (pdfExportTimeoutRef.current !== undefined) clearTimeout(pdfExportTimeoutRef.current)
      pdfExportTimeoutRef.current = window.setTimeout(() => {
        pdfExportTimeoutRef.current = undefined
        pendingDownloadAsRef.current = null
        printTabRef.current = null
        setPdfExportBusy(false)
      }, 120_000)
      try {
        apiRef.current.downloadAs('pdf')
      } catch {
        if (pdfExportTimeoutRef.current !== undefined) clearTimeout(pdfExportTimeoutRef.current)
        pdfExportTimeoutRef.current = undefined
        pendingDownloadAsRef.current = null
        printTabRef.current = null
        setPdfExportBusy(false)
        try {
          w.close()
        } catch {
          /* ignore */
        }
      }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [cfg, pdfExportBusy, saving, closing, unsavedSaveBusy])

  // Initialise OO DS editor once config is available
  useEffect(() => {
    if (!cfg) return
    hasUncommittedOoEditsRef.current = false
    setDocumentDirty(false)
    const base = resolveOoScriptBase(cfg.document_server_url)
    let active = true

    loadOoScript(base)
      .then(() => {
        if (!active) return
        const host = document.getElementById('oo-editor-page')
        if (!host) {
          if (active) setErr('Editor mount point missing — reload this tab.')
          return
        }
        const g = window as Window & {
          DocsAPI?: { DocEditor: new (id: string, c: Record<string, unknown>) => DocsApiEditor }
        }
        if (!g.DocsAPI) {
          if (active) setErr('ONLYOFFICE script loaded but DocsAPI is missing')
          return
        }
        apiRef.current?.destroyEditor?.()
        const dsMajor = onlyofficeDsMajor()
        const documentType = resolveOoDocumentType(cfg, dsMajor)
        if (documentType !== (cfg.document_type || '').trim().toLowerCase()) {
          console.info(
            '[ONLYOFFICE] documentType %s (api.js DS %s; backend sent %s)',
            documentType,
            dsMajor || '?',
            cfg.document_type,
          )
        }
        try {
          apiRef.current = new g.DocsAPI.DocEditor('oo-editor-page', {
          documentServerUrl: `${base.replace(/\/$/, '')}/`,
          token: cfg.token,
          document: cfg.document,
          editorConfig: cfg.editor_config,
          type: 'desktop',
          documentType,
          width: '100%',
          height: '100%',
          events: {
            onAppReady: () => console.info('[ONLYOFFICE] onAppReady'),
            onDocumentStateChange: (event: unknown) => {
              if (!active) return
              const v = parseOnlyofficeDocumentStateEvent(event)
              if (v === true) {
                ooEditorBusyRef.current = true
                hasUncommittedOoEditsRef.current = true
                setDocumentDirty(true)
              } else if (v === false) {
                ooEditorBusyRef.current = false
                setDocumentDirty(hasUncommittedOoEditsRef.current)
              }
            },
            onDocumentReady: () => {
              console.info('[ONLYOFFICE] onDocumentReady — document rendered OK')
              if (active) {
                ooEditorBusyRef.current = false
                hasUncommittedOoEditsRef.current = false
                setDocumentDirty(false)
              }
            },
            onWarning: (event: unknown) => console.warn('[ONLYOFFICE onWarning]', event),
            onError: (event: unknown) => {
              const raw = JSON.stringify(event)
              console.error('[ONLYOFFICE onError] RAW:', raw)
              if (active) {
                apiRef.current?.destroyEditor?.()
                apiRef.current = null
                setErr(`${formatOoError(event)} | raw: ${raw}`)
              }
            },
            // Required for downloadAs(); Print + Save as PDF use conversion URLs under /cache/files/.
            onDownloadAs: (event: unknown) => {
              if (pdfExportTimeoutRef.current !== undefined) {
                clearTimeout(pdfExportTimeoutRef.current)
                pdfExportTimeoutRef.current = undefined
              }
              const e = event as { data?: { url?: string; fileType?: string } }
              const url = e?.data?.url
              const mode = pendingDownloadAsRef.current
              pendingDownloadAsRef.current = null
              const printWin = printTabRef.current
              printTabRef.current = null

              if (mode === 'persist') {
                const wait = persistSaveWaitRef.current
                persistSaveWaitRef.current = null
                if (!wait) return
                if (typeof url !== 'string' || !url.length) {
                  clearTimeout(wait.timeout)
                  wait.reject(new Error('ONLYOFFICE did not return a download URL for save.'))
                  return
                }
                if (!params || !token) {
                  clearTimeout(wait.timeout)
                  wait.reject(new Error('Sign in again to save.'))
                  return
                }
                const persistPath = editorPersistPath(params)
                void (async () => {
                  try {
                    await apiFetch(persistPath, {
                      method: 'POST',
                      token,
                      json: { browser_url: url },
                    })
                    clearTimeout(wait.timeout)
                    wait.resolve()
                  } catch (err: unknown) {
                    clearTimeout(wait.timeout)
                    const msg =
                      (err as { message?: string }).message ?? 'Could not persist document to Canary storage.'
                    wait.reject(new Error(msg))
                  }
                })()
                return
              }

              if (mode === 'print') {
                if (typeof url === 'string' && url.length > 0 && printWin && token) {
                  void (async () => {
                    try {
                      const r = await apiFetch<{ sid: string; t: string }>('/onlyoffice/print-stage', {
                        method: 'POST',
                        token,
                        json: { browser_url: url },
                      })
                      const next = new URL('/oo-print', window.location.origin)
                      next.searchParams.set('sid', r.sid)
                      next.searchParams.set('t', r.t)
                      printWin.location.replace(next.href)
                    } catch (err: unknown) {
                      const msg =
                        (err as { message?: string }).message ??
                        'Print staging failed. Try Save as PDF instead.'
                      try {
                        printWin.document.body.textContent = msg
                      } catch {
                        printWin.close()
                      }
                    } finally {
                      setPdfExportBusy(false)
                    }
                  })()
                  return
                }
                try {
                  printWin?.close()
                } catch {
                  /* ignore */
                }
                if (!token) setErr('Sign in again to print.')
                else if (!url) setErr('ONLYOFFICE did not return a PDF URL for print.')
                setPdfExportBusy(false)
                return
              }

              if (mode === 'saveAsPdf') {
                if (typeof url !== 'string' || !url.length) {
                  setErr('ONLYOFFICE did not return a PDF URL.')
                  setPdfExportBusy(false)
                  setSaveAsPdfBusy(false)
                  return
                }
                if (!params || params.mode !== 'case' || !token) {
                  setErr('Save as PDF is only available for matter documents while signed in.')
                  setPdfExportBusy(false)
                  setSaveAsPdfBusy(false)
                  return
                }
                void (async () => {
                  try {
                    const r = await apiFetch<{ file_id: string; original_filename: string }>(
                      `/cases/${params.caseId}/files/${params.fileId}/oo-export-pdf`,
                      { method: 'POST', token, json: { browser_url: url } },
                    )
                    setErr(null)
                    const msg = `Saved as ${r.original_filename} in this matter.`
                    setSaveAsPdfNotice(msg)
                    if (saveAsPdfNoticeTimeoutRef.current !== undefined) {
                      clearTimeout(saveAsPdfNoticeTimeoutRef.current)
                    }
                    saveAsPdfNoticeTimeoutRef.current = window.setTimeout(() => {
                      saveAsPdfNoticeTimeoutRef.current = undefined
                      setSaveAsPdfNotice(null)
                    }, 10_000)
                    notifyCaseFilesChangedIfCase()
                  } catch (err: unknown) {
                    setSaveAsPdfNotice(null)
                    setErr(
                      (err as { message?: string }).message ??
                        'Could not save PDF to matter storage.',
                    )
                  } finally {
                    setPdfExportBusy(false)
                    setSaveAsPdfBusy(false)
                  }
                })()
                return
              }

              setPdfExportBusy(false)
              setSaveAsPdfBusy(false)
            },
          },
        })
        } catch (boot: unknown) {
          if (active) {
            const m = (boot as Error).message?.trim()
            setErr(m || 'Failed to start ONLYOFFICE editor (see browser console).')
          }
        }
      })
      .catch((e: unknown) => {
        if (active) {
          const m = (e as { message?: string }).message?.trim()
          setErr(m || 'Failed to load ONLYOFFICE')
        }
      })

    return () => {
      active = false
      apiRef.current?.destroyEditor?.()
      apiRef.current = null
    }
  }, [cfg]) // eslint-disable-line react-hooks/exhaustive-deps

  function notifyCaseFilesChangedIfCase() {
    if (params?.mode !== 'case') return
    try {
      window.opener?.postMessage(
        { type: 'canary-files-changed', caseId: params.caseId },
        window.location.origin,
      )
    } catch {
      /* ignore */
    }
    signalCaseFilesChanged(params.caseId)
  }

  function saveDocumentViaDownloadAs(format: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const editor = apiRef.current
      if (!editor?.downloadAs) {
        reject(new Error('ONLYOFFICE editor is not ready. Wait for the document to finish loading.'))
        return
      }
      const timeout = window.setTimeout(() => {
        if (pendingDownloadAsRef.current === 'persist') {
          pendingDownloadAsRef.current = null
          persistSaveWaitRef.current = null
          reject(new Error('Save timed out waiting for ONLYOFFICE to export the document.'))
        }
      }, OO_PERSIST_SAVE_TIMEOUT_MS)
      persistSaveWaitRef.current = {
        resolve: () => {
          clearTimeout(timeout)
          resolve()
        },
        reject: (err: Error) => {
          clearTimeout(timeout)
          reject(err)
        },
        timeout,
      }
      pendingDownloadAsRef.current = 'persist'
      try {
        editor.downloadAs(format)
      } catch (e: unknown) {
        clearTimeout(timeout)
        pendingDownloadAsRef.current = null
        persistSaveWaitRef.current = null
        reject(e instanceof Error ? e : new Error(String(e)))
      }
    })
  }

  async function waitForOoServerSync(): Promise<void> {
    const deadline = Date.now() + OO_SYNC_WAIT_MS
    while (Date.now() < deadline) {
      if (!ooEditorBusyRef.current && !hasUncommittedOoEditsRef.current) {
        await new Promise((r) => setTimeout(r, 250))
        return
      }
      await new Promise((r) => setTimeout(r, 100))
    }
  }

  /**
   * Office save: prefer forcesave callback (native OO save path). ``downloadAs`` exports can
   * produce .docx files that ONLYOFFICE fails to reopen (``changesError`` on next open).
   */
  async function performOfficeSave(format: string): Promise<void> {
    if (!params || !cfg) return
    const docKey = String((cfg.document as { key?: string }).key ?? '')
    if (!docKey) {
      throw new Error('Editor key missing; cannot save safely. Please reload and try again.')
    }
    const saveBase = editorForceSaveBase(params)

    await waitForOoServerSync()

    const arm = await apiFetch<OoForceSaveArmOut>(ooForceSavePath(saveBase, docKey, 'arm'), {
      method: 'POST',
      token,
    })
    const statusUrl = ooSaveStatusPath(saveBase, arm.base_version)

    let saveTriggered = triggerOnlyofficeToolbarSave()
    if (!saveTriggered) {
      try {
        await apiFetch(ooForceSavePath(saveBase, docKey, 'command'), { method: 'POST', token })
        saveTriggered = true
      } catch (e: unknown) {
        console.warn('[ONLYOFFICE] command forcesave failed:', e)
      }
    }

    if (saveTriggered) {
      try {
        await pollOnlyofficeSaveConfirmed(statusUrl, arm.base_version, token, OO_OFFICE_SAVE_POLL_MS)
        return
      } catch (pollErr: unknown) {
        console.warn('[ONLYOFFICE] forcesave not confirmed; using downloadAs:', pollErr)
      }
    } else {
      console.info('[ONLYOFFICE] toolbar Save not reachable; using downloadAs persist')
    }

    await saveDocumentViaDownloadAs(format)
  }

  /**
   * PDF save: prefer native toolbar forcesave (correct form appearances). CommandService
   * forcesave does not bump version for PDFs in practice — do not poll 45s waiting for it.
   * Fall back quickly to ``downloadAs`` + backend NeedAppearances fix.
   */
  async function performPdfSave(): Promise<void> {
    if (!params || !cfg) return
    const docKey = String((cfg.document as { key?: string }).key ?? '')
    if (!docKey) {
      throw new Error('Editor key missing; cannot save safely. Please reload and try again.')
    }
    const saveBase = editorForceSaveBase(params)

    await waitForOoServerSync()

    if (triggerOnlyofficeToolbarSave()) {
      const arm = await apiFetch<OoForceSaveArmOut>(ooForceSavePath(saveBase, docKey, 'arm'), {
        method: 'POST',
        token,
      })
      const statusUrl = ooSaveStatusPath(saveBase, arm.base_version)
      try {
        await pollOnlyofficeSaveConfirmed(
          statusUrl,
          arm.base_version,
          token,
          OO_PDF_TOOLBAR_POLL_MS,
        )
        return
      } catch (pollErr: unknown) {
        console.warn('[ONLYOFFICE] toolbar forcesave not confirmed; using downloadAs:', pollErr)
      }
    } else {
      console.info('[ONLYOFFICE] toolbar Save not reachable; using downloadAs persist')
    }

    await saveDocumentViaDownloadAs('pdf')
  }

  const canUseSaveAsPdf =
    params?.mode === 'case' && cfg !== null && !isPdfOoConfig(cfg)

  async function performSave(): Promise<boolean> {
    if (!params || !cfg) return false
    const fileType = String((cfg.document as { fileType?: string }).fileType ?? '').toLowerCase()
    const dlFormat = fileType === 'pdf' ? 'pdf' : fileType || 'docx'
    /** Compose drafts (quotes, letters) are already on disk — publishing is enough if the user did not edit. */
    const composePublishOnly =
      params.mode === 'case' &&
      composePublishPending &&
      !hasUncommittedOoEditsRef.current &&
      !documentDirty
    try {
      if (!composePublishOnly) {
        if (isPdfOoConfig(cfg)) {
          await performPdfSave()
        } else {
          await performOfficeSave(dlFormat)
        }
      }

      if (params.mode === 'case') {
        let notifyPortalContacts = false
        if (composePublishPending && cfg.folder_path !== undefined && token) {
          try {
            const grants = await apiFetch<CasePortalFolderAccessGrantOut[]>(
              `/cases/${params.caseId}/files/portal-folder-access`,
              { token },
            )
            const folderPath = cfg.folder_path ?? ''
            if (isPortalSharedFolder(folderPath, grants)) {
              const contacts = portalContactsForFolder(folderPath, grants)
              notifyPortalContacts = await askConfirm({
                title: 'Notify portal contacts?',
                message: portalSharedFolderUploadNotifyMessage(contacts, 1),
                confirmLabel: 'Send e-mail',
                cancelLabel: 'Skip',
              })
            }
          } catch {
            /* optional — publish without notify prompt */
          }
        }
        await apiFetch(`/cases/${params.caseId}/files/${params.fileId}/publish-compose`, {
          method: 'POST',
          token,
          json: { notify_portal_contacts: notifyPortalContacts },
        })
        notifyCaseFilesChangedIfCase()
      }
      hasUncommittedOoEditsRef.current = false
      setDocumentDirty(false)
      setComposePublishPending(false)
      return true
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Save failed. Keep this window open and try again.')
      return false
    }
  }

  async function handleSaveChanges() {
    if (!params || !cfg || saving || closing) return
    setSaving(true)
    try {
      await performSave()
    } finally {
      setSaving(false)
    }
  }

  async function releaseCaseEditSession() {
    if (params?.mode !== 'case') return
    try {
      await apiFetch(`/cases/${params.caseId}/files/${params.fileId}/release-edit`, {
        method: 'POST',
        token,
      })
    } catch {
      /* best-effort: still try to close */
    }
  }

  function tearDownOnlyofficeEditor() {
    apiRef.current?.destroyEditor?.()
    apiRef.current = null
  }

  async function performCloseClean() {
    if (!params || closing) return
    setClosing(true)
    try {
      tearDownOnlyofficeEditor()
      await releaseCaseEditSession()
      notifyCaseFilesChangedIfCase()
      window.close()
    } finally {
      setClosing(false)
    }
  }

  async function performCloseDiscardUnsaved() {
    if (!params || closing) return
    setClosing(true)
    try {
      tearDownOnlyofficeEditor()
      if (params.mode === 'case') {
        try {
          await apiFetch(`/cases/${params.caseId}/files/${params.fileId}/discard-edit`, {
            method: 'POST',
            token,
          })
        } catch {
          /* best-effort */
        }
      }
      notifyCaseFilesChangedIfCase()
      window.close()
    } finally {
      setClosing(false)
    }
  }

  function handleCloseClick() {
    if (!params || saving || closing || unsavedSaveBusy || !cfg) return
    if (!documentDirty && !composePublishPending) void performCloseClean()
    else setUnsavedCloseOpen(true)
  }

  async function handleUnsavedCloseSave() {
    if (!params || unsavedSaveBusy) return
    setUnsavedSaveBusy(true)
    try {
      const ok = await performSave()
      if (!ok) return
      setUnsavedCloseOpen(false)
      tearDownOnlyofficeEditor()
      await releaseCaseEditSession()
      notifyCaseFilesChangedIfCase()
      window.close()
    } finally {
      setUnsavedSaveBusy(false)
    }
  }

  function handleUnsavedCloseDontSave() {
    if (unsavedSaveBusy) return
    setUnsavedCloseOpen(false)
    void performCloseDiscardUnsaved()
  }

  if (!params) {
    return <div style={{ color: '#dc2626', padding: 20 }}>Invalid editor URL</div>
  }

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        width: '100vw',
        height: '100vh',
        background: 'var(--page-bg)',
        overflow: 'hidden',
      }}
    >
      {/* Minimal toolbar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '0 12px',
          background: '#ffffff',
          borderBottom: '1px solid rgba(15,23,42,0.1)',
          flexShrink: 0,
          height: 36,
          boxSizing: 'border-box',
        }}
      >
        <span
          style={{
            color: saveAsPdfNotice ? '#15803d' : '#64748b',
            fontSize: 13,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            flex: 1,
          }}
          title={saveAsPdfNotice ?? filename}
        >
          {saveAsPdfNotice ?? filename}
        </span>
        <button
          type="button"
          title="Opens a print dialog via HTML preview (works when the browser treats ONLYOFFICE PDFs as downloads)."
          onClick={() => {
            if (pdfExportBusy || !apiRef.current?.downloadAs || !cfg || saving || closing || unsavedSaveBusy)
              return
            const w = window.open(
              'about:blank',
              'canary_oo_print',
              'popup=yes,width=1080,height=1440,left=60,top=40',
            )
            printTabRef.current = w
            if (!w) {
              setErr('Print needs a new window — allow pop-ups for this site, then try again.')
              return
            }
            pendingDownloadAsRef.current = 'print'
            setPdfExportBusy(true)
            if (pdfExportTimeoutRef.current !== undefined) clearTimeout(pdfExportTimeoutRef.current)
            pdfExportTimeoutRef.current = window.setTimeout(() => {
              pdfExportTimeoutRef.current = undefined
              pendingDownloadAsRef.current = null
              printTabRef.current = null
              setPdfExportBusy(false)
            }, 120_000)
            try {
              apiRef.current.downloadAs('pdf')
            } catch {
              if (pdfExportTimeoutRef.current !== undefined) clearTimeout(pdfExportTimeoutRef.current)
              pdfExportTimeoutRef.current = undefined
              pendingDownloadAsRef.current = null
              printTabRef.current = null
              setPdfExportBusy(false)
              try {
                w.close()
              } catch {
                /* ignore */
              }
            }
          }}
          disabled={pdfExportBusy || saving || closing || unsavedSaveBusy || !cfg}
          style={{
            background: 'rgba(15,23,42,0.06)',
            border: '1px solid rgba(15,23,42,0.15)',
            color: '#334155',
            cursor: pdfExportBusy || saving || closing || unsavedSaveBusy || !cfg ? 'default' : 'pointer',
            fontSize: 12,
            padding: '3px 10px',
            borderRadius: 4,
            flexShrink: 0,
            opacity: pdfExportBusy || saving || closing || unsavedSaveBusy || !cfg ? 0.5 : 1,
            whiteSpace: 'nowrap',
          }}
        >
          {pdfExportBusy ? 'Preparing…' : 'Print'}
        </button>
        <button
          type="button"
          title={
            !cfg
              ? ''
              : canUseSaveAsPdf
                ? 'Save a PDF copy to this matter (does not replace the open document).'
                : isPdfOoConfig(cfg)
                  ? 'Already a PDF — use Save Changes to update this file.'
                  : 'Save as PDF is only available for matter documents.'
          }
          onClick={() => {
            if (
              !canUseSaveAsPdf ||
              pdfExportBusy ||
              !apiRef.current?.downloadAs ||
              saving ||
              closing ||
              unsavedSaveBusy
            ) {
              return
            }
            setSaveAsPdfNotice(null)
            pendingDownloadAsRef.current = 'saveAsPdf'
            setSaveAsPdfBusy(true)
            setPdfExportBusy(true)
            if (pdfExportTimeoutRef.current !== undefined) clearTimeout(pdfExportTimeoutRef.current)
            pdfExportTimeoutRef.current = window.setTimeout(() => {
              pdfExportTimeoutRef.current = undefined
              pendingDownloadAsRef.current = null
              setPdfExportBusy(false)
              setSaveAsPdfBusy(false)
              setErr('Save as PDF timed out waiting for ONLYOFFICE.')
            }, 120_000)
            try {
              apiRef.current.downloadAs('pdf')
            } catch {
              if (pdfExportTimeoutRef.current !== undefined) clearTimeout(pdfExportTimeoutRef.current)
              pdfExportTimeoutRef.current = undefined
              pendingDownloadAsRef.current = null
              setPdfExportBusy(false)
              setSaveAsPdfBusy(false)
              setErr('Could not start PDF export from ONLYOFFICE.')
            }
          }}
          disabled={
            !canUseSaveAsPdf || pdfExportBusy || saving || closing || unsavedSaveBusy || !cfg
          }
          style={{
            background: 'rgba(15,23,42,0.06)',
            border: '1px solid rgba(15,23,42,0.15)',
            color: '#334155',
            cursor:
              !canUseSaveAsPdf || pdfExportBusy || saving || closing || unsavedSaveBusy || !cfg
                ? 'default'
                : 'pointer',
            fontSize: 12,
            padding: '3px 10px',
            borderRadius: 4,
            flexShrink: 0,
            opacity:
              !canUseSaveAsPdf || pdfExportBusy || saving || closing || unsavedSaveBusy || !cfg
                ? 0.5
                : 1,
            whiteSpace: 'nowrap',
          }}
        >
          {saveAsPdfBusy ? 'Saving PDF…' : 'Save as PDF'}
        </button>
        <button
          type="button"
          onClick={() => void handleSaveChanges()}
          disabled={saving || closing || unsavedSaveBusy || !cfg}
          style={{
            background: 'rgba(37,99,235,0.12)',
            border: '1px solid rgba(37,99,235,0.45)',
            color: '#1d4ed8',
            cursor: saving || closing || unsavedSaveBusy || !cfg ? 'default' : 'pointer',
            fontSize: 12,
            padding: '3px 10px',
            borderRadius: 4,
            flexShrink: 0,
            opacity: saving || closing || unsavedSaveBusy || !cfg ? 0.5 : 1,
            whiteSpace: 'nowrap',
          }}
        >
          {saving ? 'Saving…' : 'Save Changes'}
        </button>
        {unsavedCloseOpen ? (
          <>
            <span style={{ color: '#64748b', fontSize: 12, whiteSpace: 'nowrap' }}>
              Unsaved changes. Save before closing?
            </span>
            <button
              type="button"
              onClick={() => void handleUnsavedCloseSave()}
              disabled={unsavedSaveBusy}
              style={{
                background: 'rgba(37,99,235,0.12)',
                border: '1px solid rgba(37,99,235,0.45)',
                color: '#1d4ed8',
                cursor: unsavedSaveBusy ? 'default' : 'pointer',
                fontSize: 12,
                padding: '3px 10px',
                borderRadius: 4,
                flexShrink: 0,
                opacity: unsavedSaveBusy ? 0.5 : 1,
                whiteSpace: 'nowrap',
              }}
            >
              {unsavedSaveBusy ? 'Working…' : 'Save'}
            </button>
            <button
              type="button"
              onClick={() => handleUnsavedCloseDontSave()}
              disabled={unsavedSaveBusy}
              style={{
                background: 'rgba(255,77,77,0.15)',
                border: '1px solid rgba(255,77,77,0.6)',
                color: '#dc2626',
                cursor: unsavedSaveBusy ? 'default' : 'pointer',
                fontSize: 12,
                padding: '3px 10px',
                borderRadius: 4,
                flexShrink: 0,
                opacity: unsavedSaveBusy ? 0.5 : 1,
                whiteSpace: 'nowrap',
              }}
            >
              Don&apos;t save
            </button>
            <button
              type="button"
              onClick={() => setUnsavedCloseOpen(false)}
              style={{
                background: 'none',
                border: '1px solid rgba(15,23,42,0.1)',
                color: '#64748b',
                cursor: 'pointer',
                fontSize: 12,
                padding: '3px 10px',
                borderRadius: 4,
                flexShrink: 0,
                whiteSpace: 'nowrap',
              }}
            >
              Cancel
            </button>
          </>
        ) : (
          <button
            type="button"
            title="Close this editor. You will be prompted if there are unsaved changes."
            onClick={() => handleCloseClick()}
            disabled={saving || closing || unsavedSaveBusy || !cfg}
            style={{
              background: 'none',
              border: '1px solid rgba(220,38,38,0.35)',
              color: '#dc2626',
              cursor: saving || closing || unsavedSaveBusy || !cfg ? 'default' : 'pointer',
              fontSize: 12,
              padding: '3px 10px',
              borderRadius: 4,
              flexShrink: 0,
              opacity: saving || closing || unsavedSaveBusy || !cfg ? 0.5 : 1,
              whiteSpace: 'nowrap',
            }}
          >
            {closing ? 'Closing…' : 'Close'}
          </button>
        )}
      </div>

      <div style={{ flex: 1, minHeight: 0, position: 'relative', display: 'flex', flexDirection: 'column' }}>
        {!cfg ? (
          err ? (
            <div
              style={{
                flex: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#dc2626',
                padding: 24,
                textAlign: 'center',
              }}
            >
              {err}
            </div>
          ) : (
            <div
              style={{
                flex: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <BusyIcon label="Loading editor" />
            </div>
          )
        ) : (
          <div id="oo-editor-page" style={{ flex: 1, minHeight: 0 }} />
        )}
        {cfg && err ? (
          <div
            className="modalBusyOverlay"
            style={{
              position: 'absolute',
              inset: 0,
              borderRadius: 0,
              background: 'rgba(248, 250, 252, 0.96)',
              zIndex: 2,
            }}
            role="alert"
          >
            <div style={{ color: '#dc2626', padding: 24, textAlign: 'center', maxWidth: 560, lineHeight: 1.45 }}>
              {err}
            </div>
          </div>
        ) : null}
        {saving || unsavedSaveBusy ? (
          <div
            className="modalBusyOverlay"
            style={{ position: 'absolute', inset: 0, borderRadius: 0, zIndex: 3 }}
            role="status"
            aria-live="polite"
          >
            <BusyIcon label="Saving document" />
          </div>
        ) : null}
      </div>
    </div>
  )
}
