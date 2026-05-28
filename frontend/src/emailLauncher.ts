import type { UserPublic } from './types'

/** Default Outlook on the web inbox (user may override in settings). */
export const DEFAULT_OUTLOOK_WEB_MAIL_URL = 'https://outlook.office.com/mail'

/** Admin → E-mail Graph mode with resolvable Entra credentials (OWA links, Outlook categories — not compose). */
export function isOrgMicrosoftGraphConfigured(user: UserPublic | null | undefined): boolean {
  return (
    user?.email_integration_mode === 'microsoft_graph' && user?.m365_graph_drafts_configured === true
  )
}

export const OUTLOOK_WEB_WITHOUT_GRAPH_CONFIRM_MESSAGE =
  'Your organisation does not have Microsoft Graph / Entra configured. If you attempt to use Outlook Web, expect significant deficiencies in functionality. We recommend that you use Outlook desktop instead. Do you still want to proceed?'

/**
 * Unfold RFC 822 header lines (continuation lines begin with space or tab).
 */
function unfoldHeaderBlock(block: string): string[] {
  const lines = block.replace(/\r\n/g, '\n').split('\n')
  const out: string[] = []
  for (const line of lines) {
    if ((line.startsWith(' ') || line.startsWith('\t')) && out.length > 0) {
      out[out.length - 1] = `${out[out.length - 1].trimEnd()} ${line.trim()}`.trim()
    } else {
      out.push(line.trimEnd())
    }
  }
  return out
}

/**
 * Read the first `Message-ID` / `Message-Id` header value from raw RFC822 / .eml text.
 * Returns the trimmed header value (often including angle brackets).
 */
export function extractInternetMessageIdFromEmlText(raw: string): string | null {
  let s = raw.replace(/\r\n/g, '\n')
  /* Skip leading mbox "From sender Thu ..." line if present */
  if (s.startsWith('From ') && s.includes('\n')) {
    const nl = s.indexOf('\n')
    s = s.slice(nl + 1)
  }
  const idx = s.indexOf('\n\n')
  const headerBlock = idx === -1 ? s : s.slice(0, idx)
  if (!headerBlock.trim()) return null
  for (const line of unfoldHeaderBlock(headerBlock)) {
    const m = /^message-id\s*:\s*(.+)$/i.exec(line)
    if (m) {
      const v = m[1].trim()
      return v || null
    }
  }
  return null
}

/**
 * Outlook / Exchange KQL: search by Internet Message ID so OWA can jump to that message
 * if it exists in the user’s mailbox (same ID as in the .eml headers).
 *
 * @see https://learn.microsoft.com/en-us/microsoftsearch/reference-syntax
 */
function kqlInternetMessageId(messageIdHeaderValue: string): string {
  const t = messageIdHeaderValue.trim()
  if (t.startsWith('<') && t.endsWith('>')) {
    return `internetmessageid:${t}`
  }
  return `internetmessageid:<${t}>`
}

/** True when the .eml was built by the Outlook add-in (not a live Exchange Message-ID). */
export function isCanarySyntheticMessageId(messageIdHeaderValue: string | null | undefined): boolean {
  const s = (messageIdHeaderValue || '').trim().toLowerCase()
  return s.includes('@canary-outlook-addin')
}

/** Graph / REST mailbox message ids are typically long ``AAMk…`` / ``AQMk…`` strings. */
export function isLikelyExchangeRestItemId(itemId: string | null | undefined): boolean {
  const s = (itemId || '').trim()
  if (!s || s.includes('[object')) return false
  if (/^AAMk/i.test(s) || /^AQMk/i.test(s) || /^AQAA/i.test(s)) return true
  if (s.includes('@')) return false
  return s.length >= 40
}

function normalizeOwaHost(url: string): string {
  return url.replace(/^https?:\/\/outlook\.office365\.com(?=\/|$)/i, 'https://outlook.office.com')
}

function owaOriginAndMailPrefix(owaBaseFromUser: string | null | undefined): { origin: string; prefix: string } {
  const base = (owaBaseFromUser || '').trim() || DEFAULT_OUTLOOK_WEB_MAIL_URL
  try {
    const u = new URL(base.includes('://') ? base : `https://${base}`)
    const origin = normalizeOwaHost(u.origin)
    const prefix = u.pathname.toLowerCase().includes('/mail/0') ? '/mail/0' : '/mail/0'
    return { origin, prefix }
  } catch {
    return { origin: new URL(DEFAULT_OUTLOOK_WEB_MAIL_URL).origin, prefix: '/mail/0' }
  }
}

function owaOriginAndMailPrefixForItemId(
  owaBaseFromUser: string | null | undefined,
  outlookWebLink?: string | null,
): { origin: string; prefix: string } {
  const wl = (outlookWebLink || '').trim()
  if (wl) {
    try {
      const u = new URL(wl.includes('://') ? wl : `https://${wl}`)
      if (u.hostname) {
        return { origin: normalizeOwaHost(u.origin), prefix: '/mail/0' }
      }
    } catch {
      /* fall through */
    }
  }
  return owaOriginAndMailPrefix(owaBaseFromUser)
}

/** True when the URL is a Graph/OWA single-message open link. */
export function isUsableOutlookMessageWebLink(url: string | null | undefined): boolean {
  const trimmed = (url || '').trim()
  if (!trimmed.startsWith('http://') && !trimmed.startsWith('https://')) return false
  const low = trimmed.toLowerCase()
  if (low.includes('deeplink/search')) return false
  if (low.includes('deeplink/read')) return true
  if (low.includes('itemid=')) return true
  if (low.includes('/owa/') && low.includes('viewmodel=readmessageitem')) return true
  return false
}

function owaOriginFromBase(owaBaseFromUser: string | null | undefined): string {
  return owaOriginAndMailPrefix(owaBaseFromUser).origin
}

/**
 * Extract an Exchange REST item id from a Graph ``webLink`` or legacy OWA URL.
 */
export function extractItemIdFromOutlookWebUrl(url: string): string | null {
  const trimmed = (url || '').trim()
  if (!trimmed) return null
  try {
    const u = new URL(trimmed.includes('://') ? trimmed : `https://${trimmed}`)
    for (const key of ['ItemID', 'itemid', 'ItemId']) {
      const v = u.searchParams.get(key)
      if (v && v.trim()) return v.trim()
    }
    const readPath = /\/deeplink\/read\/([^/?]+)/i.exec(u.pathname)
    if (readPath?.[1]) {
      try {
        return decodeURIComponent(readPath[1]).trim()
      } catch {
        return readPath[1].trim()
      }
    }
    const inboxPath = /\/mail\/[^/]+\/id\/([^/?]+)/i.exec(u.pathname)
    if (inboxPath?.[1]) {
      try {
        return decodeURIComponent(inboxPath[1]).trim()
      } catch {
        return inboxPath[1].trim()
      }
    }
  } catch {
    /* ignore */
  }
  return null
}

/**
 * Rebuild OWA read URLs using the current ``/mail/deeplink/read/{id}`` shape.
 * Legacy ``/owa/?ItemID=`` and Graph ``webLink`` values often redirect to routes that spin forever.
 */
export function normalizeOutlookWebReadLink(
  url: string,
  owaBaseFromUser?: string | null,
): string | null {
  const itemId = extractItemIdFromOutlookWebUrl(url)
  if (itemId && isLikelyExchangeRestItemId(itemId)) {
    return buildOutlookWebReadItemUrl(owaBaseFromUser ?? null, itemId)
  }
  if (/deeplink\/search/i.test(url) || /\/owa\/\?/i.test(url)) {
    return null
  }
  return null
}

/**
 * Build an Outlook on the web URL that opens mailbox search scoped to this Message-ID.
 * The message must exist in the user’s Exchange / M365 mailbox for a result to appear.
 */
export function buildOutlookWebMessageSearchUrl(owaBaseFromUser: string | null | undefined, messageIdHeaderValue: string): string {
  const origin = owaOriginFromBase(owaBaseFromUser)
  const kql = kqlInternetMessageId(messageIdHeaderValue)
  /* “Deeplink search” opens OWA with the search box pre-filled (tenant UI may vary slightly). */
  return `${origin}/mail/deeplink/search?query=${encodeURIComponent(kql)}`
}

/**
 * OWA read URL for a Graph / REST message id.
 * Prefer this over legacy ``/owa/?ItemID=`` (redirects to deeplink routes that can hang on “Loading”).
 */
export function buildOutlookWebReadItemUrl(
  owaBaseFromUser: string | null | undefined,
  restItemId: string,
  outlookWebLink?: string | null,
): string {
  const { origin, prefix } = owaOriginAndMailPrefixForItemId(owaBaseFromUser, outlookWebLink)
  const id = restItemId.trim()
  const encId = encodeURIComponent(id)
  return `${origin}${prefix}/deeplink/read/${encId}?ItemID=${encId}&exvsurl=1&viewmodel=ReadMessageItem`
}

/** OWA folder view for Sent Items (when only a Canary copy is stored, not a deeplink item id). */
export function buildOutlookWebSentItemsUrl(owaBaseFromUser: string | null | undefined): string {
  const { origin, prefix } = owaOriginAndMailPrefix(owaBaseFromUser)
  return `${origin}${prefix}/sentitems/`
}

/** Whether “Open” in Outlook web can target a live mailbox message (vs Canary-only synthetic .eml). */
export function canOpenEmlInOutlookWebMailbox(file: {
  source_internet_message_id?: string | null
  source_outlook_item_id?: string | null
  outlook_graph_message_id?: string | null
  outlook_web_link?: string | null
}): boolean {
  const web = (file.outlook_web_link || '').trim()
  if (web) {
    const iid = extractItemIdFromOutlookWebUrl(web)
    if (iid && isLikelyExchangeRestItemId(iid)) return true
  }
  const gid = (file.outlook_graph_message_id || file.source_outlook_item_id || '').trim()
  if (isLikelyExchangeRestItemId(gid)) return true
  const mid = (file.source_internet_message_id || '').trim()
  if (!isCanarySyntheticMessageId(mid) && mid) return true
  return false
}

/**
 * Default mailbox compose route. ``/mail/0/`` selects the primary account in multi-account OWA; compose prefill is
 * unreliable on ``/mail/deeplink/compose`` alone for many work tenants.
 */
const OWA_COMPOSE_DEEPLINK_PATH = '/mail/0/deeplink/compose'

/** Outlook treats ``+`` in compose query values as a literal plus, not a space — normalize to ``%20``. */
export function normalizeComposeQueryPlusAsSpaces(url: string): string {
  const q = url.indexOf('?')
  if (q < 0) return url
  return url.slice(0, q + 1) + url.slice(q + 1).replace(/\+/g, '%20')
}

/**
 * Outlook on the web “new message” URL (no Graph). When org integration is mailto and the user chose “Outlook web”.
 *
 * ``mailtouri=`` is for Edge’s **mailto protocol handler** (``--app=…``). A normal browser navigation to that URL often
 * loads the mail shell without opening compose. We instead use the compose route with explicit ``to`` / ``subject`` /
 * ``body`` and ``encodeURIComponent`` (not ``URLSearchParams``, which can emit ``+`` for spaces and confuse OWA).
 *
 * Auth hints (``login_hint`` / ``domain_hint``) are appended separately via ``appendOutlookWebAuthHintsForNav``.
 */
export function buildOutlookWebComposeUrl(
  owaBaseFromUser: string | null | undefined,
  params: { to: string; subject: string; body: string },
): string {
  const base = (owaBaseFromUser || '').trim() || DEFAULT_OUTLOOK_WEB_MAIL_URL
  let origin: string
  try {
    const u = new URL(base.includes('://') ? base : `https://${base}`)
    origin = u.origin
  } catch {
    origin = new URL(DEFAULT_OUTLOOK_WEB_MAIL_URL).origin
  }

  const to = (params.to || '').trim()
  const q: string[] = []
  if (to) q.push(`to=${encodeURIComponent(to)}`)
  q.push(`subject=${encodeURIComponent(params.subject)}`)
  q.push(`body=${encodeURIComponent(params.body)}`)

  return normalizeComposeQueryPlusAsSpaces(`${origin}${OWA_COMPOSE_DEEPLINK_PATH}?${q.join('&')}`)
}

/**
 * Build a ``mailto:`` URL with optional to, subject, and body (RFC 6068).
 */
export function buildMailtoComposeUrl(params: { to: string; subject: string; body: string }): string {
  const to = (params.to || '').trim()
  const q: string[] = []
  if (params.subject) q.push(`subject=${encodeURIComponent(params.subject)}`)
  if (params.body) q.push(`body=${encodeURIComponent(params.body)}`)
  const query = q.length ? `?${q.join('&')}` : ''
  return normalizeComposeQueryPlusAsSpaces(`mailto:${to}${query}`)
}

/**
 * Opens the user's preferred mail handler (desktop ``mailto:`` or Outlook on the web).
 * Used when opening mail from a matter (e.g. .eml fallback without Message-ID).
 */
export function openCanaryEmailLauncher(me: UserPublic | null | undefined): void {
  const pref = me?.email_launch_preference ?? 'desktop'
  if (pref === 'outlook_web') {
    const raw = (me?.email_outlook_web_url ?? '').trim() || DEFAULT_OUTLOOK_WEB_MAIL_URL
    try {
      const u = new URL(raw)
      if (u.protocol !== 'http:' && u.protocol !== 'https:') throw new Error('unsupported scheme')
      window.open(u.toString(), '_blank', 'noopener,noreferrer')
    } catch {
      window.open(DEFAULT_OUTLOOK_WEB_MAIL_URL, '_blank', 'noopener,noreferrer')
    }
    return
  }
  const a = document.createElement('a')
  a.href = 'mailto:'
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}
