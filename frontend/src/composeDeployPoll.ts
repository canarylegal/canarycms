import { apiFetch, apiUrl } from './api'
import type { AdminDeployComposeJobOut, AdminDeployTriggerOut } from './types'

const POLL_MS = 2500
/** After compose up, wait for API/proxy to answer before reloading the browser. */
const RESTART_WAIT_MS = 120_000
const RESTART_POLL_MS = 2000
/** Slightly longer than backend compose build timeout (3600s). */
const MAX_WAIT_MS = 2 * 3600 * 1000 + 120_000

/** Longer retry window while nginx/Cloudflare returns 502 during container recreate. */
const POLL_FETCH_RETRIES = 18
const POLL_FETCH_RETRY_MS = 2500

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms))
}

/** Transient proxy errors while the stack is being recreated. */
export async function apiFetchWithRetry<T>(
  path: string,
  token: string,
  init?: RequestInit & { json?: unknown },
): Promise<T> {
  let last: unknown
  for (let attempt = 0; attempt < POLL_FETCH_RETRIES; attempt++) {
    try {
      return await apiFetch<T>(path, { token, ...init })
    } catch (e) {
      last = e
      const err = e as { status?: number; message?: string }
      const retry =
        err?.status === 502 ||
        err?.status === 503 ||
        err?.status === 504 ||
        err?.status === 520 ||
        (typeof err?.message === 'string' && /failed to fetch|networkerror|load failed/i.test(err.message))
      if (!retry || attempt === POLL_FETCH_RETRIES - 1) throw e
      await sleep(POLL_FETCH_RETRY_MS)
    }
  }
  throw last
}

/** Poll ``/health`` until the stack is reachable again after ``compose up`` recreates containers. */
export async function waitForAppReadyAfterComposeUpdate(): Promise<void> {
  const deadline = Date.now() + RESTART_WAIT_MS
  while (Date.now() < deadline) {
    try {
      const res = await fetch(apiUrl('/health'), { cache: 'no-store' })
      if (res.ok) return
    } catch {
      /* proxy or API still restarting */
    }
    await sleep(RESTART_POLL_MS)
  }
}

/**
 * POST /admin/deploy/trigger then poll GET /admin/deploy/compose-job until the returned job finishes.
 * HTTP returns immediately so reverse proxies (e.g. Cloudflare) do not time out during docker build.
 */
export async function postDeployTriggerAndWaitForCompose(
  token: string,
  body: { method: 'auto' | 'compose'; git_strategy?: 'ff-only' | 'reset' },
  options?: {
    onProgress?: (st: AdminDeployComposeJobOut) => void
    onFinishing?: () => void
  },
): Promise<{ message: string; usedComposeAsync: boolean; reloadApp: boolean }> {
  const out = await apiFetchWithRetry<AdminDeployTriggerOut>('/admin/deploy/trigger', token, {
    method: 'POST',
    json: body,
  })
  if (!out.async_mode || !out.job_id) {
    return { message: out.message, usedComposeAsync: false, reloadApp: false }
  }
  const expectId = out.job_id
  const deadline = Date.now() + MAX_WAIT_MS

  while (Date.now() < deadline) {
    const st = await apiFetchWithRetry<AdminDeployComposeJobOut>('/admin/deploy/compose-job', token)

    if (st.status === 'running' && st.job_id && st.job_id !== expectId) {
      throw new Error('Another compose update started; stopping this wait.')
    }

    if (st.job_id === expectId) {
      if (st.status === 'running') {
        options?.onProgress?.(st)
      }
      if (st.status === 'succeeded') {
        options?.onFinishing?.()
        await waitForAppReadyAfterComposeUpdate()
        return { message: 'Update complete.', usedComposeAsync: true, reloadApp: true }
      }
      if (st.status === 'failed') {
        const detail = st.error_detail || ''
        if (detail.includes('restarted during the update')) {
          options?.onFinishing?.()
          await waitForAppReadyAfterComposeUpdate()
          return { message: 'Update complete.', usedComposeAsync: true, reloadApp: true }
        }
        const tail = st.log_excerpt ? `\n\n${st.log_excerpt}` : ''
        throw new Error(`${detail || 'Compose update failed.'}${tail}`)
      }
    }

    await sleep(POLL_MS)
  }

  throw new Error('Timed out waiting for compose update. Check Admin → Deploy or server logs.')
}
