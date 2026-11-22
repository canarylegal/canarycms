import { apiFetch } from '../api'
import type { PrecedentOut } from '../types'

/** Keep a retry identity for the same form/file until the server confirms it. */
export function createPrecedentUploader() {
  let attempt: { file: File; metadata: string; key: string } | null = null
  return async (token: string, file: File, fields: Record<string, string>) => {
    const metadata = JSON.stringify(Object.entries(fields).sort(([a], [b]) => a.localeCompare(b)))
    if (!attempt || attempt.file !== file || attempt.metadata !== metadata) {
      attempt = { file, metadata, key: crypto.randomUUID() }
    }
    const body = new FormData()
    for (const [key, value] of Object.entries(fields)) body.set(key, value)
    body.set('upload', file)
    const result = await apiFetch<PrecedentOut>('/precedents', {
      token, method: 'POST', body, headers: { 'Idempotency-Key': attempt.key },
    })
    attempt = null
    return result
  }
}
