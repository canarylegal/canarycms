/**
 * Outlook on the web / Graph-style open helpers (aligned with canarycms.experimental).
 * Uses the same OWA deeplink shapes as ``emailLauncher.ts``; naming matches the experimental UI.
 */

import { buildOutlookWebReadItemUrl, DEFAULT_OUTLOOK_WEB_MAIL_URL } from './emailLauncher'

/**
 * Build OWA “read item” URL from a Microsoft Graph message id or Exchange REST item id.
 * In practice these identifiers use the same ``AAMk…`` shape for mailbox messages.
 */
export function buildOutlookWebReadUrlFromGraphMessageId(
  graphMessageId: string,
  owaBaseFromUser?: string | null,
): string {
  return buildOutlookWebReadItemUrl(owaBaseFromUser ?? null, graphMessageId)
}

/** Reasonable default for “open this message in OWA” as a secondary window (not full-screen tab). */
export const OWA_MESSAGE_WINDOW_FEATURES =
  'width=1050,height=760,scrollbars=yes,resizable=yes,status=no'

/**
 * Reuse one popup for Canary → OWA navigations so the browser keeps Microsoft session cookies in that browsing context
 * (new anonymous ``_blank`` windows often trigger account-picker / sign-in again).
 */
export const OWA_MAIL_WINDOW_NAME = 'CanaryOwaMail'

function consumerMicrosoftMailboxDomain(domain: string): boolean {
  const d = domain.toLowerCase()
  return (
    d === 'outlook.com' ||
    d === 'hotmail.com' ||
    d === 'live.com' ||
    d === 'msn.com' ||
    d.endsWith('.outlook.com')
  )
}

/**
 * Open a full ``https://…`` Outlook URL; returns whether ``window.open`` returned a handle (not fully reliable across browsers).
 * Avoid ``noopener`` in ``windowFeatures``: some browsers return ``null`` from ``window.open`` while still opening the window.
 */
export function openOutlookWebAppFromGraphWebLink(
  url: string,
  options?: { windowFeatures?: string | null; windowName?: string; fullTab?: boolean },
): boolean {
  if (options?.fullTab) {
    const w = window.open(url, '_blank', 'noopener,noreferrer')
    return w != null
  }
  const feat = options?.windowFeatures
  const name = options?.windowName ?? OWA_MAIL_WINDOW_NAME
  const w =
    feat != null && feat !== '' ? window.open(url, name, feat) : window.open(url, name)
  return w != null
}

/**
 * Append ``login_hint`` / ``domain_hint`` so Microsoft identity can pick the right work account without an extra prompt.
 * (Consumer @outlook.com addresses skip ``domain_hint`` — it can confuse live.com / personal flows.)
 */
export function appendOutlookWebAuthHintsForNav(url: string, loginHint: string | null | undefined): string {
  const h = (loginHint || '').trim()
  if (!h) return url
  try {
    const base = url.startsWith('http://') || url.startsWith('https://') ? url : `https://${url}`
    const u = new URL(base)
    if (!u.searchParams.has('login_hint')) {
      u.searchParams.set('login_hint', h)
    }
    const at = h.indexOf('@')
    if (at > 0 && at < h.length - 1) {
      const domain = h.slice(at + 1).trim().toLowerCase()
      if (domain && !consumerMicrosoftMailboxDomain(domain) && !u.searchParams.has('domain_hint')) {
        u.searchParams.set('domain_hint', domain)
      }
    }
    return u.toString()
  } catch {
    return url
  }
}

export function outlookWebMailBase(owaBaseFromUser: string | null | undefined): string {
  const raw = (owaBaseFromUser || '').trim() || DEFAULT_OUTLOOK_WEB_MAIL_URL
  try {
    const u = new URL(raw.includes('://') ? raw : `https://${raw}`)
    return `${u.origin}/mail/`
  } catch {
    return `${new URL(DEFAULT_OUTLOOK_WEB_MAIL_URL).origin}/mail/`
  }
}
