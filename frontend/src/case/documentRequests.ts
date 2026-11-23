import { signalSessionExpired } from '../auth/sessionRecovery'
import { apiUrl, applyAuthHeaders } from '../api'

export class DocumentRequestError extends Error {
  readonly status: number | null
  readonly retryable: boolean
  constructor(message: string, status: number | null, retryable: boolean) {
    super(message)
    this.status = status
    this.retryable = retryable
    this.name = 'DocumentRequestError'
  }
}

export function documentErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof DocumentRequestError) return error.message
  const status = (error as { status?: number } | null)?.status
  if (status === 401) return 'Your session has expired. Sign in again in another tab, then retry. Keep this window open.'
  if (status === 403) return 'You do not have permission to access this document. Ask your administrator to check your access.'
  if (status === 423) return 'This document is quarantined or awaiting a security check. It cannot be opened until Canary marks it clean.'
  if (status === 404) return 'This document is no longer available. Refresh the document list.'
  if (error instanceof TypeError) return 'Could not reach the server. Check your connection and try again.'
  if ((error as { name?: string } | null)?.name === 'AbortError') return 'The document request timed out. Please try again.'
  const message = (error as { message?: unknown } | null)?.message
  return typeof message === 'string' && message && !message.trim().startsWith('<') ? message : fallback
}

/** A deadline covers the response body too. Only reads are automatically retried. */
export async function documentRequest<T>(
  path: string,
  token: string | undefined,
  read: (response: Response) => Promise<T>,
  options: { method?: 'GET' | 'POST'; body?: BodyInit; timeoutMs?: number; retryReads?: boolean; idempotencyKey?: string } = {},
): Promise<T> {
  const method = options.method ?? 'GET'
  for (let attempt = 0; ; attempt++) {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? 90_000)
    try {
      const headers = new Headers()
      applyAuthHeaders(headers, token ?? '')
      if (options.idempotencyKey) headers.set('Idempotency-Key', options.idempotencyKey)
      const response = await fetch(apiUrl(path), { method, headers, credentials: 'include', body: options.body, signal: controller.signal })
      if (!response.ok) {
        const status = response.status
        if (status === 401) signalSessionExpired()
        const retryable = status === 429 || ((method === 'GET' || !!options.idempotencyKey) && [408, 500, 502, 503, 504].includes(status))
        let message = documentErrorMessage({ status }, 'The document request failed. Please try again.')
        if (status === 429) message = 'The server is busy. Wait a moment, then retry.'
        else if (status === 410) message = 'The previously uploaded document was deleted. Start a new import only if you want to recreate it.'
        else if (options.idempotencyKey && (status >= 500 || status === 408)) message = 'The upload result could not be confirmed. Retry safely to check or finish this file.'
        else if (status >= 500) message = method === 'POST'
          ? 'The upload result could not be confirmed. Refresh the document list before importing this file again to avoid a duplicate.'
          : 'The document service is temporarily unavailable. Please try again.'
        else if (status === 413) message = 'This file is too large to upload.'
        else if ([400, 409, 422].includes(status)) {
          const body: unknown = await response.json().catch(() => null)
          const detail = (body as { detail?: unknown } | null)?.detail
          if (typeof detail === 'string' && !detail.includes('<')) message = detail.slice(0, 400)
        }
        throw new DocumentRequestError(message, status, retryable)
      }
      return await read(response)
    } catch (error) {
      const failure = error instanceof DocumentRequestError ? error : new DocumentRequestError(
        options.idempotencyKey ? 'The upload result could not be confirmed. Retry safely to check or finish this file.' : method === 'POST'
          ? 'The upload result could not be confirmed. Refresh the document list before importing this file again to avoid a duplicate.'
          : documentErrorMessage(error, 'Could not read the document. Please try again.'),
        null, (method === 'GET' || !!options.idempotencyKey) && (error instanceof TypeError || controller.signal.aborted || (!!options.idempotencyKey && error instanceof SyntaxError)),
      )
      if (method !== 'GET' || options.retryReads === false || !failure.retryable || attempt >= 1) throw failure
    } finally {
      clearTimeout(timer)
    }
    await new Promise((resolve) => setTimeout(resolve, 300))
  }
}
