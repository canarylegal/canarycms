import { useCallback, useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from 'react'
import { applyAuthHeaders, apiUrl, browserAbsoluteApiUrl, formatApiErrorDetail } from './api'
import { DocMimeIcon } from './case/DocCells'
import { decodeFolderPathForDisplay, decodeFolderPathSegment } from './case/folderPathCodec'
import { PortalCanarySignPanel } from './PortalCanarySignPanel'
import { PortalFormFillPanel } from './PortalFormFillPanel'
import { PortalQuotePdfViewer } from './PortalQuotePdfViewer'
import { PortalLayout, type PortalBrandingConfig } from './portal/PortalBranding'
import type {
  PortalAuthOut,
  PortalBrowseOut,
  PortalCanarySignExchangeOut,
  PortalCanarySignOut,
  PortalClientActionItemOut,
  PortalClientActionsOut,
  PortalDocusignSigningOut,
  PortalFileOut,
  PortalFormExchangeOut,
  PortalFormPendingOut,
  PortalGrantSummaryOut,
  PortalQuoteDeliveryViewOut,
  PortalQuoteExchangeOut,
  PortalSessionOut,
} from './types'

import { portalRequestError, PortalRequestError, type PortalDraft } from './portal/sessionErrors'

const PORTAL_FILES_GRID = '36px minmax(0, 1fr) 72px max-content'

const PORTAL_TOKEN_KEY = 'canary_portal_token'

const DEFAULT_PORTAL_CONFIG: PortalBrandingConfig = {
  firm_name: '',
  portal_title: 'Client Portal',
  portal_logo_url: null,
  portal_logo_enabled: true,
  portal_background_color: null,
  portal_background_url: null,
  portal_font_color: null,
  portal_background_on_signed_in: true,
}

type SignInMode = 'code' | 'reset'

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
  opts: RequestInit & { portalToken?: string; json?: unknown; isCurrent?: () => boolean } = {},
): Promise<T> {
  const { portalToken, json, isCurrent, ...rest } = opts
  const headers = new Headers(rest.headers ?? {})
  const auth = (portalToken ?? getStoredPortalToken()).trim()
  if (auth) applyAuthHeaders(headers, auth)
  if (json !== undefined) headers.set('Content-Type', 'application/json')
  const res = await fetch(apiUrl(path), { ...rest, headers, body: json !== undefined ? JSON.stringify(json) : rest.body })
  const body = await res.text()
  if (isCurrent && !isCurrent()) throw new Error('Superseded portal request')
  let parsed: unknown = null
  if (body) {
    try {
      parsed = JSON.parse(body)
    } catch {
      parsed = body
    }
  }
  if (!res.ok) {
    throw portalRequestError(res.status, formatApiErrorDetail(parsed, res.statusText, apiUrl(path)), auth)
  }
  return parsed as T
}

function portalGrantFolderLabel(label: string | null | undefined): string {
  const raw = (label ?? '').trim()
  if (!raw) return 'Documents'
  return decodeFolderPathForDisplay(raw)
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

function buildMatterGroups(
  grants: PortalGrantSummaryOut[],
  forms: PortalFormPendingOut[],
  quotes: PortalQuoteDeliveryViewOut[],
  clientActions: PortalClientActionsOut | null = null,
): MatterGroup[] {
  const map = new Map<string, MatterGroup>()
  for (const g of grants) {
    let group = map.get(g.case_id)
    if (!group) {
      group = { caseId: g.case_id, caseTitle: g.case_title, grants: [] }
      map.set(g.case_id, group)
    }
    group.grants.push(g)
  }
  for (const f of forms) {
    if (!f.case_id) continue
    if (!map.has(f.case_id)) {
      map.set(f.case_id, { caseId: f.case_id, caseTitle: f.matter_label, grants: [] })
    }
  }
  for (const q of quotes) {
    if (!q.case_id) continue
    if (!map.has(q.case_id)) {
      map.set(q.case_id, { caseId: q.case_id, caseTitle: (q.case_title || '').trim() || 'Matter', grants: [] })
    }
  }
  const actionItems = [
    ...(clientActions?.outstanding ?? []),
    ...(clientActions?.complete ?? []),
    ...(clientActions?.inactive ?? []),
  ]
  for (const a of actionItems) {
    if (!a.case_id) continue
    const existing = map.get(a.case_id)
    if (!existing) {
      map.set(a.case_id, {
        caseId: a.case_id,
        caseTitle: (a.matter_label || '').trim() || 'Matter',
        grants: [],
      })
    } else if (!(existing.caseTitle || '').trim() || existing.caseTitle === 'Matter') {
      const label = (a.matter_label || '').trim()
      if (label) existing.caseTitle = label
    }
  }

  const outstandingByCase = new Map<string, number>()
  for (const a of clientActions?.outstanding ?? []) {
    if (!a.case_id) continue
    outstandingByCase.set(a.case_id, (outstandingByCase.get(a.case_id) ?? 0) + 1)
  }

  return Array.from(map.values()).sort((a, b) => {
    const ao = outstandingByCase.get(a.caseId) ?? 0
    const bo = outstandingByCase.get(b.caseId) ?? 0
    if (ao !== bo) return bo - ao
    return a.caseTitle.localeCompare(b.caseTitle)
  })
}

function outstandingCountForCase(
  clientActions: PortalClientActionsOut | null,
  caseId: string,
): number {
  if (!clientActions) return 0
  return clientActions.outstanding.filter((a) => a.case_id === caseId).length
}

function canarySignTokenFromLocation(): string | null {
  const pathMatch = window.location.pathname.match(/^\/portal\/s\/([^/]+)$/i)
  if (pathMatch?.[1]) return pathMatch[1].trim()
  // DocuSign already uses ?sign= on /portal — do not claim that query for Canary.
  return null
}

function actionStatusBadgeClass(bucket: 'outstanding' | 'complete' | 'inactive', status: string): string {
  if (bucket === 'outstanding') return 'portalActionBadge portalActionBadge--outstanding'
  if (bucket === 'complete') return 'portalActionBadge portalActionBadge--complete'
  if (status === 'declined') return 'portalActionBadge portalActionBadge--declined'
  if (status === 'expired') return 'portalActionBadge portalActionBadge--expired'
  return 'portalActionBadge portalActionBadge--cancelled'
}

function actionStatusLabel(bucket: 'outstanding' | 'complete' | 'inactive', status: string): string {
  if (bucket === 'outstanding') return 'Outstanding'
  if (bucket === 'complete') return 'Complete'
  if (status === 'declined') return 'Declined'
  if (status === 'expired') return 'Expired'
  if (status === 'voided' || status === 'superseded') return 'Cancelled'
  return 'Inactive'
}

function actionKindLabel(item: PortalClientActionItemOut): string {
  if (item.badge?.trim()) return item.badge.trim()
  if (item.kind === 'quote') return 'Quote'
  if (item.kind === 'form') return 'Form'
  if (item.kind === 'canary_sign') return 'Sign'
  if (item.kind === 'docusign') return 'DocuSign'
  return item.kind
}

function actionKindBadgeClass(item: PortalClientActionItemOut): string {
  if (item.kind === 'quote') return 'portalActionBadge portalActionBadge--kindQuote'
  if (item.kind === 'form') return 'portalActionBadge portalActionBadge--kindForm'
  if (item.kind === 'canary_sign') return 'portalActionBadge portalActionBadge--kindSign'
  if (item.kind === 'docusign') return 'portalActionBadge portalActionBadge--kindSign'
  return 'portalActionBadge portalActionBadge--neutral'
}

function quoteDeliveryFileUrl(deliveryId: string, download: boolean): string {
  const q = download ? '?download=1' : ''
  return apiUrl(`/portal/quote-deliveries/${encodeURIComponent(deliveryId)}/file${q}`)
}

function quoteExchangeTokenFromLocation(): string | null {
  const pathMatch = window.location.pathname.match(/^\/portal\/q\/([^/]+)$/i)
  if (pathMatch?.[1]) return pathMatch[1].trim()
  return new URLSearchParams(window.location.search).get('quote')?.trim() || null
}

function formExchangeTokenFromLocation(): string | null {
  const pathMatch = window.location.pathname.match(/^\/portal\/f\/([^/]+)$/i)
  if (pathMatch?.[1]) return pathMatch[1].trim()
  return new URLSearchParams(window.location.search).get('form')?.trim() || null
}

export default function PortalPage() {
  const [portalConfig, setPortalConfig] = useState<PortalBrandingConfig>(DEFAULT_PORTAL_CONFIG)
  const [signInMode, setSignInMode] = useState<SignInMode>('code')
  const [accessCode, setAccessCode] = useState('')
  const [resetEmail, setResetEmail] = useState('')
  const [resetVerifyCode, setResetVerifyCode] = useState('')
  const [resetCodeSent, setResetCodeSent] = useState(false)
  const [sessionToken, setSessionToken] = useState(() => getStoredPortalToken())
  const [contactName, setContactName] = useState('')
  const [contactId, setContactId] = useState<string | null>(null)
  const [recoveryNeeded, setRecoveryNeeded] = useState(false)
  const [sessionUnavailable, setSessionUnavailable] = useState(false)
  const draft = useRef<PortalDraft | null>(null)
  const recoveryForm = useRef<string | null>(null)
  const sessionEpoch = useRef(0)
  const currentToken = useRef(sessionToken)
  currentToken.current = sessionToken
  const captureSession = useCallback((token: string) => {
    const epoch = sessionEpoch.current
    return () => epoch === sessionEpoch.current && token === currentToken.current
  }, [])
  const sessionFetch = useCallback(<T,>(path: string, opts: RequestInit & { portalToken: string; json?: unknown }) => {
    const isCurrent = captureSession(opts.portalToken)
    if (!isCurrent()) return Promise.reject(new Error('Superseded portal request'))
    return portalFetch<T>(path, { ...opts, isCurrent })
  }, [captureSession])
  useEffect(() => {
    const expired = (event: Event) => {
      const detail = (event as CustomEvent<{token: string; message: string}>).detail
      if (detail.token !== currentToken.current) return
      setRecoveryNeeded(true)
      setErr(detail.message)
    }
    window.addEventListener('portal-session-expired', expired)
    return () => window.removeEventListener('portal-session-expired', expired)
  }, [])
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
  const [formExchangeBusy, setFormExchangeBusy] = useState(false)
  const [canaryExchangeBusy, setCanaryExchangeBusy] = useState(false)
  const [quoteDelivery, setQuoteDelivery] = useState<PortalQuoteDeliveryViewOut | null>(null)
  const [quotePreviewFailed, setQuotePreviewFailed] = useState(false)
  const [quoteDeclineOpen, setQuoteDeclineOpen] = useState(false)
  const [quoteDeclineReason, setQuoteDeclineReason] = useState('')
  const [quoteRespondBusy, setQuoteRespondBusy] = useState(false)
  const [activeFormId, setActiveFormId] = useState<string | null>(null)
  const [allPendingForms, setAllPendingForms] = useState<PortalFormPendingOut[]>([])
  const [pendingQuoteDeliveries, setPendingQuoteDeliveries] = useState<PortalQuoteDeliveryViewOut[]>([])
  const [clientActions, setClientActions] = useState<PortalClientActionsOut | null>(null)
  const [outstandingOpen, setOutstandingOpen] = useState(true)
  const [completeOpen, setCompleteOpen] = useState(false)
  const [inactiveOpen, setInactiveOpen] = useState(false)
  const [activeCanarySign, setActiveCanarySign] = useState<PortalCanarySignOut | null>(null)
  const [previewFocusCaseId, setPreviewFocusCaseId] = useState<string | null>(null)
  const [staffPreviewSession, setStaffPreviewSession] = useState(false)
  const [portalAudience, setPortalAudience] = useState<'client' | 'exchange'>('client')

  const isRenderedSessionCurrent = captureSession(sessionToken)

  const matterGroups = useMemo(
    () => buildMatterGroups(grants, allPendingForms, pendingQuoteDeliveries, clientActions),
    [grants, allPendingForms, pendingQuoteDeliveries, clientActions],
  )
  const activeMatter = useMemo(
    () => matterGroups.find((m) => m.caseId === activeCaseId) ?? null,
    [matterGroups, activeCaseId],
  )
  const activeGrant = useMemo(() => grants.find((g) => g.id === activeGrantId) ?? null, [grants, activeGrantId])

  const mattersNeedingAttention = useMemo(
    () => matterGroups.filter((m) => outstandingCountForCase(clientActions, m.caseId) > 0),
    [matterGroups, clientActions],
  )
  const otherMatters = useMemo(
    () => matterGroups.filter((m) => outstandingCountForCase(clientActions, m.caseId) === 0),
    [matterGroups, clientActions],
  )

  const staffPreview = useMemo(() => {
    if (typeof window === 'undefined') return staffPreviewSession
    if (staffPreviewSession) return true
    return new URLSearchParams(window.location.search).get('staff_preview') === '1'
  }, [staffPreviewSession])

  const loadConfig = useCallback(async () => {
    try {
      const cfg = await portalFetch<PortalBrandingConfig>('/portal/config')
      setPortalConfig({
        firm_name: cfg.firm_name?.trim() ?? '',
        portal_title: cfg.portal_title?.trim() || DEFAULT_PORTAL_CONFIG.portal_title,
        portal_logo_url: cfg.portal_logo_url ?? null,
        portal_logo_enabled: cfg.portal_logo_enabled !== false,
        portal_background_color: cfg.portal_background_color ?? null,
        portal_background_url: cfg.portal_background_url ?? null,
        portal_font_color: cfg.portal_font_color ?? null,
        portal_background_on_signed_in: cfg.portal_background_on_signed_in !== false,
      })
    } catch {
      /* optional */
    }
  }, [])

  useEffect(() => {
    document.title = portalConfig.portal_title
  }, [portalConfig.portal_title])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const exchange = params.get('preview_exchange')?.trim()
    if (!exchange) return
    const authEpoch = sessionEpoch.current
    void (async () => {
      setPreviewExchangeBusy(true)
      setErr(null)
      try {
        const out = await portalFetch<PortalAuthOut>('/portal/auth/preview-exchange', {
          method: 'POST',
          isCurrent: () => authEpoch === sessionEpoch.current,
          json: { exchange_token: exchange },
        })
        if (authEpoch !== sessionEpoch.current) return
        sessionEpoch.current += 1
        currentToken.current = out.session_token
        storePortalToken(out.session_token)
        setSessionToken(out.session_token)
        setContactName(out.contact_name)
        setGrants(out.grants)
        setStaffPreviewSession(Boolean(out.staff_preview))
        if (out.focus_case_id) {
          setPreviewFocusCaseId(out.focus_case_id)
          setActiveCaseId(out.focus_case_id)
          setActiveGrantId(null)
          setBrowse(null)
          setBrowseSubfolder('')
        }
        params.delete('preview_exchange')
        const qs = params.toString()
        window.history.replaceState(null, '', `${window.location.pathname}${qs ? `?${qs}` : ''}${window.location.hash}`)
      } catch (e: unknown) {
        if (authEpoch !== sessionEpoch.current) return
        sessionEpoch.current += 1
        currentToken.current = ''
        storePortalToken('')
        setSessionToken('')
        setErr((e as { message?: string }).message ?? 'Preview link expired or invalid')
      } finally {
        setPreviewExchangeBusy(false)
      }
    })()
  }, [])

  useEffect(() => {
    const quoteToken = quoteExchangeTokenFromLocation()
    if (!quoteToken) return
    const authEpoch = sessionEpoch.current
    void (async () => {
      setQuoteExchangeBusy(true)
      setErr(null)
      try {
        const out = await portalFetch<PortalQuoteExchangeOut>('/portal/quote-exchange', {
          method: 'POST',
          isCurrent: () => authEpoch === sessionEpoch.current,
          json: { exchange_token: quoteToken },
        })
        if (authEpoch !== sessionEpoch.current) return
        sessionEpoch.current += 1
        currentToken.current = out.session_token
        storePortalToken(out.session_token)
        setSessionToken(out.session_token)
        setContactName(out.contact_name)
        setGrants(out.grants)
        setQuoteDelivery(out.quote)
        // Land in the matter (not a folder); quote panel opens on top.
        if (out.quote.case_id) {
          setActiveCaseId(out.quote.case_id)
          setActiveGrantId(null)
          setBrowse(null)
          setBrowseSubfolder('')
        } else if (out.quote.grant_id) {
          const grant = out.grants.find((g) => g.id === out.quote.grant_id)
          if (grant) {
            setActiveCaseId(grant.case_id)
            setActiveGrantId(null)
          }
        }
        window.history.replaceState(null, '', '/portal')
      } catch (e: unknown) {
        if (authEpoch !== sessionEpoch.current) return
        sessionEpoch.current += 1
        currentToken.current = ''
        storePortalToken('')
        setSessionToken('')
        setErr((e as { message?: string }).message ?? 'Quote link expired or invalid')
      } finally {
        setQuoteExchangeBusy(false)
      }
    })()
  }, [])

  useEffect(() => {
    const formToken = formExchangeTokenFromLocation()
    if (!formToken) return
    const authEpoch = sessionEpoch.current
    void (async () => {
      setFormExchangeBusy(true)
      setErr(null)
      try {
        const out = await portalFetch<PortalFormExchangeOut>('/portal/form-exchange', {
          method: 'POST',
          isCurrent: () => authEpoch === sessionEpoch.current,
          json: { exchange_token: formToken },
        })
        if (authEpoch !== sessionEpoch.current) return
        sessionEpoch.current += 1
        currentToken.current = out.session_token
        storePortalToken(out.session_token)
        setSessionToken(out.session_token)
        setContactName(out.contact_name)
        setGrants(out.grants)
        setActiveFormId(out.form.id)
        if (out.form.case_id) {
          setActiveCaseId(out.form.case_id)
          setActiveGrantId(null)
          setBrowse(null)
          setBrowseSubfolder('')
        }
        window.history.replaceState(null, '', '/portal')
      } catch (e: unknown) {
        if (authEpoch !== sessionEpoch.current) return
        sessionEpoch.current += 1
        currentToken.current = ''
        storePortalToken('')
        setSessionToken('')
        setErr((e as { message?: string }).message ?? 'Form link expired or invalid')
      } finally {
        setFormExchangeBusy(false)
      }
    })()
  }, [])

  useEffect(() => {
    const signToken = canarySignTokenFromLocation()
    if (!signToken) return
    const authEpoch = sessionEpoch.current
    void (async () => {
      setCanaryExchangeBusy(true)
      setErr(null)
      try {
        const out = await portalFetch<PortalCanarySignExchangeOut>('/portal/canary-sign-exchange', {
          method: 'POST',
          isCurrent: () => authEpoch === sessionEpoch.current,
          json: { sign_token: signToken },
        })
        if (authEpoch !== sessionEpoch.current) return
        sessionEpoch.current += 1
        currentToken.current = out.session_token
        storePortalToken(out.session_token)
        setSessionToken(out.session_token)
        setContactName(out.contact_name)
        setGrants(out.grants)
        setActiveCanarySign(out.signing)
        if (out.signing.case_id) {
          setActiveCaseId(out.signing.case_id)
          setActiveGrantId(null)
          setBrowse(null)
          setBrowseSubfolder('')
        }
        window.history.replaceState(null, '', '/portal')
      } catch (e: unknown) {
        if (authEpoch !== sessionEpoch.current) return
        sessionEpoch.current += 1
        currentToken.current = ''
        storePortalToken('')
        setSessionToken('')
        setErr((e as { message?: string }).message ?? 'Signing link expired or invalid')
      } finally {
        setCanaryExchangeBusy(false)
      }
    })()
  }, [])

  const refreshSession = useCallback(async (token: string) => {
    const isCurrent = captureSession(token)
    if (!isCurrent()) return
    const sess = await sessionFetch<PortalSessionOut>('/portal/session', { portalToken: token })
    if (!isCurrent()) return sess
    setContactId(sess.contact_id ?? null)
    setSessionUnavailable(false)
    setContactName(sess.contact_name)
    setGrants(sess.grants)
    setStaffPreviewSession(Boolean(sess.staff_preview))
    setPortalAudience(sess.audience === 'exchange' ? 'exchange' : 'client')
    if (sess.focus_case_id) setActiveCaseId(sess.focus_case_id)
    return sess
  }, [captureSession, sessionFetch])

  const isRevokedGrantError = useCallback((message: string) => {
    const msg = message.toLowerCase()
    return msg.includes('not found') || msg.includes('no longer available')
  }, [])

  useEffect(() => {
    if (!sessionToken.trim()) return
    setActiveGrantId((grantId) => {
      if (grantId && !grants.some((g) => g.id === grantId)) {
        setBrowse(null)
        setBrowseSubfolder('')
        return null
      }
      return grantId
    })
    setActiveCaseId((caseId) => {
      if (!caseId) return caseId
      if (caseId === previewFocusCaseId) return caseId
      if (grants.some((g) => g.case_id === caseId)) return caseId
      if (allPendingForms.some((f) => f.case_id === caseId)) return caseId
      if (pendingQuoteDeliveries.some((q) => q.case_id === caseId)) return caseId
      const actionItems = [
        ...(clientActions?.outstanding ?? []),
        ...(clientActions?.complete ?? []),
        ...(clientActions?.inactive ?? []),
      ]
      if (actionItems.some((a) => a.case_id === caseId)) return caseId
      return null
    })
  }, [grants, sessionToken, allPendingForms, pendingQuoteDeliveries, clientActions, previewFocusCaseId])

  const loadBrowse = useCallback(async (grantId: string, subfolder: string, token: string) => {
    const isCurrent = captureSession(token)
    if (!isCurrent()) return
    const q = subfolder ? `?subfolder=${encodeURIComponent(subfolder)}` : ''
    const data = await sessionFetch<PortalBrowseOut>(`/portal/grants/${grantId}/browse${q}`, { portalToken: token })
    if (!isCurrent()) return
    setBrowse(data)
    setBrowseSubfolder(data.subfolder)
    // Mark this visit so the next session clears folder "new" badges.
    try {
      await sessionFetch(`/portal/grants/${grantId}/viewed`, { method: 'POST', portalToken: token })
    } catch {
      if (!isCurrent()) return
      /* non-fatal */
    }
  }, [captureSession, sessionFetch])

  const loadPendingForms = useCallback(async (token: string) => {
    const isCurrent = captureSession(token)
    if (!isCurrent()) return
    try {
      const rows = await sessionFetch<PortalFormPendingOut[]>('/portal/forms', { portalToken: token })
      if (!isCurrent()) return
      setAllPendingForms(Array.isArray(rows) ? rows : [])
    } catch {
      if (!isCurrent()) return
      setAllPendingForms([])
    }
  }, [captureSession, sessionFetch])

  const loadPendingQuotes = useCallback(async (token: string) => {
    const isCurrent = captureSession(token)
    if (!isCurrent()) return
    try {
      const rows = await sessionFetch<PortalQuoteDeliveryViewOut[]>('/portal/quote-deliveries', { portalToken: token })
      if (!isCurrent()) return
      setPendingQuoteDeliveries(Array.isArray(rows) ? rows : [])
    } catch {
      if (!isCurrent()) return
      setPendingQuoteDeliveries([])
    }
  }, [captureSession, sessionFetch])

  const loadClientActions = useCallback(async (token: string) => {
    const isCurrent = captureSession(token)
    if (!isCurrent()) return
    try {
      const data = await sessionFetch<PortalClientActionsOut>('/portal/client-actions', { portalToken: token })
      if (!isCurrent()) return
      setClientActions(data)
    } catch {
      if (!isCurrent()) return
      setClientActions(null)
    }
  }, [captureSession, sessionFetch])

  useEffect(() => {
    const token = sessionToken.trim()
    if (!token || previewExchangeBusy || quoteExchangeBusy || formExchangeBusy || canaryExchangeBusy) return
    if (portalAudience === 'exchange') {
      setAllPendingForms([])
      setPendingQuoteDeliveries([])
      setClientActions(null)
      return
    }
    void loadPendingForms(token)
    void loadPendingQuotes(token)
    void loadClientActions(token)
  }, [
    sessionToken,
    portalAudience,
    loadPendingForms,
    loadPendingQuotes,
    loadClientActions,
    previewExchangeBusy,
    quoteExchangeBusy,
    formExchangeBusy,
    canaryExchangeBusy,
  ])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const signToken = params.get('sign')?.trim()
    if (!signToken) return
    window.location.href = apiUrl(`/docusign/sign/${encodeURIComponent(signToken)}`)
  }, [])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get('signing') === 'complete') {
      setInfo('Thank you — your signature has been submitted.')
      params.delete('signing')
      params.delete('token')
      const qs = params.toString()
      window.history.replaceState(null, '', `${window.location.pathname}${qs ? `?${qs}` : ''}${window.location.hash}`)
    }
  }, [])

  useEffect(() => {
    void loadConfig()
  }, [loadConfig])

  useEffect(() => {
    const token = sessionToken.trim()
    const isCurrent = captureSession(token)
    if (!token || previewExchangeBusy || quoteExchangeBusy || formExchangeBusy || canaryExchangeBusy) return
    void (async () => {
      setBusy(true)
      setErr(null)
      try {
        await refreshSession(token)
      } catch (e: unknown) {
        if (!isCurrent()) return
        setSessionUnavailable(!(e instanceof PortalRequestError && e.status === 401))
        setErr((e as { message?: string }).message ?? 'Could not check session. Please retry.')
      } finally {
        if (isCurrent()) setBusy(false)
      }
    })()
  }, [captureSession, sessionToken, refreshSession, previewExchangeBusy, quoteExchangeBusy, formExchangeBusy, canaryExchangeBusy])

  useEffect(() => {
    const token = sessionToken.trim()
    const isCurrent = captureSession(token)
    if (!token) return
    const refresh = () => {
      void refreshSession(token).catch((e: unknown) => {
        if (!isCurrent()) return
        setSessionUnavailable(!(e instanceof PortalRequestError && e.status === 401))
        setErr((e as Error).message || 'Could not check session. Please retry.')
      })
    }
    const onVisibility = () => {
      if (document.visibilityState === 'visible') refresh()
    }
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      window.removeEventListener('focus', refresh)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [captureSession, sessionToken, refreshSession])

  useEffect(() => {
    const token = sessionToken.trim()
    if (!token || !activeCaseId || activeGrantId) return
    void refreshSession(token).catch(() => {})
  }, [sessionToken, activeCaseId, activeGrantId, refreshSession])

  useEffect(() => {
    const token = sessionToken.trim()
    const isCurrent = captureSession(token)
    if (!token || !activeGrantId) return
    void (async () => {
      try {
        await loadBrowse(activeGrantId, browseSubfolder, token)
      } catch (e: unknown) {
        if (!isCurrent()) return
        const msg = (e as { message?: string }).message ?? 'Could not load folder'
        if (isRevokedGrantError(msg)) {
          setBrowse(null)
          setBrowseSubfolder('')
          setActiveGrantId(null)
          try {
            await refreshSession(token)
          } catch {
            /* session refresh may sign out if no grants remain */
          }
          if (!isCurrent()) return
          setInfo('This shared folder is no longer available.')
        } else {
          setErr(msg)
        }
      } finally {
        if (isCurrent()) setBusy(false)
      }
    })()
  }, [captureSession, activeGrantId, sessionToken, browseSubfolder, loadBrowse, isRevokedGrantError, refreshSession])

  async function signInWithCode(e: React.FormEvent) {
    e.preventDefault()
    let authEpoch = sessionEpoch.current
    setBusy(true)
    setErr(null)
    setInfo(null)
    try {
      const out = await portalFetch<PortalAuthOut>('/portal/auth', {
        method: 'POST',
        json: { access_code: accessCode },
      })
      if (authEpoch !== sessionEpoch.current) return
      const verified = await portalFetch<PortalSessionOut>('/portal/session', { portalToken: out.session_token })
      if (authEpoch !== sessionEpoch.current) return
      let resumeId: string | null = null
      if (recoveryForm.current && draft.current && verified.contact_id &&
          verified.contact_id === draft.current.contactId && !verified.staff_preview && verified.audience !== 'exchange') {
        try {
          const form = await portalFetch<{contact_id: string; status: string}>(`/portal/forms/${recoveryForm.current}`, { portalToken: out.session_token })
          if (form.contact_id === verified.contact_id && form.status === 'pending') resumeId = recoveryForm.current
        } catch (error: unknown) {
          // Permission loss is definitive; an outage is not. Keep the draft hidden
          // until a subsequent sign-in can verify this same client's form access.
          if (!(error instanceof PortalRequestError && [403, 404, 410].includes(error.status))) {
            throw new Error('Could not verify form access. Your unsent draft is still held in this tab. Sign in again to retry.')
          }
        }
      }
      if (authEpoch !== sessionEpoch.current) return
      if (!resumeId) draft.current = null
      recoveryForm.current = null
      setActiveFormId(resumeId)
      setContactId(verified.contact_id ?? null)
      setRecoveryNeeded(false)
      setSessionUnavailable(false)
      sessionEpoch.current += 1
      authEpoch = sessionEpoch.current
      currentToken.current = out.session_token
      storePortalToken(out.session_token)
      setSessionToken(out.session_token)
      setContactName(out.contact_name)
      setGrants(out.grants)
      setStaffPreviewSession(Boolean(out.staff_preview))
      setPortalAudience(out.audience === 'exchange' ? 'exchange' : 'client')
      setActiveCaseId(out.focus_case_id || null)
      setActiveGrantId(null)
      setBrowse(null)
      setBrowseSubfolder('')
      setAccessCode('')
    } catch (e: unknown) {
      if (authEpoch !== sessionEpoch.current) return
      setErr((e as { message?: string }).message ?? 'Sign-in failed')
    } finally {
      if (authEpoch === sessionEpoch.current) setBusy(false)
    }
  }

  async function requestCodeReset(e: React.FormEvent) {
    e.preventDefault()
    const authEpoch = sessionEpoch.current
    setBusy(true)
    setErr(null)
    setInfo(null)
    try {
      await portalFetch('/portal/auth/request-code-reset', {
        method: 'POST',
        json: { email: resetEmail.trim() },
      })
      if (authEpoch !== sessionEpoch.current) return
      setResetCodeSent(true)
      setInfo('If this e-mail has portal access, a verification code has been sent.')
    } catch (e: unknown) {
      if (authEpoch !== sessionEpoch.current) return
      setErr((e as { message?: string }).message ?? 'Could not send verification code')
    } finally {
      if (authEpoch === sessionEpoch.current) setBusy(false)
    }
  }

  async function confirmCodeReset(e: React.FormEvent) {
    e.preventDefault()
    const authEpoch = sessionEpoch.current
    setBusy(true)
    setErr(null)
    setInfo(null)
    try {
      const out = await portalFetch<{ access_code: string; contact_name: string }>(
        '/portal/auth/confirm-code-reset',
        {
          method: 'POST',
          json: { email: resetEmail.trim(), code: resetVerifyCode.trim() },
        },
      )
      if (authEpoch !== sessionEpoch.current) return
      setAccessCode(out.access_code)
      setResetVerifyCode('')
      setResetCodeSent(false)
      setSignInMode('code')
      setInfo(
        out.contact_name
          ? `A new access code for ${out.contact_name} is ready below (and was e-mailed). Sign in to continue.`
          : 'A new access code is ready below (and was e-mailed). Sign in to continue.',
      )
    } catch (e: unknown) {
      if (authEpoch !== sessionEpoch.current) return
      setErr((e as { message?: string }).message ?? 'Could not reset access code')
    } finally {
      if (authEpoch === sessionEpoch.current) setBusy(false)
    }
  }

  function beginRecovery() {
    const retainedDraft = draft.current
    const retainedForm = activeFormId
    signOut()
    draft.current = retainedDraft
    recoveryForm.current = retainedForm
    setSignInMode('code')
    setInfo('Sign in to resume. Your unsent form is held only in this tab until your access is checked.')
  }

  function signOut() {
    sessionEpoch.current += 1
    setBusy(false)
    setUploadBusy(false)
    setQuoteRespondBusy(false)
    setSessionUnavailable(false)
    setPreviewFocusCaseId(null)
    setStaffPreviewSession(false)
    setPortalAudience('client')
    draft.current = null
    recoveryForm.current = null
    setRecoveryNeeded(false)
    setContactId(null)
    currentToken.current = ''
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
    setActiveFormId(null)
    setAllPendingForms([])
    setPendingQuoteDeliveries([])
    setClientActions(null)
    setOutstandingOpen(true)
    setCompleteOpen(false)
    setInactiveOpen(false)
    setActiveCanarySign(null)
  }

  async function downloadQuoteFile() {
    if (!quoteDelivery) return
    const token = sessionToken.trim()
    const isCurrent = captureSession(token)
    if (!token) return
    setErr(null)
    try {
      const url = quoteDeliveryFileUrl(quoteDelivery.id, true)
      const headers = new Headers()
      applyAuthHeaders(headers, token)
      const res = await fetch(url, { headers })
      if (!isCurrent()) return
      if (!res.ok) {
        const detail = await res.text()
        if (!isCurrent()) return
        throw portalRequestError(res.status, formatApiErrorDetail(detail, res.statusText), token)
      }
      const blob = await res.blob()
      if (!isCurrent()) return
      const obj = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = obj
      a.download = quoteDelivery.original_filename
      a.click()
      URL.revokeObjectURL(obj)
    } catch (e: unknown) {
      if (!isCurrent()) return
      setErr((e as { message?: string }).message ?? 'Download failed')
    }
  }

  async function respondToQuote(accepted: boolean) {
    if (!quoteDelivery) return
    const isCurrent = captureSession(sessionToken)
    await respondToApproval(quoteDelivery.id, accepted, quoteDeclineReason.trim() || null)
    if (!isCurrent()) return
    setQuoteDeclineOpen(false)
    setQuoteDeclineReason('')
  }

  async function respondToApproval(
    deliveryId: string,
    accepted: boolean,
    declineReason: string | null = null,
  ) {
    const token = sessionToken.trim()
    const isCurrent = captureSession(token)
    if (!token) return
    setQuoteRespondBusy(true)
    setErr(null)
    try {
      const out = await sessionFetch<PortalQuoteDeliveryViewOut>(
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
      if (!isCurrent()) return
      if (quoteDelivery?.id === deliveryId) setQuoteDelivery(out)
      setInfo(accepted ? 'Thank you — your acceptance has been recorded.' : 'Your response has been recorded.')
      void loadPendingQuotes(token)
      void loadClientActions(token)
      if (activeGrantId) {
        await loadBrowse(activeGrantId, browseSubfolder, token)
        if (!isCurrent()) return
      }
    } catch (e: unknown) {
      if (!isCurrent()) return
      setErr((e as { message?: string }).message ?? 'Could not submit response')
    } finally {
      if (isCurrent()) setQuoteRespondBusy(false)
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
    const isCurrent = captureSession(token)
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
        if (!isCurrent()) return
        if (!res.ok) {
          const text = await res.text()
          if (!isCurrent()) return
          let parsed: unknown = text
          try {
            parsed = JSON.parse(text)
          } catch {
            /* keep text */
          }
          throw portalRequestError(res.status, formatApiErrorDetail(parsed, res.statusText), token)
        }
      }
      await loadBrowse(activeGrantId, browseSubfolder, token)
      if (!isCurrent()) return
    } catch (e: unknown) {
      if (!isCurrent()) return
      setErr((e as { message?: string }).message ?? 'Upload failed')
    } finally {
      if (isCurrent()) setUploadBusy(false)
    }
  }

  async function fetchFileBlob(file: PortalFileOut, download: boolean): Promise<Blob> {
    const token = sessionToken.trim()
    const isCurrent = captureSession(token)
    if (!token || !activeGrantId) throw new Error('Not signed in')
    const q = download ? '?download=1' : ''
    const url = apiUrl(`/portal/grants/${activeGrantId}/files/${file.id}${q}`)
    const headers = new Headers()
    applyAuthHeaders(headers, token)
    const res = await fetch(url, { headers })
    if (!isCurrent()) throw new Error('Superseded portal request')
    if (!res.ok) {
      const text = await res.text()
      if (!isCurrent()) throw new Error('Superseded portal request')
      let parsed: unknown = text
      try {
        parsed = JSON.parse(text)
      } catch {
        /* keep text */
      }
      throw portalRequestError(res.status, formatApiErrorDetail(parsed, res.statusText), token)
    }
    const blob = await res.blob()
    if (!isCurrent()) throw new Error('Superseded portal request')
    return blob
  }

  async function openFile(file: PortalFileOut) {
    const isCurrent = captureSession(sessionToken)
    const token = sessionToken.trim()
    if (!token || !activeGrantId) return
    setErr(null)
    try {
      // Prefer a real navigation URL so the browser applies its normal content-type handling
      // (PDF viewer, image tab, etc.) instead of a blob: address bar.
      const minted = await sessionFetch<{ token: string }>(
        `/portal/grants/${activeGrantId}/files/${file.id}/open-token`,
        { method: 'POST', portalToken: token },
      )
      if (!isCurrent()) return
      const openUrl = browserAbsoluteApiUrl(
        apiUrl(
          `/portal/grants/${activeGrantId}/files/${file.id}/open?token=${encodeURIComponent(minted.token)}`,
        ),
      )
      const opened = window.open(openUrl, '_blank', 'noopener,noreferrer')
      if (!opened) {
        // Popup blocked — fall back to same-tab navigation.
        window.location.assign(openUrl)
      }
    } catch (e: unknown) {
      if (!isCurrent()) return
      setErr((e as { message?: string }).message ?? 'Could not open file')
    }
  }

  async function downloadFile(file: PortalFileOut) {
    const isCurrent = captureSession(sessionToken)
    setErr(null)
    try {
      const blob = await fetchFileBlob(file, true)
      if (!isCurrent()) return
      const obj = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = obj
      a.download = file.original_filename
      a.click()
      URL.revokeObjectURL(obj)
    } catch (e: unknown) {
      if (!isCurrent()) return
      setErr((e as { message?: string }).message ?? 'Download failed')
    }
  }

  async function downloadAllFiles() {
    const token = sessionToken.trim()
    const isCurrent = captureSession(token)
    if (!token || !activeGrantId) return
    setBusy(true)
    setErr(null)
    try {
      const url = apiUrl(`/portal/grants/${activeGrantId}/files/download-zip`)
      const headers = new Headers()
      applyAuthHeaders(headers, token)
      const res = await fetch(url, { headers })
      if (!isCurrent()) return
      if (!res.ok) {
        const text = await res.text()
        if (!isCurrent()) return
        let parsed: unknown = text
        try {
          parsed = JSON.parse(text)
        } catch {
          /* keep text */
        }
        throw portalRequestError(res.status, formatApiErrorDetail(parsed, res.statusText), token)
      }
      const blob = await res.blob()
      if (!isCurrent()) return
      const obj = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = obj
      a.download = `${portalGrantFolderLabel(activeGrant?.folder_label) ?? 'documents'}.zip`
      a.click()
      URL.revokeObjectURL(obj)
    } catch (e: unknown) {
      if (!isCurrent()) return
      setErr((e as { message?: string }).message ?? 'Download failed')
    } finally {
      if (isCurrent()) setBusy(false)
    }
  }

  function openGrant(grantId: string) {
    if (!grants.some((g) => g.id === grantId)) return
    setActiveGrantId(grantId)
    setBrowseSubfolder('')
    setBrowse(null)
  }

  async function openMatter(caseId: string) {
    const token = sessionToken.trim()
    const isCurrent = captureSession(token)
    let visibleGrants = grants
    if (token) {
      try {
        const sess = await refreshSession(token)
        if (!isCurrent() || !sess) return
        visibleGrants = sess.grants
      } catch {
        return
      }
    }
    const hasGrant = visibleGrants.some((g) => g.case_id === caseId)
    const hasForm = allPendingForms.some((f) => f.case_id === caseId)
    const hasQuote = pendingQuoteDeliveries.some((q) => q.case_id === caseId)
    const actionItems = [
      ...(clientActions?.outstanding ?? []),
      ...(clientActions?.complete ?? []),
      ...(clientActions?.inactive ?? []),
    ]
    const hasAction = actionItems.some((a) => a.case_id === caseId)
    if (!hasGrant && !hasForm && !hasQuote && !hasAction && caseId !== previewFocusCaseId) {
      setActiveCaseId(null)
      return
    }
    setActiveCaseId(caseId)
    setActiveGrantId(null)
    setBrowse(null)
    setBrowseSubfolder('')
    setOutstandingOpen(true)
    setCompleteOpen(false)
    setInactiveOpen(false)
  }

  async function backToAllMatters() {
    const token = sessionToken.trim()
    const isCurrent = captureSession(token)
    if (token) {
      try {
        await refreshSession(token)
      } catch {
        /* ignore */
      }
    }
    if (!isCurrent()) return
    setActiveCaseId(null)
    setActiveGrantId(null)
    setPreviewFocusCaseId(null)
    setBrowse(null)
    setBrowseSubfolder('')
    setQuoteDelivery(null)
    setActiveFormId(null)
    setActiveCanarySign(null)
    setOutstandingOpen(true)
    setCompleteOpen(false)
    setInactiveOpen(false)
  }

  async function backToFolderList() {
    const token = sessionToken.trim()
    const isCurrent = captureSession(token)
    if (token) {
      try {
        await refreshSession(token)
      } catch {
        /* ignore */
      }
    }
    if (!isCurrent()) return
    setActiveGrantId(null)
    setBrowse(null)
    setBrowseSubfolder('')
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

  if (previewExchangeBusy || quoteExchangeBusy || formExchangeBusy || canaryExchangeBusy) {
    // Match destination chrome: avoid flashing login branding when signed-in canvas is off.
    const exchangeUsesCustomCanvas =
      !sessionToken || portalConfig.portal_background_on_signed_in !== false
    return (
      <PortalLayout config={portalConfig} wide={false} useCustomCanvas={exchangeUsesCustomCanvas}>
        <div className="muted" style={{ marginTop: 12 }}>
          {canaryExchangeBusy
            ? 'Opening signature…'
            : formExchangeBusy
              ? 'Opening form…'
              : quoteExchangeBusy
                ? 'Opening quote…'
                : 'Opening preview…'}
        </div>
      </PortalLayout>
    )
  }

  if (!sessionToken) {
    return (
      <PortalLayout config={portalConfig} wide={false} subtitle="Sign in with your access code.">
        {staffPreview ? (
          <div className="notice portalStaffPreviewBanner">
            Staff preview — choose a contact from the matter Portal panel, or sign in manually with an access code.
          </div>
        ) : null}

        {signInMode === 'code' ? (
          <form className="stack portalSignInForm" style={{ marginTop: 16 }} onSubmit={(e) => void signInWithCode(e)}>
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
            <div className="portalSignInActions">
              <button type="submit" className="btn primary" disabled={busy || !accessCode.trim()}>
                {busy ? 'Signing in…' : 'Sign in'}
              </button>
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => {
                  setSignInMode('reset')
                  setErr(null)
                  setInfo(null)
                  setResetCodeSent(false)
                  setResetVerifyCode('')
                }}
              >
                E-mail code
              </button>
            </div>
            {err ? <div className="error">{err}</div> : null}
            {info ? <div className="notice">{info}</div> : null}
          </form>
        ) : (
          <form
            className="stack portalSignInForm"
            style={{ marginTop: 16 }}
            onSubmit={(e) => void (resetCodeSent ? confirmCodeReset(e) : requestCodeReset(e))}
          >
            {!resetCodeSent ? (
              <label className="stack" style={{ gap: 6 }}>
                <span>E-mail address</span>
                <div className="portalSignInFieldRow">
                  <input
                    type="email"
                    value={resetEmail}
                    onChange={(e) => setResetEmail(e.target.value)}
                    autoComplete="email"
                    autoFocus
                    disabled={busy}
                  />
                  <button type="submit" className="btn primary" disabled={busy || !resetEmail.trim()}>
                    {busy ? 'Sending…' : 'Send code'}
                  </button>
                </div>
              </label>
            ) : (
              <label className="stack" style={{ gap: 6 }}>
                <span>Verification code</span>
                <div className="portalSignInFieldRow">
                  <input
                    value={resetVerifyCode}
                    onChange={(e) => setResetVerifyCode(e.target.value)}
                    autoComplete="one-time-code"
                    autoFocus
                    placeholder="123456"
                    disabled={busy}
                  />
                  <button type="submit" className="btn primary" disabled={busy || !resetVerifyCode.trim()}>
                    {busy ? 'Resetting…' : 'Reset code'}
                  </button>
                </div>
              </label>
            )}
            {err ? <div className="error">{err}</div> : null}
            {info ? <div className="notice">{info}</div> : null}
            <button
              type="button"
              className="btnLink"
              disabled={busy}
              onClick={() => {
                if (resetCodeSent) {
                  setResetCodeSent(false)
                  setResetVerifyCode('')
                  setInfo(null)
                } else {
                  setSignInMode('code')
                  setErr(null)
                  setInfo(null)
                }
              }}
            >
              {resetCodeSent ? 'Use a different e-mail' : 'Back to sign in'}
            </button>
          </form>
        )}
      </PortalLayout>
    )
  }

  const files = browse?.files ?? []
  const subfolders = browse?.subfolders ?? []
  const browseBreadcrumb = browse?.breadcrumb ?? []
  const currentFolderTitle =
    browseBreadcrumb.length > 0
      ? decodeFolderPathSegment(browseBreadcrumb[browseBreadcrumb.length - 1])
      : portalGrantFolderLabel(activeGrant?.folder_label)

  const scopedClientActions: PortalClientActionsOut | null = (() => {
    if (!clientActions || !activeCaseId || activeGrantId) return null
    const filter = (items: PortalClientActionItemOut[]) => items.filter((a) => a.case_id === activeCaseId)
    return {
      outstanding: filter(clientActions.outstanding),
      complete: filter(clientActions.complete),
      inactive: filter(clientActions.inactive),
    }
  })()

  const hasScopedActions = Boolean(
    scopedClientActions &&
      (scopedClientActions.outstanding.length > 0 ||
        scopedClientActions.complete.length > 0 ||
        scopedClientActions.inactive.length > 0),
  )

  async function openClientAction(item: PortalClientActionItemOut) {
    const token = sessionToken.trim()
    const isCurrent = captureSession(token)
    if (!token) return
    setErr(null)
    if (item.case_id) {
      setActiveCaseId(item.case_id)
      setActiveGrantId(null)
      setBrowse(null)
      setBrowseSubfolder('')
    }
    try {
      if (item.kind === 'quote') {
        const existing = pendingQuoteDeliveries.find((q) => q.id === item.id)
        if (existing) {
          setQuoteDelivery(existing)
        } else {
          const q = await sessionFetch<PortalQuoteDeliveryViewOut>(`/portal/quote-deliveries/${item.id}`, {
            portalToken: token,
          })
          if (!isCurrent()) return
          setQuoteDelivery(q)
        }
        return
      }
      if (item.kind === 'form') {
        setActiveFormId(item.id)
        return
      }
      if (item.kind === 'canary_sign') {
        setBusy(true)
        const signing = await sessionFetch<PortalCanarySignOut>(`/portal/canary-sign/${item.id}`, {
          portalToken: token,
        })
        if (!isCurrent()) return
        setActiveCanarySign(signing)
        return
      }
      if (item.kind === 'docusign') {
        await startDocusignSigning({
          id: item.id,
          envelope_subject: item.title,
          status: item.status,
          can_sign: true,
          recipient_id: '',
          sign_token: '',
        })
        if (!isCurrent()) return
      }
    } catch (e: unknown) {
      if (!isCurrent()) return
      setErr((e as { message?: string }).message ?? 'Could not open action')
    } finally {
      if (isCurrent()) setBusy(false)
    }
  }

  function formatActionWhen(iso: string | null | undefined): string {
    if (!iso) return ''
    try {
      return new Date(iso).toLocaleString('en-GB', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    } catch {
      return iso
    }
  }

  function renderActionList(
    bucket: 'outstanding' | 'complete' | 'inactive',
    items: PortalClientActionItemOut[],
  ) {
    if (items.length === 0) return null
    const showStatusBadge = bucket === 'inactive'
    return (
      <ul className="portalActionList">
        {items.map((item) => {
          const when = formatActionWhen(item.occurred_at)
          return (
            <li key={`${item.kind}:${item.id}`}>
              <button
                type="button"
                className="portalActionRow"
                disabled={busy}
                onClick={() => void openClientAction(item)}
              >
                <span className="portalActionRowMain">
                  {showStatusBadge ? (
                    <span className={actionStatusBadgeClass(bucket, item.status)}>
                      {actionStatusLabel(bucket, item.status)}
                    </span>
                  ) : null}
                  <span className={actionKindBadgeClass(item)}>{actionKindLabel(item)}</span>
                  <span className="portalActionRowTitleBlock">
                    <span className="portalActionRowTitle">{item.title}</span>
                    {when ? (
                      <span className="muted portalActionRowWhen">
                        {bucket === 'complete' ? `Completed ${when}` : when}
                      </span>
                    ) : null}
                  </span>
                </span>
                <span className="portalRowChevron" aria-hidden>
                  ›
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    )
  }

  function renderMatterList(matters: MatterGroup[]) {
    if (matters.length === 0) return null
    return (
      <div className="list portalMatterList">
        {matters.map((m) => {
          const todo = outstandingCountForCase(clientActions, m.caseId)
          const newFiles = m.grants.reduce((n, g) => n + (g.new_file_count ?? 0), 0)
          return (
            <button
              key={m.caseId}
              type="button"
              className="listCard rowbtn portalMatterCard"
              onClick={() => void openMatter(m.caseId)}
            >
              <div className="portalMatterCardMain">
                <div className="listTitle portalMatterTitle">{m.caseTitle}</div>
                {todo > 0 ? (
                  <div className="muted portalMatterTodoLabel">
                    {todo === 1 ? '1 action needed' : `${todo} actions needed`}
                  </div>
                ) : null}
                {newFiles > 0 ? (
                  <div className="muted portalMatterNewLabel">
                    {newFiles === 1 ? '1 new shared file' : `${newFiles} new shared files`}
                  </div>
                ) : null}
              </div>
              {newFiles > 0 ? (
                <span className="portalNewBadge" title="New since last visit">
                  New
                </span>
              ) : null}
              <span className="portalRowChevron" aria-hidden>
                ›
              </span>
            </button>
          )
        })}
      </div>
    )
  }

  function renderActionSection(
    key: 'outstanding' | 'complete' | 'inactive',
    title: string,
    items: PortalClientActionItemOut[],
    open: boolean,
    setOpen: Dispatch<SetStateAction<boolean>>,
  ) {
    if (items.length === 0) return null
    return (
      <div className="portalActionSection">
        <button
          type="button"
          className="btnLink portalActionSectionToggle"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          <span aria-hidden className="portalActionSectionChevron">
            {open ? '▾' : '▸'}
          </span>
          <span className="portalActionSectionTitle">{title}</span>
          <span className="portalActionSectionCount">{items.length}</span>
        </button>
        {open ? <div className="portalActionSectionBody">{renderActionList(key, items)}</div> : null}
      </div>
    )
  }

  function renderYourActions() {
    if (!scopedClientActions || !hasScopedActions) return null
    return (
      <section className="portalSection">
        <h2 className="portalSectionHeading">Your actions</h2>
        <div className="portalSectionBody">
          {renderActionSection(
            'outstanding',
            'Outstanding',
            scopedClientActions.outstanding,
            outstandingOpen,
            setOutstandingOpen,
          )}
          {renderActionSection(
            'complete',
            'Complete',
            scopedClientActions.complete,
            completeOpen,
            setCompleteOpen,
          )}
          {renderActionSection(
            'inactive',
            'Inactive',
            scopedClientActions.inactive,
            inactiveOpen,
            setInactiveOpen,
          )}
        </div>
      </section>
    )
  }

  async function startDocusignSigning(item: PortalDocusignSigningOut) {
    const token = sessionToken.trim()
    if (!token) return
    setErr(null)
    setBusy(true)
    try {
      const out = await portalFetch<{ url: string }>(`/portal/signing-requests/${item.id}/start`, {
        method: 'POST',
        portalToken: token,
      })
      window.location.href = out.url
    } catch (e: unknown) {
      setErr((e as { message?: string }).message ?? 'Could not open DocuSign')
    } finally {
      setBusy(false)
    }
  }

  return (
    <PortalLayout
      config={portalConfig}
      // When false, signed-in view keeps Canary default chrome (login still uses custom colours).
      useCustomCanvas={portalConfig.portal_background_on_signed_in !== false}
      subtitle={recoveryNeeded ? "Session expired or access changed" : contactName ? `Signed in as ${contactName}` : null}
      headerActions={
        <button type="button" className="btn portalSignOutBtn" onClick={signOut}>
          Sign out
        </button>
      }
    >
      {recoveryNeeded ? <div className="notice" role="alert">
        Your session expired or access changed. Sign in again to check access and resume your unsent form.
        <button type="button" className="btn primary" onClick={beginRecovery}>Sign in</button>
      </div> : sessionUnavailable ? <div className="notice" role="alert">
        Your session could not be checked. Your work and login have been kept.
        <button type="button" className="btn" onClick={() => {
          const isCurrent = captureSession(sessionToken)
          void refreshSession(sessionToken).then(() => { if (isCurrent()) setErr(null) }).catch((e: Error) => { if (isCurrent()) setErr(e.message) })
        }}>Retry</button>
      </div> : null}

        {err ? <div className="error" style={{ marginTop: 12 }}>{err}</div> : null}
        {info ? <div className="notice" style={{ marginTop: 12 }}>{info}</div> : null}

        {staffPreview ? (
          <div className="notice portalStaffPreviewBanner" style={{ marginTop: 12 }}>
            Staff preview — viewing as {contactName}. This is what this contact sees in the portal.
          </div>
        ) : null}

        {quoteDelivery ? (
          <div className="portalQuotePanel card" style={{ marginTop: 16, padding: 16 }}>
            <div className="row" style={{ gap: 8, flexWrap: 'wrap', marginBottom: 12, alignItems: 'center' }}>
              <button
                type="button"
                className="btn"
                onClick={() => {
                  const caseId = quoteDelivery.case_id
                  setQuoteDelivery(null)
                  setQuotePreviewFailed(false)
                  setQuoteDeclineOpen(false)
                  setQuoteDeclineReason('')
                  if (caseId) setActiveCaseId(caseId)
                }}
              >
                ← Back
              </button>
              <h2 style={{ margin: 0, flex: 1, fontSize: 18 }}>Quote</h2>
            </div>
            <div className="listTitle">{quoteDelivery.original_filename}</div>
            <p className="muted" style={{ marginBottom: 12 }}>{quoteStatusMessage(quoteDelivery)}</p>
            {quoteDelivery.portal_pdf_available && sessionToken.trim() ? (
              <div style={{ marginBottom: 16 }}>
                <PortalQuotePdfViewer
                  fetchUrl={quoteDeliveryFileUrl(quoteDelivery.id, false)}
                  portalToken={sessionToken}
                  title={quoteDelivery.original_filename}
                  onPreviewStateChange={(s) => {
                    if (!s.loading) setQuotePreviewFailed(Boolean(s.error))
                  }}
                />
              </div>
            ) : (
              <p className="muted" style={{ marginTop: 0, marginBottom: 16 }}>
                Download the quote to view it in Word, Google Docs, or your device&apos;s files app. Review the
                downloaded file before accepting.
              </p>
            )}
            {quoteDelivery.can_respond && quotePreviewFailed ? (
              <p className="muted" style={{ marginTop: 0, marginBottom: 12, fontSize: 13 }}>
                Preview could not be shown. Download the quote, review it, then accept if you are happy to proceed.
              </p>
            ) : null}
            {quoteDelivery.can_respond && !quoteDeclineOpen ? (
              <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                <button
                  type="button"
                  className={quotePreviewFailed ? 'btn primary' : 'btn'}
                  onClick={() => void downloadQuoteFile()}
                >
                  Download
                </button>
                <button
                  type="button"
                  className={quotePreviewFailed ? 'btn' : 'btn primary'}
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
            ) : quoteDelivery.can_respond && quoteDeclineOpen ? (
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
            ) : (
              <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                <button type="button" className="btn" onClick={() => void downloadQuoteFile()}>
                  Download
                </button>
              </div>
            )}
          </div>
        ) : activeFormId ? (
          <PortalFormFillPanel
            submissionId={activeFormId}
            portalToken={sessionToken}
            previewMode={staffPreview}
            sessionBlocked={recoveryNeeded}
            isSessionCurrent={isRenderedSessionCurrent}
            recoveryDraft={contactId && draft.current?.contactId === contactId ? draft.current : null}
            onDraftChange={(next) => { if (isRenderedSessionCurrent()) draft.current = next }}
            onBack={() => setActiveFormId(null)}
            onSubmitted={() => {
              if (!isRenderedSessionCurrent()) return
              setActiveFormId(null)
              draft.current = null
              setInfo('Thank you — your form has been submitted.')
              const token = sessionToken.trim()
              if (token) {
                void loadPendingForms(token)
                void loadClientActions(token)
                if (activeGrantId) void loadBrowse(activeGrantId, browseSubfolder, token)
              }
            }}
          />
        ) : activeCanarySign ? (
          <PortalCanarySignPanel
            signing={activeCanarySign}
            portalToken={sessionToken}
            previewMode={staffPreview}
            onSigningUpdated={(next) => { if (isRenderedSessionCurrent()) setActiveCanarySign(next) }}
            onBack={() => setActiveCanarySign(null)}
            onCompleted={(next) => {
              if (!isRenderedSessionCurrent()) return
              const done = (next.status || '').toLowerCase() === 'completed' || Boolean(next.has_signed_document)
              setInfo(
                done
                  ? 'Thank you — your signature has been submitted. You can download the signed document below.'
                  : 'Thank you — your signature has been submitted. Waiting for remaining signers before the final document is issued.',
              )
              const token = sessionToken.trim()
              if (token) {
                void loadClientActions(token)
                if (activeGrantId) void loadBrowse(activeGrantId, browseSubfolder, token)
              }
            }}
            onDeclined={() => {
              if (!isRenderedSessionCurrent()) return
              setActiveCanarySign(null)
              setInfo('Your decline has been recorded.')
              const token = sessionToken.trim()
              if (token) {
                void loadClientActions(token)
                if (activeGrantId) void loadBrowse(activeGrantId, browseSubfolder, token)
              }
            }}
          />
        ) : !activeCaseId && !activeGrantId ? (
          <div className="portalPage">
            {matterGroups.length > 0 ? (
              <>
                {mattersNeedingAttention.length > 0 ? (
                  <section className="portalSection">
                    <h2 className="portalSectionHeading">Needs your attention</h2>
                    {renderMatterList(mattersNeedingAttention)}
                  </section>
                ) : null}
                {otherMatters.length > 0 ? (
                  <section className="portalSection">
                    <h2 className="portalSectionHeading">
                      {mattersNeedingAttention.length > 0 ? 'Other matters' : 'Your matters'}
                    </h2>
                    {renderMatterList(otherMatters)}
                  </section>
                ) : null}
              </>
            ) : (
              <div className="muted portalEmptyState">
                Nothing has been shared with you yet. When your solicitor shares documents, quotes, or forms, they will
                appear here.
              </div>
            )}
          </div>
        ) : activeCaseId && !activeGrantId ? (
          <div className="portalPage">
            <header className="portalPageHeader">
              <button type="button" className="btn portalBackBtn" onClick={() => void backToAllMatters()}>
                ← All matters
              </button>
              <h2 className="portalPageTitle">{activeMatter?.caseTitle ?? 'Matter'}</h2>
            </header>
            {renderYourActions()}
            {activeMatter && activeMatter.grants.length > 0 ? (
              <section className="portalSection">
                <h2 className="portalSectionHeading">Folders</h2>
                <div className="list portalFolderList">
                  {activeMatter.grants.map((g) => (
                    <button
                      key={g.id}
                      type="button"
                      className="listCard rowbtn portalFolderCard"
                      onClick={() => openGrant(g.id)}
                    >
                      <span className="portalFolderIcon" aria-hidden>
                        📁
                      </span>
                      <div className="portalFolderCardMain">
                        <div className="listTitle">{portalGrantFolderLabel(g.folder_label)}</div>
                        <div className="muted portalFolderMeta">
                          {g.can_download ? 'View & download' : 'View'}
                          {g.can_upload ? ' · Upload allowed' : ''}
                          {(g.new_file_count ?? 0) > 0
                            ? ` · ${g.new_file_count === 1 ? '1 new file' : `${g.new_file_count} new files`}`
                            : ''}
                        </div>
                      </div>
                      {(g.new_file_count ?? 0) > 0 ? (
                        <span className="portalNewBadge" title="New since last visit">
                          New
                        </span>
                      ) : null}
                      <span className="portalRowChevron" aria-hidden>
                        ›
                      </span>
                    </button>
                  ))}
                </div>
              </section>
            ) : !hasScopedActions ? (
              <div className="muted">No folders are shared for this matter.</div>
            ) : null}
          </div>
        ) : (
          <div className="portalPage">
            <header className="portalPageHeader">
              <div className="portalPageHeaderTop">
                <button type="button" className="btn portalBackBtn" onClick={() => void backToFolderList()}>
                  ← Folders
                </button>
                <div className="portalPageToolbar">
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
              </div>
              <h2 className="portalPageTitle">{currentFolderTitle}</h2>
              {activeMatter ? <p className="portalPageContext">{activeMatter.caseTitle}</p> : null}
            </header>

            {browseBreadcrumb.length > 0 ? (
              <div className="portalBreadcrumb muted">
                <button type="button" className="btnLink" onClick={() => navigateBreadcrumb(-1)}>
                  {portalGrantFolderLabel(activeGrant?.folder_label) || 'Root'}
                </button>
                {browseBreadcrumb.map((part, idx) => (
                  <span key={`${part}-${idx}`} className="portalBreadcrumbPart">
                    <span aria-hidden>/</span>
                    {idx === browseBreadcrumb.length - 1 ? (
                      <span>{decodeFolderPathSegment(part)}</span>
                    ) : (
                      <button type="button" className="btnLink" onClick={() => navigateBreadcrumb(idx)}>
                        {decodeFolderPathSegment(part)}
                      </button>
                    )}
                  </span>
                ))}
              </div>
            ) : null}

            {busy && !browse ? <div className="muted">Loading…</div> : null}

            <div className="table portalFilesTable">
              <div className="tr th" style={{ gridTemplateColumns: PORTAL_FILES_GRID }}>
                <div className="thCell portalFilesTableIconCol" aria-hidden />
                <div className="thCell">Name</div>
                <div className="thCell portalFilesTableSizeCol">Size</div>
                <div className="thCell portalFilesTableActionsCol">Actions</div>
              </div>
              {subfolders.map((name) => (
                <div
                  key={`dir-${name}`}
                  className="tr rowbtn portalFilesTableRow"
                  style={{ gridTemplateColumns: PORTAL_FILES_GRID }}
                  onClick={() => navigateToSubfolder(name)}
                >
                  <div className="td portalFilesTableIconCol">
                    <span className="docsTypeIcon" aria-hidden>
                      📁
                    </span>
                  </div>
                  <div className="td">{decodeFolderPathSegment(name)}</div>
                  <div className="td muted portalFilesTableSizeCol">—</div>
                  <div className="td muted portalFilesTableActionsCol">Open</div>
                </div>
              ))}
              {files.map((f) => (
                <div key={f.id} className="tr portalFilesTableRow" style={{ gridTemplateColumns: PORTAL_FILES_GRID }}>
                  <div className="td portalFilesTableIconCol">
                    <span className="docsTypeIcon" aria-hidden>
                      <DocMimeIcon mime={f.mime_type} filename={f.original_filename} />
                    </span>
                  </div>
                  <div className="td portalFilesTableName">
                    {f.original_filename}
                    {f.is_new ? (
                      <span className="portalNewBadge portalNewBadge--inline" title="New since last visit">
                        New
                      </span>
                    ) : null}
                  </div>
                  <div className="td muted portalFilesTableSizeCol">{formatBytes(f.size_bytes)}</div>
                  <div className="td portalFilesTableActions">
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
                <div className="muted portalEmptyState">No files in this folder yet.</div>
              ) : null}
            </div>
          </div>
        )}
    </PortalLayout>
  )
}
