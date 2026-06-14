import { useCallback, useEffect, useMemo, useState } from 'react'
import { applyAuthHeaders, apiUrl, formatApiErrorDetail } from './api'
import { DocMimeIcon } from './case/DocCells'
import type { PortalAuthOut, PortalBrowseOut, PortalFileOut, PortalGrantSummaryOut, PortalQuoteDeliveryViewOut, PortalQuoteExchangeOut, PortalSessionOut } from './types'

const PORTAL_FILES_GRID = '32px 1fr 120px 100px 180px'

const PORTAL_TOKEN_KEY = 'canary_portal_token'
const PORTAL_TITLE = 'Canary Portal'

type SignInMode = 'code' | 'email'

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

function uploadFolderForGrant(grant: PortalGrantSummaryOut, subfolder: string): string {
  const root = (grant.folder_path || '').trim()
  const rel = (subfolder || '').trim()
  if (!rel) return root
  return root ? `${root}/${rel}` : rel
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
  const [firmDisplayName, setFirmDisplayName] = useState('')
  const [signInMode, setSignInMode] = useState<SignInMode>('code')
  const [accessCode, setAccessCode] = useState('')
  const [otpEmail, setOtpEmail] = useState('')
  const [otpCode, setOtpCode] = useState('')
  const [otpSent, setOtpSent] = useState(false)
  const [sessionToken, setSessionToken] = useState(() => getStoredPortalToken())
  const [contactName, setContactName] = useState('')
  const [grants, setGrants] = useState<PortalGrantSummaryOut[]>([])
  const [activeCaseId, setActiveCaseId] = useState<string | null>(null)
  const [activeGrantId, setActiveGrantId] = useState<string | null>(null)
  const [browseSubfolder, setBrowseSubfolder] = useState('')
  const [browse, setBrowse] = useState<PortalBrowseOut | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [uploadBusy, setUploadBusy] = useState(false)
  const [previewExchangeBusy, setPreviewExchangeBusy] = useState(false)
  const [quoteExchangeBusy, setQuoteExchangeBusy] = useState(false)
  const [quoteDelivery, setQuoteDelivery] = useState<PortalQuoteDeliveryViewOut | null>(null)
  const [quoteDeclineOpen, setQuoteDeclineOpen] = useState(false)
  const [quoteDeclineReason, setQuoteDeclineReason] = useState('')
  const [quoteRespondBusy, setQuoteRespondBusy] = useState(false)
  const [approvalDeclineOpenId, setApprovalDeclineOpenId] = useState<string | null>(null)
  const [approvalDeclineReason, setApprovalDeclineReason] = useState('')
  const [approvalRespondBusyId, setApprovalRespondBusyId] = useState<string | null>(null)

  const matterGroups = useMemo(() => groupGrantsByMatter(grants), [grants])
  const activeMatter = useMemo(
    () => matterGroups.find((m) => m.caseId === activeCaseId) ?? null,
    [matterGroups, activeCaseId],
  )
  const activeGrant = useMemo(() => grants.find((g) => g.id === activeGrantId) ?? null, [grants, activeGrantId])

  const staffPreview = useMemo(() => {
    if (typeof window === 'undefined') return false
    return new URLSearchParams(window.location.search).get('staff_preview') === '1'
  }, [])

  const loadConfig = useCallback(async () => {
    try {
      const cfg = await portalFetch<{ firm_name: string }>('/portal/config')
      setFirmDisplayName(cfg.firm_name?.trim() ?? '')
    } catch {
      /* optional */
    }
  }, [])

  useEffect(() => {
    document.title = PORTAL_TITLE
  }, [])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const exchange = params.get('preview_exchange')?.trim()
    if (!exchange) return
    void (async () => {
      setPreviewExchangeBusy(true)
      setErr(null)
      try {
        const out = await portalFetch<PortalAuthOut>('/portal/auth/preview-exchange', {
          method: 'POST',
          json: { exchange_token: exchange },
        })
        storePortalToken(out.session_token)
        setSessionToken(out.session_token)
        setContactName(out.contact_name)
        setGrants(out.grants)
        params.delete('preview_exchange')
        const qs = params.toString()
        window.history.replaceState(null, '', `${window.location.pathname}${qs ? `?${qs}` : ''}${window.location.hash}`)
      } catch (e: unknown) {
        storePortalToken('')
        setSessionToken('')
        setErr((e as { message?: string }).message ?? 'Preview link expired or invalid')
      } finally {
        setPreviewExchangeBusy(false)
      }
    })()
  }, [])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const quoteToken = params.get('quote')?.trim()
    if (!quoteToken) return
    void (async () => {
      setQuoteExchangeBusy(true)
      setErr(null)
      try {
        const out = await portalFetch<PortalQuoteExchangeOut>('/portal/quote-exchange', {
          method: 'POST',
          json: { exchange_token: quoteToken },
        })
        storePortalToken(out.session_token)
        setSessionToken(out.session_token)
        setContactName(out.contact_name)
        setGrants(out.grants)
        setQuoteDelivery(out.quote)
        if (out.quote.grant_id) {
          const grant = out.grants.find((g) => g.id === out.quote.grant_id)
          if (grant) {
            setActiveCaseId(grant.case_id)
            setActiveGrantId(grant.id)
          }
        }
        params.delete('quote')
        const qs = params.toString()
        window.history.replaceState(null, '', `${window.location.pathname}${qs ? `?${qs}` : ''}${window.location.hash}`)
      } catch (e: unknown) {
        storePortalToken('')
        setSessionToken('')
        setErr((e as { message?: string }).message ?? 'Quote link expired or invalid')
      } finally {
        setQuoteExchangeBusy(false)
      }
    })()
  }, [])

  const refreshSession = useCallback(async (token: string) => {
    const sess = await portalFetch<PortalSessionOut>('/portal/session', { portalToken: token })
    setContactName(sess.contact_name)
    setGrants(sess.grants)
    return sess
  }, [])

  const loadBrowse = useCallback(async (grantId: string, subfolder: string, token: string) => {
    const q = subfolder ? `?subfolder=${encodeURIComponent(subfolder)}` : ''
    const data = await portalFetch<PortalBrowseOut>(`/portal/grants/${grantId}/browse${q}`, { portalToken: token })
    setBrowse(data)
    setBrowseSubfolder(data.subfolder)
  }, [])

  useEffect(() => {
    void loadConfig()
  }, [loadConfig])

  useEffect(() => {
    const token = sessionToken.trim()
    if (!token || previewExchangeBusy || quoteExchangeBusy) return
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
  }, [sessionToken, refreshSession, previewExchangeBusy, quoteExchangeBusy])

  useEffect(() => {
    const token = sessionToken.trim()
    if (!token || !activeGrantId) return
    void (async () => {
      setBusy(true)
      setErr(null)
      try {
        await loadBrowse(activeGrantId, browseSubfolder, token)
      } catch (e: unknown) {
        setErr((e as { message?: string }).message ?? 'Could not load folder')
      } finally {
        setBusy(false)
      }
    })()
  }, [activeGrantId, sessionToken, browseSubfolder, loadBrowse])

  async function signInWithCode(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setErr(null)
    setInfo(null)
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
      setBrowse(null)
      setBrowseSubfolder('')
      setAccessCode('')
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Sign-in failed')
    } finally {
      setBusy(false)
    }
  }

  async function requestOtp(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setErr(null)
    setInfo(null)
    try {
      await portalFetch('/portal/auth/request-otp', { method: 'POST', json: { email: otpEmail.trim() } })
      setOtpSent(true)
      setInfo('If this e-mail has portal access, a sign-in code has been sent.')
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not send sign-in code')
    } finally {
      setBusy(false)
    }
  }

  async function verifyOtp(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setErr(null)
    setInfo(null)
    try {
      const out = await portalFetch<PortalAuthOut>('/portal/auth/verify-otp', {
        method: 'POST',
        json: { email: otpEmail.trim(), code: otpCode.trim() },
      })
      storePortalToken(out.session_token)
      setSessionToken(out.session_token)
      setContactName(out.contact_name)
      setGrants(out.grants)
      setActiveCaseId(null)
      setActiveGrantId(null)
      setBrowse(null)
      setBrowseSubfolder('')
      setOtpCode('')
      setOtpSent(false)
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
    setBrowse(null)
    setBrowseSubfolder('')
    setQuoteDelivery(null)
    setQuoteDeclineOpen(false)
    setQuoteDeclineReason('')
    setApprovalDeclineOpenId(null)
    setApprovalDeclineReason('')
  }

  async function downloadQuoteFile() {
    if (!quoteDelivery?.grant_id) return
    const token = sessionToken.trim()
    if (!token) return
    setErr(null)
    try {
      const url = apiUrl(
        `/portal/grants/${quoteDelivery.grant_id}/files/${quoteDelivery.file_id}?download=1`,
      )
      const headers = new Headers()
      applyAuthHeaders(headers, token)
      const res = await fetch(url, { headers })
      if (!res.ok) throw new Error(formatApiErrorDetail(await res.text(), res.statusText))
      const blob = await res.blob()
      const obj = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = obj
      a.download = quoteDelivery.original_filename
      a.click()
      URL.revokeObjectURL(obj)
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Download failed')
    }
  }

  async function respondToQuote(accepted: boolean) {
    if (!quoteDelivery) return
    await respondToApproval(quoteDelivery.id, accepted, quoteDeclineReason.trim() || null)
    setQuoteDeclineOpen(false)
    setQuoteDeclineReason('')
  }

  async function respondToApproval(
    deliveryId: string,
    accepted: boolean,
    declineReason: string | null = null,
  ) {
    const token = sessionToken.trim()
    if (!token) return
    setApprovalRespondBusyId(deliveryId)
    setQuoteRespondBusy(true)
    setErr(null)
    try {
      const out = await portalFetch<PortalQuoteDeliveryViewOut>(
        `/portal/quote-deliveries/${deliveryId}/respond`,
        {
          method: 'POST',
          portalToken: token,
          json: {
            accepted,
            decline_reason: accepted ? null : declineReason,
          },
        },
      )
      if (quoteDelivery?.id === deliveryId) setQuoteDelivery(out)
      setApprovalDeclineOpenId(null)
      setApprovalDeclineReason('')
      setInfo(accepted ? 'Thank you — your acceptance has been recorded.' : 'Your response has been recorded.')
      if (activeGrantId) {
        await loadBrowse(activeGrantId, browseSubfolder, token)
      }
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not submit response')
    } finally {
      setApprovalRespondBusyId(null)
      setQuoteRespondBusy(false)
    }
  }

  async function downloadApprovalFile(delivery: PortalQuoteDeliveryViewOut) {
    const grantId = delivery.grant_id ?? activeGrantId
    const token = sessionToken.trim()
    if (!grantId || !token) return
    setErr(null)
    try {
      const url = apiUrl(`/portal/grants/${grantId}/files/${delivery.file_id}?download=1`)
      const headers = new Headers()
      applyAuthHeaders(headers, token)
      const res = await fetch(url, { headers })
      if (!res.ok) throw new Error(formatApiErrorDetail(await res.text(), res.statusText))
      const blob = await res.blob()
      const obj = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = obj
      a.download = delivery.original_filename
      a.click()
      URL.revokeObjectURL(obj)
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Download failed')
    }
  }

  async function openApprovalFile(delivery: PortalQuoteDeliveryViewOut) {
    const grantId = delivery.grant_id ?? activeGrantId
    const token = sessionToken.trim()
    if (!grantId || !token) return
    setErr(null)
    try {
      const url = apiUrl(`/portal/grants/${grantId}/files/${delivery.file_id}`)
      const headers = new Headers()
      applyAuthHeaders(headers, token)
      const res = await fetch(url, { headers })
      if (!res.ok) throw new Error(formatApiErrorDetail(await res.text(), res.statusText))
      const blob = await res.blob()
      const typed = delivery.mime_type ? new Blob([blob], { type: delivery.mime_type }) : blob
      const obj = URL.createObjectURL(typed)
      window.open(obj, '_blank', 'noopener,noreferrer')
      window.setTimeout(() => URL.revokeObjectURL(obj), 60_000)
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not open file')
    }
  }

  function quoteStatusMessage(q: PortalQuoteDeliveryViewOut): string {
    if (q.status === 'accepted') return 'You accepted this quote.'
    if (q.status === 'declined') {
      return q.decline_reason ? `You declined this quote: ${q.decline_reason}` : 'You declined this quote.'
    }
    if (q.status === 'superseded') return 'This quote has been revised. Contact your firm for an updated copy.'
    if (!q.can_respond) return 'This quote is no longer awaiting a response.'
    return 'Please review the quote below, then accept or decline.'
  }

  async function uploadFiles(fileList: FileList | null) {
    if (!fileList?.length || !activeGrantId || !activeGrant?.can_upload) return
    const token = sessionToken.trim()
    if (!token) return
    setUploadBusy(true)
    setErr(null)
    const folder = uploadFolderForGrant(activeGrant, browseSubfolder)
    try {
      for (const file of Array.from(fileList)) {
        const fd = new FormData()
        fd.append('upload', file)
        fd.append('folder', folder)
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
      await loadBrowse(activeGrantId, browseSubfolder, token)
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
      const typed = file.mime_type ? new Blob([blob], { type: file.mime_type }) : blob
      const obj = URL.createObjectURL(typed)
      window.open(obj, '_blank', 'noopener,noreferrer')
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

  function openGrant(grantId: string) {
    setActiveGrantId(grantId)
    setBrowseSubfolder('')
    setBrowse(null)
  }

  function navigateToSubfolder(name: string) {
    const next = browseSubfolder ? `${browseSubfolder}/${name}` : name
    setBrowseSubfolder(next)
  }

  function navigateBreadcrumb(index: number) {
    if (index < 0) {
      setBrowseSubfolder('')
      return
    }
    const crumbs = browse?.breadcrumb ?? []
    setBrowseSubfolder(crumbs.slice(0, index + 1).join('/'))
  }

  if (previewExchangeBusy || quoteExchangeBusy) {
    return (
      <div className="portalShell">
        <div className="portalCard card">
          <h1>{PORTAL_TITLE}</h1>
          <div className="muted" style={{ marginTop: 12 }}>
            {quoteExchangeBusy ? 'Opening quote…' : 'Opening preview…'}
          </div>
        </div>
      </div>
    )
  }

  if (!sessionToken) {
    return (
      <div className="portalShell">
        <div className="portalCard card">
          <h1>{PORTAL_TITLE}</h1>
          {firmDisplayName ? <p className="muted" style={{ marginTop: 4 }}>{firmDisplayName}</p> : null}
          <p className="muted">Sign in with your access code or e-mail one-time code.</p>

          {staffPreview ? (
            <div className="notice portalStaffPreviewBanner">
              Staff preview — choose a contact from the matter Portal panel, or sign in manually with an access code or
              e-mail code.
            </div>
          ) : null}

          <div className="portalSignInTabs row" style={{ gap: 8, marginBottom: 16 }}>
            <button
              type="button"
              className={`btn${signInMode === 'code' ? ' primary' : ''}`}
              onClick={() => {
                setSignInMode('code')
                setErr(null)
                setInfo(null)
              }}
            >
              Access code
            </button>
            <button
              type="button"
              className={`btn${signInMode === 'email' ? ' primary' : ''}`}
              onClick={() => {
                setSignInMode('email')
                setErr(null)
                setInfo(null)
              }}
            >
              E-mail code
            </button>
          </div>

          {signInMode === 'code' ? (
            <form className="stack" onSubmit={(e) => void signInWithCode(e)}>
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
              {info ? <div className="notice">{info}</div> : null}
              <button type="submit" className="btn primary" disabled={busy || !accessCode.trim()}>
                {busy ? 'Signing in…' : 'Sign in'}
              </button>
            </form>
          ) : (
            <form className="stack" onSubmit={(e) => void (otpSent ? verifyOtp(e) : requestOtp(e))}>
              <label className="stack" style={{ gap: 6 }}>
                <span>E-mail address</span>
                <input
                  type="email"
                  value={otpEmail}
                  onChange={(e) => setOtpEmail(e.target.value)}
                  autoComplete="email"
                  autoFocus
                  disabled={busy || otpSent}
                />
              </label>
              {otpSent ? (
                <label className="stack" style={{ gap: 6 }}>
                  <span>Sign-in code</span>
                  <input
                    value={otpCode}
                    onChange={(e) => setOtpCode(e.target.value)}
                    autoComplete="one-time-code"
                    placeholder="123456"
                    disabled={busy}
                  />
                </label>
              ) : null}
              {err ? <div className="error">{err}</div> : null}
              {info ? <div className="notice">{info}</div> : null}
              {otpSent ? (
                <>
                  <button type="submit" className="btn primary" disabled={busy || !otpCode.trim()}>
                    {busy ? 'Signing in…' : 'Verify code'}
                  </button>
                  <button
                    type="button"
                    className="btn"
                    disabled={busy}
                    onClick={() => {
                      setOtpSent(false)
                      setOtpCode('')
                      setInfo(null)
                    }}
                  >
                    Use a different e-mail
                  </button>
                </>
              ) : (
                <button type="submit" className="btn primary" disabled={busy || !otpEmail.trim()}>
                  {busy ? 'Sending…' : 'Send sign-in code'}
                </button>
              )}
            </form>
          )}
        </div>
      </div>
    )
  }

  const files = browse?.files ?? []
  const subfolders = browse?.subfolders ?? []
  const pendingApprovals = (browse?.pending_approvals ?? []).filter((d) => d.can_respond)

  return (
    <div className="portalShell">
      <div className="portalCard card portalCardWide">
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
          <div>
            <h1 style={{ margin: 0 }}>{PORTAL_TITLE}</h1>
            {firmDisplayName ? <div className="muted">{firmDisplayName}</div> : null}
            <div className="muted">Signed in as {contactName}</div>
          </div>
          <button type="button" className="btn" onClick={signOut}>
            Sign out
          </button>
        </div>

        {err ? <div className="error" style={{ marginTop: 12 }}>{err}</div> : null}
        {info ? <div className="notice" style={{ marginTop: 12 }}>{info}</div> : null}

        {quoteDelivery && !activeGrantId ? (
          <div className="portalQuotePanel card" style={{ marginTop: 16, padding: 16 }}>
            <h2 style={{ marginTop: 0, fontSize: 18 }}>Quote</h2>
            <div className="listTitle">{quoteDelivery.original_filename}</div>
            <p className="muted" style={{ marginBottom: 12 }}>{quoteStatusMessage(quoteDelivery)}</p>
            <div className="row" style={{ gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
              <button type="button" className="btn" onClick={() => void downloadQuoteFile()}>
                Download
              </button>
            </div>
            {quoteDelivery.can_respond ? (
              <>
                {!quoteDeclineOpen ? (
                  <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                    <button
                      type="button"
                      className="btn primary"
                      disabled={quoteRespondBusy}
                      onClick={() => void respondToQuote(true)}
                    >
                      Accept quote
                    </button>
                    <button
                      type="button"
                      className="btn"
                      disabled={quoteRespondBusy}
                      onClick={() => setQuoteDeclineOpen(true)}
                    >
                      Decline
                    </button>
                  </div>
                ) : (
                  <div className="stack" style={{ gap: 8 }}>
                    <label className="field">
                      <span>Reason for declining (optional)</span>
                      <textarea
                        className="input"
                        rows={3}
                        value={quoteDeclineReason}
                        onChange={(e) => setQuoteDeclineReason(e.target.value)}
                      />
                    </label>
                    <div className="row" style={{ gap: 8 }}>
                      <button
                        type="button"
                        className="btn primary"
                        disabled={quoteRespondBusy}
                        onClick={() => void respondToQuote(false)}
                      >
                        {quoteRespondBusy ? 'Submitting…' : 'Submit decline'}
                      </button>
                      <button
                        type="button"
                        className="btn"
                        disabled={quoteRespondBusy}
                        onClick={() => {
                          setQuoteDeclineOpen(false)
                          setQuoteDeclineReason('')
                        }}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </>
            ) : null}
          </div>
        ) : null}

        {staffPreview ? (
          <div className="notice portalStaffPreviewBanner" style={{ marginTop: 12 }}>
            Staff preview — viewing as {contactName}. This is what this contact sees in the portal.
          </div>
        ) : null}

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
                  onClick={() => openGrant(g.id)}
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
                  setBrowse(null)
                  setBrowseSubfolder('')
                }}
              >
                ← Folders
              </button>
              <h2 style={{ margin: 0, flex: 1 }}>{activeGrant?.folder_label ?? 'Documents'}</h2>
              {activeGrant?.can_download && (files.length > 0 || subfolders.length > 0) ? (
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

            <div className="portalBreadcrumb muted" style={{ marginBottom: 12, display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
              <button type="button" className="btnLink" onClick={() => navigateBreadcrumb(-1)}>
                {activeGrant?.folder_label ?? 'Root'}
              </button>
              {(browse?.breadcrumb ?? []).map((part, idx) => (
                <span key={`${part}-${idx}`} style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
                  <span aria-hidden>/</span>
                  <button type="button" className="btnLink" onClick={() => navigateBreadcrumb(idx)}>
                    {part}
                  </button>
                </span>
              ))}
            </div>

            {busy && !browse ? <div className="muted">Loading…</div> : null}

            {pendingApprovals.length > 0 ? (
              <div className="portalPendingApprovals" style={{ marginBottom: 16 }}>
                <h3 style={{ margin: '0 0 8px', fontSize: 16 }}>Documents awaiting your approval</h3>
                <div className="table portalFilesTable">
                  <div className="tr th" style={{ gridTemplateColumns: PORTAL_FILES_GRID }}>
                    <div className="thCell portalFilesTableIconCol" aria-hidden />
                    <div className="thCell">Name</div>
                    <div className="thCell">Folder</div>
                    <div className="thCell">Size</div>
                    <div className="thCell">Actions</div>
                  </div>
                  {pendingApprovals.map((d) => {
                    const declineOpen = approvalDeclineOpenId === d.id
                    const respondBusy = approvalRespondBusyId === d.id
                    return (
                      <div key={d.id} className="stack" style={{ gap: 0 }}>
                        <div className="tr portalPendingApprovalRow" style={{ gridTemplateColumns: PORTAL_FILES_GRID }}>
                          <div className="td portalFilesTableIconCol">
                            <span className="docsTypeIcon" aria-hidden>
                              <DocMimeIcon mime={d.mime_type ?? ''} filename={d.original_filename} />
                            </span>
                          </div>
                          <div className="td">{d.original_filename}</div>
                          <div className="td muted">{d.folder_display?.trim() || '—'}</div>
                          <div className="td muted">{formatBytes(d.size_bytes ?? 0)}</div>
                          <div className="td row" style={{ gap: 6, flexWrap: 'wrap' }}>
                            {activeGrant?.can_download ? (
                              <>
                                <button type="button" className="btn" disabled={respondBusy} onClick={() => void openApprovalFile(d)}>
                                  Open
                                </button>
                                <button type="button" className="btn" disabled={respondBusy} onClick={() => void downloadApprovalFile(d)}>
                                  Download
                                </button>
                              </>
                            ) : null}
                            {!declineOpen ? (
                              <>
                                <button
                                  type="button"
                                  className="btn primary"
                                  disabled={respondBusy}
                                  onClick={() => void respondToApproval(d.id, true)}
                                >
                                  Accept
                                </button>
                                <button
                                  type="button"
                                  className="btn"
                                  disabled={respondBusy}
                                  onClick={() => {
                                    setApprovalDeclineOpenId(d.id)
                                    setApprovalDeclineReason('')
                                  }}
                                >
                                  Decline
                                </button>
                              </>
                            ) : null}
                          </div>
                        </div>
                        {declineOpen ? (
                          <div className="portalPendingApprovalDecline card stack" style={{ margin: '0 0 8px', padding: 12, gap: 8 }}>
                            <label className="field">
                              <span>Reason for declining (optional)</span>
                              <textarea
                                className="input"
                                rows={2}
                                value={approvalDeclineReason}
                                onChange={(e) => setApprovalDeclineReason(e.target.value)}
                              />
                            </label>
                            <div className="row" style={{ gap: 8 }}>
                              <button
                                type="button"
                                className="btn primary"
                                disabled={respondBusy}
                                onClick={() => void respondToApproval(d.id, false, approvalDeclineReason.trim() || null)}
                              >
                                {respondBusy ? 'Submitting…' : 'Submit decline'}
                              </button>
                              <button
                                type="button"
                                className="btn"
                                disabled={respondBusy}
                                onClick={() => {
                                  setApprovalDeclineOpenId(null)
                                  setApprovalDeclineReason('')
                                }}
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        ) : null}
                      </div>
                    )
                  })}
                </div>
              </div>
            ) : null}

            <div className="table portalFilesTable">
              <div className="tr th" style={{ gridTemplateColumns: PORTAL_FILES_GRID }}>
                <div className="thCell portalFilesTableIconCol" aria-hidden />
                <div className="thCell">Name</div>
                <div className="thCell">Folder</div>
                <div className="thCell">Size</div>
                <div className="thCell">Actions</div>
              </div>
              {subfolders.map((name) => (
                <div key={`dir-${name}`} className="tr rowbtn" style={{ gridTemplateColumns: PORTAL_FILES_GRID }} onClick={() => navigateToSubfolder(name)}>
                  <div className="td portalFilesTableIconCol">
                    <span className="docsTypeIcon" aria-hidden>📁</span>
                  </div>
                  <div className="td">{name}</div>
                  <div className="td muted">—</div>
                  <div className="td muted">—</div>
                  <div className="td muted">Folder</div>
                </div>
              ))}
              {files.map((f) => (
                <div key={f.id} className="tr" style={{ gridTemplateColumns: PORTAL_FILES_GRID }}>
                  <div className="td portalFilesTableIconCol">
                    <span className="docsTypeIcon" aria-hidden>
                      <DocMimeIcon mime={f.mime_type} filename={f.original_filename} />
                    </span>
                  </div>
                  <div className="td">{f.original_filename}</div>
                  <div className="td muted">{f.folder_display || '—'}</div>
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
              {!busy && subfolders.length === 0 && files.length === 0 ? (
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
