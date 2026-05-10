import { useEffect, useRef, useState } from 'react'
import { apiFetch } from './api'
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
}

type EditorTarget =
  | { mode: 'case'; caseId: string; fileId: string }
  | { mode: 'precedent'; precedentId: string }

function parseEditorPath(): EditorTarget | null {
  const parts = window.location.pathname.split('/').filter(Boolean)
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

function loadOoScript(base: string): Promise<void> {
  const g = window as Window & { DocsAPI?: unknown }
  if (g.DocsAPI) return Promise.resolve()
  const url = `${base}/web-apps/apps/api/documents/api.js`
  return new Promise((resolve, reject) => {
    const s = document.createElement('script')
    s.src = url
    s.async = true
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
  const apiRef = useRef<DocsApiEditor | null>(null)
  const pdfExportTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  /** After downloadAs('pdf'): open PDF in new tab (export) vs Canary print-ui tab (print). */
  const pendingDownloadAsRef = useRef<'export' | 'print' | null>(null)
  const printTabRef = useRef<Window | null>(null)
  const token = localStorage.getItem('token') ?? undefined

  // Fetch editor config on mount. AbortController avoids overlapping onlyoffice-config calls
  // (React Strict Mode remount, fast tab switches) minting extra WebDAV sessions server-side.
  useEffect(() => {
    if (!params) {
      setErr('Invalid editor URL — expected /editor/{caseId}/{fileId} or /editor/precedent/{precedentId}')
      return
    }
    const ac = new AbortController()
    const configUrl = params.mode === 'precedent'
      ? `/precedents/${params.precedentId}/onlyoffice-config`
      : `/cases/${params.caseId}/files/${params.fileId}/onlyoffice-config`
    apiFetch<OoConfig>(configUrl, { token, signal: ac.signal })
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
        const g = window as Window & {
          DocsAPI?: { DocEditor: new (id: string, c: Record<string, unknown>) => DocsApiEditor }
        }
        if (!g.DocsAPI) {
          if (active) setErr('ONLYOFFICE script loaded but DocsAPI is missing')
          return
        }
        apiRef.current?.destroyEditor?.()
        try {
          apiRef.current = new g.DocsAPI.DocEditor('oo-editor-page', {
          documentServerUrl: `${base.replace(/\/$/, '')}/`,
          token: cfg.token,
          document: cfg.document,
          editorConfig: cfg.editor_config,
          type: 'desktop',
          documentType: cfg.document_type,
          width: '100%',
          height: '100%',
          events: {
            onAppReady: () => console.info('[ONLYOFFICE] onAppReady'),
            onDocumentStateChange: (event: unknown) => {
              if (!active) return
              const v = parseOnlyofficeDocumentStateEvent(event)
              if (v === true) {
                hasUncommittedOoEditsRef.current = true
                setDocumentDirty(true)
              } else if (v === false) {
                setDocumentDirty(hasUncommittedOoEditsRef.current)
              }
            },
            onDocumentReady: () => {
              console.info('[ONLYOFFICE] onDocumentReady — document rendered OK')
              if (active) {
                hasUncommittedOoEditsRef.current = false
                setDocumentDirty(false)
              }
            },
            onWarning: (event: unknown) => console.warn('[ONLYOFFICE onWarning]', event),
            onError: (event: unknown) => {
              const raw = JSON.stringify(event)
              console.error('[ONLYOFFICE onError] RAW:', raw)
              if (active) setErr(`${formatOoError(event)} | raw: ${raw}`)
            },
            // Required for downloadAs(); Canary Print + Export PDF both use conversion URLs under /cache/files/.
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
                        'Print staging failed. Try Export PDF instead.'
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

              if (typeof url === 'string' && url.length > 0 && mode === 'export') {
                window.open(url, '_blank', 'noopener,noreferrer')
              }
              setPdfExportBusy(false)
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

  async function performSave(): Promise<boolean> {
    if (!params || !cfg) return false
    const docKey = (cfg.document as { key?: string }).key ?? ''
    if (!docKey) {
      setErr('Editor key missing; cannot save safely. Please reload and try again.')
      return false
    }
    try {
      if (params.mode === 'case') {
        await apiFetch(
          `/cases/${params.caseId}/files/${params.fileId}/oo-force-save?doc_key=${encodeURIComponent(docKey)}`,
          { method: 'POST', token },
        )
        await apiFetch(`/cases/${params.caseId}/files/${params.fileId}/publish-compose`, {
          method: 'POST',
          token,
        })
        notifyCaseFilesChangedIfCase()
      } else {
        await apiFetch(
          `/precedents/${params.precedentId}/oo-force-save?doc_key=${encodeURIComponent(docKey)}`,
          { method: 'POST', token },
        )
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

  async function performCloseClean() {
    if (!params || closing) return
    setClosing(true)
    try {
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
            color: '#64748b',
            fontSize: 13,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            flex: 1,
          }}
        >
          {filename}
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
          title="Download ONLYOFFICE’s PDF in a new tab (browser PDF handler)."
          onClick={() => {
            if (pdfExportBusy || !apiRef.current?.downloadAs || saving || closing || unsavedSaveBusy) return
            pendingDownloadAsRef.current = 'export'
            setPdfExportBusy(true)
            if (pdfExportTimeoutRef.current !== undefined) clearTimeout(pdfExportTimeoutRef.current)
            pdfExportTimeoutRef.current = window.setTimeout(() => {
              pdfExportTimeoutRef.current = undefined
              pendingDownloadAsRef.current = null
              setPdfExportBusy(false)
            }, 120_000)
            try {
              apiRef.current.downloadAs('pdf')
            } catch {
              if (pdfExportTimeoutRef.current !== undefined) clearTimeout(pdfExportTimeoutRef.current)
              pdfExportTimeoutRef.current = undefined
              pendingDownloadAsRef.current = null
              setPdfExportBusy(false)
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
          {pdfExportBusy ? 'Preparing PDF…' : 'Export PDF'}
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

      {err ? (
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
      ) : !cfg ? (
        <div
          style={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#64748b',
          }}
        >
          Loading editor…
        </div>
      ) : (
        <div id="oo-editor-page" style={{ flex: 1, minHeight: 0 }} />
      )}
    </div>
  )
}
