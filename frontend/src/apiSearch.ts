import { apiFetch } from './api'
import type { CaseOut, ContactOut } from './types'

export type ContactSearchParams = {
  q?: string
  limit?: number
  type?: 'person' | 'organisation'
  hasEmail?: boolean
  hasPhone?: boolean
}

export type CaseSearchParams = {
  q: string
  limit?: number
  status?: string
}

export async function fetchContactSearch(token: string, params: ContactSearchParams = {}): Promise<ContactOut[]> {
  const qs = new URLSearchParams()
  const q = params.q?.trim()
  if (q) qs.set('q', q)
  if (params.limit != null) qs.set('limit', String(params.limit))
  if (params.type) qs.set('type', params.type)
  if (params.hasEmail === true) qs.set('has_email', 'true')
  if (params.hasEmail === false) qs.set('has_email', 'false')
  if (params.hasPhone === true) qs.set('has_phone', 'true')
  if (params.hasPhone === false) qs.set('has_phone', 'false')
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  const data = await apiFetch<ContactOut[]>(`/contacts${suffix}`, { token })
  return Array.isArray(data) ? data : []
}

export async function fetchCaseSearch(token: string, params: CaseSearchParams): Promise<CaseOut[]> {
  const qs = new URLSearchParams()
  qs.set('q', params.q.trim())
  if (params.limit != null) qs.set('limit', String(params.limit))
  if (params.status) qs.set('status', params.status)
  const data = await apiFetch<CaseOut[]>(`/cases?${qs.toString()}`, { token })
  return Array.isArray(data) ? data : []
}

export async function fetchContactById(token: string, contactId: string): Promise<ContactOut | null> {
  try {
    return await apiFetch<ContactOut>(`/contacts/${contactId}`, { token })
  } catch {
    return null
  }
}

export async function fetchCaseById(token: string, caseId: string): Promise<CaseOut | null> {
  try {
    return await apiFetch<CaseOut>(`/cases/${caseId}`, { token })
  } catch {
    return null
  }
}
