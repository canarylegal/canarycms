import { useCallback, useEffect, useMemo, useState } from 'react'
import { applyAuthHeaders, apiUrl, formatApiErrorDetail } from './api'
import type { PortalAuthOut, PortalFileOut, PortalGrantSummaryOut, PortalSessionOut } from './types'

const PORTAL_TOKEN_KEY = 'canary_portal_token'

function getStoredPortalToken(): string {
  try {
    return sessionStorage.getItem(PORTAL_TOKEN_KEY)?.trim() ?? ''
  } catch {
    return ''
  }
}

function storePortalToken(token: string) {
  try {
    if (token) sessionStorage.setItem(PORTAL_TOKEN_KEY, token)
    else sessionStorage.removeItem(PORTAL_TOKEN_KEY)
  } catch {
    /* ignore */
  }
}

async function portalFetch<T>(
  path: string,
  opts: RequestInit & { portalToken?: string; json?: unknown } = {},
): Promise<T> {
  const { portalToken, json, ...rest } = opts
  const headers = new Headers(rest.headers ?? {})
  const auth = (portalToken ?? getStoredPortalToken()).trim()
  if (auth) applyAuthHeaders(headers, auth)
  if (json !== undefined) headers.set('Content-Type', 'application/json')
  const res = await fetch(apiUrl(path), { ...rest, headers, body: json !== undefined ? JSON.stringify(json) : rest.body })
  const body = await res.text()
  let parsed: unknown = null
  if (body) {
    try {
      parsed = JSON.parse(body)
    } catch {
      parsed = body
    }
  }
  if (!res.ok) {
    throw new Error(formatApiErrorDetail(parsed, res.statusText, apiUrl(path)))
  }
  return parsed as T
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

type MatterGroup = {
  caseId: string
  caseTitle: string
  grants: PortalGrantSummaryOut[]
}

function groupGrantsByMatter(grants: PortalGrantSummaryOut[]): MatterGroup[] {
  const map = new Map<string, MatterGroup>()
  for (const g of grants) {
    let group = map.get(g.case_id)
    if (!group) {
      group = { caseId: g.case_id, caseTitle: g.case_title, grants: [] }
      map.set(g.case_id, group)
    }
    group.grants.push(g)
  }
  return Array.from(map.values()).sort((a, b) => a.caseTitle.localeCompare(b.caseTitle))
}

export default function PortalPage() {
  const [firmName, setFirmName] = useState('Client portal')
  const [accessCode, setAccessCode] = useState('')
  const [sessionToken, setSessionToken] = useState(() => getStoredPortalToken())
  const [contactName, setContactName] = useState('')
  const [grants, setGrants] = useState<PortalGrantSummaryOut[]>([])
  const [activeCaseId, setActiveCaseId] = useState<string | null>(null)
  const [activeGrantId, setActiveGrantId] = useState<string | null>(null)
  const [files, setFiles] = useState<PortalFileOut[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [uploadBusy, setUploadBusy] = useState(false)

  const matterGroups = useMemo(() => groupGrantsByMatter(grants), [grants])
  const activeMatter = useMemo(
    () => matterGroups.find((m) => m.caseId === activeCaseId) ?? null,
    [matterGroups, activeCaseId],
  )
  const activeGrant = useMemo(() => grants.find((g) => g.id === activeGrantId) ?? null, [grants, activeGrantId])

  const loadConfig = useCallback(async () => {
    try {
      const cfg = await portalFetch<{ firm_name: string }>('/portal/config')
      if (cfg.firm_name?.trim()) setFirmName(cfg.firm_name.trim())
    } catch {
      /* optional */
    }
  }, [])

  const refreshSession = useCallback(async (token: string) => {
    const sess = await portalFetch<PortalSessionOut>('/portal/session', { portalToken: token })
    setContactName(sess.contact_name)
    setGrants(sess.grants)
    return sess
  }, [])

  const loadFiles = useCallback(async (grantId: string, token: string) => {
    const rows = await portalFetch<PortalFileOut[]>(`/portal/grants/${grantId}/files`, { portalToken: token })
    setFiles(rows)
  }, [])

  useEffect(() => {
    void loadConfig()
  }, [loadConfig])

  useEffect(() => {
    const token = sessionToken.trim()
    if (!token) return
    void (async () => {
      setBusy(true)
      setErr(null)
      try {
        await refreshSession(token)
      } catch (e: unknown) {
        storePortalToken('')
        setSessionToken('')
        setErr((e as { message?: string }).message ?? 'Session expired')
      } finally {
        setBusy(false)
      }
    })()
  }, [sessionToken, refreshSession])

  useEffect(() => {
    const token = sessionToken.trim()
    if (!token || !activeGrantId) return
    void (async () => {
      setBusy(true)
      setErr(null)
      try {
        await loadFiles(activeGrantId, token)
      } catch (e: unknown) {
        setErr((e as { message?: string }).message ?? 'Could not load files')
      } finally {
        setBusy(false)
      }
    })()
  }, [activeGrantId, sessionToken, loadFiles])

  async function signIn(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setErr(null)
    try {
      const out = await portalFetch<PortalAuthOut>('/portal/auth', {
        method: 'POST',
        json: { access_code: accessCode },
      })
      storePortalToken(out.session_token)
      setSessionToken(out.session_token)
      setContactName(out.contact_name)
      setGrants(out.grants)
      setActiveCaseId(null)
      setActiveGrantId(null)
      setFiles([])
      setAccessCode('')
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Sign-in failed')
    } finally {
      setBusy(false)
    }
  }

  function signOut() {
    storePortalToken('')
    setSessionToken('')
    setContactName('')
    setGrants([])
    setActiveCaseId(null)
    setActiveGrantId(null)
    setFiles([])
  }

  async function uploadFiles(fileList: FileList | null) {
    if (!fileList?.length || !activeGrantId || !activeGrant?.can_upload) return
    const token = sessionToken.trim()
    if (!token) return
    setUploadBusy(true)
    setErr(null)
    try {
      for (const file of Array.from(fileList)) {
        const fd = new FormData()
        fd.append('upload', file)
        fd.append('folder', '')
        const headers = new Headers()
        applyAuthHeaders(headers, token)
        const res = await fetch(apiUrl(`/portal/grants/${activeGrantId}/files`), { method: 'POST', headers, body: fd })
        if (!res.ok) {
          const text = await res.text()
          let parsed: unknown = text
          try {
            parsed = JSON.parse(text)
          } catch {
            /* keep text */
          }
          throw new Error(formatApiErrorDetail(parsed, res.statusText))
        }
      }
      await loadFiles(activeGrantId, token)
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Upload failed')
    } finally {
      setUploadBusy(false)
    }
  }

  async function fetchFileBlob(file: PortalFileOut, download: boolean): Promise<Blob> {
    const token = sessionToken.trim()
    if (!token || !activeGrantId) throw new Error('Not signed in')
    const q = download ? '?download=1' : ''
    const url = apiUrl(`/portal/grants/${activeGrantId}/files/${file.id}${q}`)
    const headers = new Headers()
    applyAuthHeaders(headers, token)
    const res = await fetch(url, { headers })
    if (!res.ok) {
      const text = await res.text()
      let parsed: unknown = text
      try {
        parsed = JSON.parse(text)
      } catch {
        /* keep text */
      }
      throw new Error(formatApiErrorDetail(parsed, res.statusText))
    }
    return res.blob()
  }

  async function openFile(file: PortalFileOut) {
    setErr(null)
    try {
      const blob = await fetchFileBlob(file, false)
      const obj = URL.createObjectURL(blob)
      const opened = window.open(obj, '_blank', 'noopener')
      if (!opened) setErr('Pop-up blocked — allow pop-ups to open files.')
      window.setTimeout(() => URL.revokeObjectURL(obj), 60_000)
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not open file')
    }
  }

  async function downloadFile(file: PortalFileOut) {
    setErr(null)
    try {
      const blob = await fetchFileBlob(file, true)
      const obj = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = obj
      a.download = file.original_filename
      a.click()
      URL.revokeObjectURL(obj)
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Download failed')
    }
  }

  async function downloadAllFiles() {
    const token = sessionToken.trim()
    if (!token || !activeGrantId) return
    setBusy(true)
    setErr(null)
    try {
      const url = apiUrl(`/portal/grants/${activeGrantId}/files/download-zip`)
      const headers = new Headers()
      applyAuthHeaders(headers, token)
      const res = await fetch(url, { headers })
      if (!res.ok) {
        const text = await res.text()
        let parsed: unknown = text
        try {
          parsed = JSON.parse(text)
        } catch {
          /* keep text */
        }
        throw new Error(formatApiErrorDetail(parsed, res.statusText))
      }
      const blob = await res.blob()
      const obj = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = obj
      a.download = `${activeGrant?.folder_label ?? 'documents'}.zip`
      a.click()
      URL.revokeObjectURL(obj)
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Download failed')
    } finally {
      setBusy(false)
    }
  }

  if (!sessionToken) {
    return (
      <div className="portalShell">
        <div className="portalCard card">
          <h1>{firmName}</h1>
          <p className="muted">Enter your personal access code to view and upload documents.</p>
          <form className="stack" onSubmit={(e) => void signIn(e)}>
            <label className="stack" style={{ gap: 6 }}>
              <span>Access code</span>
              <input
                value={accessCode}
                onChange={(e) => setAccessCode(e.target.value)}
                autoComplete="off"
                autoFocus
                placeholder="XXXX-XXXX-XXXX"
                disabled={busy}
              />
            </label>
            {err ? <div className="error">{err}</div> : null}
            <button type="submit" className="btn primary" disabled={busy || !accessCode.trim()}>
              {busy ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        </div>
      </div>
    )
  }

  return (
    <div className="portalShell">
      <div className="portalCard card portalCardWide">
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
          <div>
            <h1 style={{ margin: 0 }}>{firmName}</h1>
            <div className="muted">Signed in as {contactName}</div>
          </div>
          <button type="button" className="btn" onClick={signOut}>
            Sign out
          </button>
        </div>

        {err ? <div className="error" style={{ marginTop: 12 }}>{err}</div> : null}

        {!activeCaseId && !activeGrantId ? (
          <div style={{ marginTop: 20 }}>
            <h2 style={{ marginTop: 0 }}>Your matters</h2>
            {matterGroups.length === 0 ? <div className="muted">No matters are available.</div> : null}
            <div className="list">
              {matterGroups.map((m) => (
                <button
                  key={m.caseId}
                  type="button"
                  className="listCard rowbtn"
                  style={{ width: '100%', textAlign: 'left' }}
                  onClick={() => setActiveCaseId(m.caseId)}
                >
                  <div className="listTitle">{m.caseTitle}</div>
                  <div className="muted">
                    {m.grants.length} shared {m.grants.length === 1 ? 'folder' : 'folders'}
                  </div>
                </button>
              ))}
            </div>
          </div>
        ) : activeCaseId && !activeGrantId ? (
          <div style={{ marginTop: 20 }}>
            <div className="row" style={{ gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
              <button type="button" className="btn" onClick={() => setActiveCaseId(null)}>
                ← All matters
              </button>
              <h2 style={{ margin: 0, flex: 1 }}>{activeMatter?.caseTitle ?? 'Matter'}</h2>
            </div>
            {activeMatter && activeMatter.grants.length === 0 ? <div className="muted">No folders are shared for this matter.</div> : null}
            <div className="list">
              {activeMatter?.grants.map((g) => (
                <button
                  key={g.id}
                  type="button"
                  className="listCard rowbtn"
                  style={{ width: '100%', textAlign: 'left' }}
                  onClick={() => setActiveGrantId(g.id)}
                >
                  <div className="listTitle">{g.folder_label}</div>
                  <div className="muted">
                    {g.can_download ? 'View & download' : 'View'}
                    {g.can_upload ? ' · Upload allowed' : ''}
                  </div>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div style={{ marginTop: 20 }}>
            <div className="row" style={{ gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
              <button
                type="button"
                className="btn"
                onClick={() => {
                  setActiveGrantId(null)
                  setFiles([])
                }}
              >
                ← Folders
              </button>
              <h2 style={{ margin: 0, flex: 1 }}>{activeGrant?.folder_label ?? 'Documents'}</h2>
              {activeGrant?.can_download && files.length > 0 ? (
                <button type="button" className="btn" disabled={busy} onClick={() => void downloadAllFiles()}>
                  Download all
                </button>
              ) : null}
              {activeGrant?.can_upload ? (
                <label className="btn primary" style={{ cursor: uploadBusy ? 'wait' : 'pointer' }}>
                  {uploadBusy ? 'Uploading…' : 'Upload files'}
                  <input
                    type="file"
                    multiple
                    hidden
                    disabled={uploadBusy}
                    onChange={(e) => {
                      void uploadFiles(e.target.files)
                      e.target.value = ''
                    }}
                  />
                </label>
              ) : null}
            </div>
            {activeMatter ? <div className="muted" style={{ marginBottom: 12 }}>{activeMatter.caseTitle}</div> : null}

            {busy && files.length === 0 ? <div className="muted">Loading files…</div> : null}
            <div className="table portalFilesTable">
              <div className="tr th" style={{ gridTemplateColumns: '1fr 100px 180px' }}>
                <div className="thCell">Name</div>
                <div className="thCell">Size</div>
                <div className="thCell">Actions</div>
              </div>
              {files.map((f) => (
                <div key={f.id} className="tr" style={{ gridTemplateColumns: '1fr 100px 180px' }}>
                  <div className="td">{f.original_filename}</div>
                  <div className="td muted">{formatBytes(f.size_bytes)}</div>
                  <div className="td row" style={{ gap: 6, flexWrap: 'wrap' }}>
                    {activeGrant?.can_download ? (
                      <>
                        <button type="button" className="btn" onClick={() => void openFile(f)}>
                          Open
                        </button>
                        <button type="button" className="btn" onClick={() => void downloadFile(f)}>
                          Download
                        </button>
                      </>
                    ) : (
                      '—'
                    )}
                  </div>
                </div>
              ))}
              {!busy && files.length === 0 ? (
                <div className="muted" style={{ padding: 12 }}>
                  No files in this folder yet.
                </div>
              ) : null}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
