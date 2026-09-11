import { apiUrl, applyAuthHeaders } from '../api'
import type { CaseContactOut, FileSummary } from '../types'
import { penceGb } from './financeTotals'

export function fileDocOwnerLabel(f: FileSummary): string {
  return f.owner_initials ?? f.owner_display_name ?? f.owner_email ?? '—'
}

/** Abort same-origin file GETs so a stuck server/proxy cannot leave the UI on “Loading” indefinitely. */
export const CASE_FILE_FETCH_MS = 90_000

export function caseAuthHeaders(token: string): Headers {
  const h = new Headers()
  applyAuthHeaders(h, String(token ?? '').trim())
  return h
}

export async function fetchCaseFileResponse(caseId: string, fileId: string, token: string): Promise<Response> {
  const ctrl = new AbortController()
  const tid = window.setTimeout(() => ctrl.abort(), CASE_FILE_FETCH_MS)
  try {
    return await fetch(apiUrl(`/cases/${caseId}/files/${fileId}`), {
      headers: caseAuthHeaders(token),
      signal: ctrl.signal,
    })
  } finally {
    clearTimeout(tid)
  }
}

export function fetchTimedOutMessage(e: unknown): string | null {
  const err = e as { name?: string }
  return err?.name === 'AbortError' ? 'Request timed out — try again or use Download.' : null
}

/** Preview only: read up to this cap (octets preserved via ISO-8859-1) so we never wait on multi‑GB .eml bodies. */
export const EML_PREVIEW_STREAM_CAP = 768 * 1024

export async function fetchEmlTextForPreview(caseId: string, fileId: string, token: string): Promise<string> {
  const ctrl = new AbortController()
  const tid = window.setTimeout(() => ctrl.abort(), CASE_FILE_FETCH_MS)
  try {
    const res = await fetch(apiUrl(`/cases/${caseId}/files/${fileId}`), {
      headers: caseAuthHeaders(token),
      signal: ctrl.signal,
    })
    if (res.status === 401) {
      localStorage.removeItem('token')
      window.location.reload()
      return ''
    }
    if (!res.ok) throw new Error((await res.text()) || res.statusText)
    if (!res.body) return await res.text()
    const reader = res.body.getReader()
    const decoder = new TextDecoder('iso-8859-1', { fatal: false })
    let out = ''
    while (out.length < EML_PREVIEW_STREAM_CAP) {
      const { done, value } = await reader.read()
      if (done) break
      if (value) out += decoder.decode(value, { stream: true })
      if (out.length >= EML_PREVIEW_STREAM_CAP) {
        try {
          ctrl.abort()
        } catch {
          /* ignore */
        }
        break
      }
    }
    return out
  } finally {
    clearTimeout(tid)
  }
}

export function ledgerSignedGb(p: number): string {
  if (p === 0) return penceGb(0)
  return p < 0 ? `-${penceGb(-p)}` : penceGb(p)
}

export const CLIENT_TYPE_SLUG = 'client'
export const LAWYERS_TYPE_SLUG = 'lawyers'

export function isClientMatterContact(c: CaseContactOut) {
  return (c.matter_contact_type || '').trim().toLowerCase() === CLIENT_TYPE_SLUG
}
